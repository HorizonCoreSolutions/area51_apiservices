import json
from urllib.parse import quote
import requests
from hashlib import sha256
from uuid import uuid4
from decimal import Decimal
from django.conf import settings
from dataclasses import dataclass
from apps.users.utils import redis_client
from apps.bets.models import Transactions
from typing import Callable, Dict, Optional
from apps.core.custom_types import BasicReturn
from apps.core.file_logger import SimpleLogger
from apps.acuitytec.acuitytec import AcuityTecAPI
from apps.acuitytec.models import DocumentTypeChoise
from apps.users.models import (
    Users,
    CoinflowAuthState,
    VERIFICATION_PENDING,
    VERIFICATION_APPROVED,
    VERIFICATION_PROCESSING,
    VERIFICATION_REJECTED,
    VERIFICATION_FAILED,
    VERIFICATION_CANCELED,
    VERIFICATION_EXPIRED
)

logger = SimpleLogger(name='Coinflow', log_file='logs/coinflow.log').get_logger()

@dataclass
class CoinFlowConfig:
    """Configuration for CoinFlow API client"""
    auth_token: str
    api_url: str
    auth_header: str
    redirection_url: str
    timeout: int = 30
    max_retries: int = 2


class CoinFlowEndpoints:
    def __init__(self, url: str):
        self._base_url: str = url.rstrip("")

    @property
    def get_merchant(self) -> str:
        return f'{self._base_url}/api/merchant'
    
    
    @property
    def register_user_attested(self) -> str:
        """
        End-point for user registration with attestation.
        Required headers: Authorization, x-coinflow-auth-user-id
        """
        return f'{self._base_url}/api/withdraw/kyc/attested'
    
    @property
    def register_user_document(self) -> str:
        """
        End-point for user document registration.
        Required headers: Authorization, x-coinflow-auth-user-id
        """
        return f'{self._base_url}/api/withdraw/kyc-doc'
    
    @property
    def create_customer(self) -> str:
        """
        End-point for user document registration.
        Required headers: Authorization, x-coinflow-auth-user-id
        """
        return f'{self._base_url}/api/customer'
    
    @property
    def checkout_link(self) -> str:
        """
        End-point for creating checkout links.
        Required headers: Authorization, x-coinflow-auth-user-id
        """
        return f'{self._base_url}/api/checkout/link'

    @property
    def get_session_key(self) -> str:
        return f'{self._base_url}/api/auth/session-key'
    
    @property
    def get_totals(self) -> str:
        return f'{self._base_url}/api/checkout/totals/'
    
    @property
    def get_withdrawers(self) -> str:
        return f'{self._base_url}/api/withdraw'


class CoinFlowAPIError(Exception):
    """Custom exception for CoinFlow API errors"""
    
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class CoinFlowClient:
    # Document type mapping
    DOCUMENT_TYPE_MAPPING = {
        DocumentTypeChoise.id_card: 'ID_CARD',
        DocumentTypeChoise.driving_license: 'DRIVERS',
        DocumentTypeChoise.passport: 'PASSPORT'
    }
    
    # File field mapping
    FILE_FIELD_MAPPING = {
        'document_id_front_photo': 'idFront',
        'document_id_back_photo': 'idBack',
    }
    '''
    This a compatibility layer for Acuitytec.
    '''
    
    def __init__(self, config: Optional[CoinFlowConfig] = None): 
        """Initialize CoinFlow client with configuration"""
        if config:
            self.config = config
        else:
            redirection_link = settings.PROJECT_DOMAIN + settings.COINFLOW_REDIRECTION_PATH
            
            self.config = CoinFlowConfig(
                auth_token=settings.COINFLOW_AUTH,
                api_url=settings.COINFLOW_API_URL,
                auth_header=settings.COINFLOW_AUTH_HEADER,
                redirection_url=redirection_link
            )
        
        self.origins = f'[{settings.PROJECT_DOMAIN}]'
        self.endpoints = CoinFlowEndpoints(url=self.config.api_url)
        self._merchant_id = None

    @property
    def merchant_id(self) -> str:
        """Lazy load merchant ID"""
        if self._merchant_id is None:
            self._merchant_id = self._fetch_merchant_id()
        return self._merchant_id

    def _build_headers(self, auth: bool=True,
                    content_json: bool=True,
                    content_type: Optional[str] = None,
                    auth_blockchain: Optional[str]=None,
                    auth_session_key: Optional[str]=None,
                    auth_user_id: Optional[str]=None,
                    auth_wallet: Optional[str]=None,
                    device_id: Optional[str]=None) -> dict:
        '''
        This functions returns the right headers, by default the auth and token
        headers are enabled, this design had in mind the docs given at:
        
        https://docs.coinflow.cash/reference/authentication
        '''
        header = {
            "accept": "application/json",
        }
        if auth:
            header['Authorization'] = self.config.auth_token
        if content_json:
            header['content-type'] = "application/json"
        if content_type:
            header['content-type'] = content_type
        if auth_blockchain:
            header['x-coinflow-auth-blockchain'] = auth_blockchain
        if auth_session_key:
            header['x-coinflow-auth-session-key'] = auth_session_key
        if auth_user_id:
            header['x-coinflow-auth-user-id'] = auth_user_id
        if auth_wallet:
            header['x-coinflow-auth-wallet'] = auth_wallet
        if device_id:
            header['x-device-id'] = device_id
            
        return header

    def _fetch_merchant_id(self) -> str:
        """Fetch merchant ID from CoinFlow API"""
        try:
            response = requests.get(
                self.endpoints.get_merchant, 
                headers=self._build_headers(),
                timeout=self.config.timeout
            )
            response.raise_for_status()
            data = response.json()
            return data['merchantId']
        except requests.RequestException as e:
            logger.error(f"Failed to fetch merchant ID: {e}")
            pass
        except KeyError:
            logger.error("Merchant ID not found in response")
            pass
        
        return 'Area51'

    def _generate_user_id(self, user: Users) -> str:
        """Generate CoinFlow user ID from Django user"""
        return f"{settings.ENV_POSTFIX}-{user.id}"

    def _parse_user_id(self, coinflow_user_id: str) -> Optional[Users]:
        """Parse CoinFlow user ID to get Django user"""
        if not coinflow_user_id.startswith(f"{settings.ENV_POSTFIX}-"):
            return None
                
        try:
            user_pk = int(coinflow_user_id[len(settings.ENV_POSTFIX) + 1:])
            return Users.objects.filter(id=user_pk).first()
        except (ValueError, IndexError):
            logger.warning(f"Invalid user ID format: {coinflow_user_id}")
            return None
    
    def _validate_user_verification(self, user: Users) -> BasicReturn:
        """Validate user verification status"""
        if user.document_verified != VERIFICATION_APPROVED:
            return BasicReturn(
                success=False, 
                error='User verification must be completed before registration.'
            )
        return BasicReturn(success=True)
        
    def _make_api_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make API request with proper error handling"""
        try:
            response = requests.request(
                method=method,
                url=url,
                timeout=self.config.timeout,
                **kwargs
            )
            response.raise_for_status()
            return response
            
        except requests.ConnectionError as e:
            logger.error(f"Network connection error: {e}")
            raise CoinFlowAPIError(f"Network connection error: {e}")
        except requests.Timeout as e:
            logger.error(f"Request timed out: {e}")
            raise CoinFlowAPIError(f"Request timed out: {e}")
        except requests.HTTPError as e:
            error_message = f"HTTP error {response.status_code}" # type: ignore
            try:
                api_error = response.json().get('details', response.text) # type: ignore
                error_message = f"{error_message}: {api_error}"
            except (json.JSONDecodeError, AttributeError):
                error_message = f"{error_message}: {response.text}" # type: ignore
            
            logger.error(f"HTTP error: {error_message}\n{e}")
            raise CoinFlowAPIError(error_message, response.status_code) # type: ignore
        except requests.RequestException as e:
            logger.error(f"Unexpected request error: {e}")
            raise CoinFlowAPIError(f"An unexpected request error occurred: {e}")

    def _get_user_assets(self, user: Users) -> BasicReturn:
        """Get user assets from AcuityTec API"""
        try:
            acuity = AcuityTecAPI(user)
            result = acuity.get_user_assets()
            
            return result
        except Exception as e:
            logger.error(f"Failed to get user assets: {e}")
            return BasicReturn(success=False, error='Failed to retrieve user verification data.')
    
    def register_user_with_document(self, user: Users) -> BasicReturn:
        """
        Register user with document verification to CoinFlow API.
        
        This method handles the complete document verification process including:
        - User verification status validation
        - Document asset retrieval from AcuityTec
        - Document type validation and mapping
        - File preparation and upload
        - API request execution with proper error handling
        
        Args:
            user: Django user instance with completed verification
            
        Returns:
            BasicReturn object with success status and data/error message
        """
        try:
            # Validate user verification status
            validation_result = self._validate_user_verification(user)
            if not validation_result.success:
                return validation_result
            
            # Get user assets from AcuityTec
            res_assets = self._get_user_assets(user)
            from pprint import pformat
            logger.info(pformat(res_assets))
            
            assets = res_assets.data
            if assets is None:
                return res_assets
            
            logger.info(f'User {user.id}-{user.username}: Had obtained his photos.')
            
            # Extract and validate document type
            doc_type = assets.pop('document_type', DocumentTypeChoise.id_card)
            if doc_type is None:
                return BasicReturn(
                    success=False, 
                    error='Document type not found in verification data.'
                )
            
            if doc_type not in self.DOCUMENT_TYPE_MAPPING:
                return BasicReturn(
                    success=False, 
                    error=f'Invalid document type: {doc_type}. Supported types: {list(self.DOCUMENT_TYPE_MAPPING.keys())}'
                )
            
            # Validate required user fields
            if not user.email:
                return BasicReturn(
                    success=False, 
                    error='User email is required for registration.'
                )
            
            # Build request payload
            payload = {
                'country': user.country_obj.code_cca2 if user.country_obj else 'US',
                'email': user.email,
                'idType': self.DOCUMENT_TYPE_MAPPING[doc_type],
                'merchantId': self.merchant_id,
            }
            
            # Build files dictionary for document uploads
            files = {}
            for asset_key, asset_value in assets.items():
                if asset_value[1] is None:
                    continue
                file_key = self.FILE_FIELD_MAPPING.get(asset_key)
                if file_key and asset_value:
                    files[file_key] = asset_value
            
            if not files:
                return BasicReturn(
                    success=False, 
                    error='No valid document files found. If you have completed all verification please contact us.'
                )
                
            logger.info(f'Generated files: {pformat(files)}\nFor user: {user.id}')
            
            # Log the registration attempt
            logger.info(f"Attempting document registration for user {user.id} with document type {doc_type}")
            
            # Make API request
            headers = self._build_headers(
                auth=True,
                content_json=False,
                auth_user_id=self._generate_user_id(user)
            )
            
            response = self._make_api_request(
                method='POST',
                url=self.endpoints.register_user_document,
                headers=headers,
                data=payload,
                files=files
            )
            
            # Parse response data
            try:
                response_data = response.json()
            except json.JSONDecodeError:
                response_data = {"message": "Registration successful"}
            
            logger.info(f"User {user.id} document registration completed successfully")
            return BasicReturn(
                success=True, 
                data=response_data,
                message="Document registration completed successfully"
            )
            
        except CoinFlowAPIError as e:
            if e.status_code == 400 and str() == '':
                # Modify use data.
                return BasicReturn(
                    success=True, 
                    data={ 'message' : 'Registration sucessful'},
                    message="Document registration completed successfully"
                )

            logger.error(f"CoinFlow API error during document registration for user {user.id}: {e}")
            return BasicReturn(success=False, error=str(e))
        except Exception as e:
            logger.error(f"Unexpected error during document registration for user {user.id}: {e}")
            return BasicReturn(
                success=False, 
                error='An unexpected error occurred during registration. Please try again.'
            )

    def register_user(self, user: Users, ssn: str) -> BasicReturn:
        if user.document_verified != VERIFICATION_APPROVED:
            return BasicReturn(success=False, error='User must be registered on Acuitytec.')
        
        if user.dob:
            year, month, day = user.dob.split('-')
            formatted_date_str = f"{year}{month}{day}"
        else:
            formatted_date_str = ''
        
        payload = {
            "email": user.email,
            "firstName": user.first_name,
            "surName": user.last_name,
            "physicalAddress": user.complete_address,
            "city": user.city,
            "state": user.state,
            "ssn": ssn,
            "dob": formatted_date_str,
            "country": user.country_obj.code_cca2 if user.country_obj else 'US',
            "zip": str(user.zip_code)
        }
        
        for k, v in payload.items():
            if v is None:
                return BasicReturn(success=False, error='Please complete your profile before taking any extra steps.')
            
            if len(str(v)) < 2:
                return BasicReturn(success=False, error=f'Please complete your profile {k} before taking any extra steps.')

        try:
            res = self._make_api_request(
                'POST',
                self.endpoints.register_user_attested,
                json=payload,
                headers=self._build_headers(auth_user_id=self._generate_user_id(user=user))
                )
            logger.info(res.text)
        except CoinFlowAPIError as e:
            pass
        
        return BasicReturn(success=True)
    
    def create_customer(self, user: Users, ip: str) -> BasicReturn:
        
        if user.dob:
            year, month, day = user.dob.split('-')
            formatted_date_str = f"{year}-{month}-{day}"
        else:
            formatted_date_str = ''
        
        customer_info = {
            "address": user.complete_address,
            "city": user.city,
            "state": user.state,
            "zip": user.zip_code,
            "country": user.country_obj.code_cca2 if user.country_obj else 'US',
            "ip" : ip,
            "firstName": user.first_name,
            "surName": user.last_name,
        }
        
        for k, v in customer_info.items():
            if v is None:
                return BasicReturn(success=False, error='Please complete your profile before taking any extra steps.')
            
            if len(str(v)) < 1:
                return BasicReturn(success=False, error='Please complete your profile before taking any extra steps.')

        payload = {
            "customerInfo" : customer_info,
            "email": user.email,
        }
        
        res = self._make_api_request(
            'POST',
            self.endpoints.create_customer,
            json=payload,
            headers=self._build_headers(auth_user_id=self._generate_user_id(user=user))
        )
        
        return BasicReturn(success=True)
    
    def get_session_auth(self, user: Users) -> BasicReturn:
        key = sha256(f'coinflow-session-key:{user.id}'.encode()).hexdigest()
        session_cache = redis_client.get(key)
        if not session_cache is None:
            logger.debug(f'coinflow-session-key:{user.id} - cache hit for session')
            return BasicReturn(success=True, data=session_cache)
        
        
        try:
            response = self._make_api_request(
                'GET',
                url=self.endpoints.get_session_key,
                headers=self._build_headers(auth_user_id=self._generate_user_id(user=user))
            )
            
            data = response.json()
            logger.debug(f'coinflow-session-key:{user.id} - session created')
            session_key = data.get('key')
            # 12h * 60m * 60s = 43_200
            redis_client.set(key, session_key, ex=43200)
            return BasicReturn(success=True, data=session_key)
        
        except json.JSONDecodeError as e:
            logger.critical(f'JSON error: >> this data cannot be parsed: {e}')
            return BasicReturn(success=False, error='This service is down, please try again later')
        except CoinFlowAPIError as e:
            logger.critical(f'HTTP error: >> cannot get session key: {e}')
            return BasicReturn(success=False, error='This service is down, please try again later')
    
    def create_checkout_link(self, 
                           user: Users,
                           amount_cents: int,
                           threeds_preference: str = 'Frictionless',
                           item_class: str = 'moneyTopUp',
                           item_id: Optional[str] = None,
                           item_name: str = 'Sweeptokens',
                           is_preset_amount: bool = False) -> BasicReturn:
        """
        Create a checkout link for user payment processing.
        
        This method handles the complete checkout link creation process including:
        - User profile validation
        - Parameter validation
        - Payload construction
        - API request execution with proper error handling
        
        Args:
            user: Django user instance
            amount_cents: Amount in cents (e.g., 500 for $5.00)
            blockchain: Blockchain to use (default: 'eth')
            currency: Currency code (default: 'USD')
            threeds_preference: 3DS challenge preference (default: 'Frictionless')
            item_class: Item class for chargeback protection (default: 'moneyTopUp')
            item_id: Unique item identifier (optional, auto-generated if not provided)
            item_name: Item name for display (default: 'Sweeptokens')
            webhook_url: Webhook URL for callbacks (optional)
            is_preset_amount: Whether the amount is preset (default: False)
            
        Returns:
            BasicReturn object with success status and checkout link data/error message
        """
        try:
            # Validate user profile
            profile_validation = self._validate_user_verification(user)
            if not profile_validation.success:
                return profile_validation
            
            # Generate item ID if not provided
            if item_id is None:
                item_id = f"checkout-{user.id}-{uuid4()}"
                
            process_id = f'{uuid4()}'
            # # Build webhook info
            # webhook_info = {}
            # if webhook_url:
            #     webhook_info['url'] = webhook_url
            # else:
            #     # Use default webhook URL from settings if available
            #     default_webhook = getattr(settings, 'COINFLOW_WEBHOOK_URL', None)
            #     if default_webhook:
            #         webhook_info['url'] = default_webhook
            
            # Construct checkout payload
            payload = {
                "subtotal": {
                    "currency": 'USD',
                    "cents": amount_cents
                },
                "email": user.email,
                # "origins" : self.origins,
                "webhookInfo": {'transaction_id' : process_id},
                "blockchain": 'eth',
                "threeDsChallengePreference": threeds_preference,
                "customerInfo": {
                    "firstName": user.first_name,
                    "lastName": user.last_name
                },
                "chargebackProtectionData": [
                    {
                        "itemClass": item_class,
                        "id": item_id,
                        "rawProductData": {
                            "Name": item_name
                        },
                        "sellingPrice": {
                            "valueInCurrency": amount_cents,
                            "currency": 'USD'
                        },
                        "quantity": 1,
                        "topUpAmount": {
                            "valueInCurrency": amount_cents,
                            "currency": 'USD'
                        },
                        "isPresetAmount": False
                    }
                ]
            }
            
            # Log the checkout attempt
            logger.info(f"Creating checkout link for user {user.id}, amount: {amount_cents} cents")
            
            # Make API request
            headers = self._build_headers(
                auth=True,
                content_json=True,
                auth_user_id=self._generate_user_id(user)
            )
            
            response = self._make_api_request(
                method='POST',
                url=self.endpoints.checkout_link,
                headers=headers,
                json=payload
            )
            
            # Parse response data
            try:
                response_data = response.json()
            except json.JSONDecodeError:
                return BasicReturn(
                    success=False,
                    error='Invalid response format from checkout API.'
                )
            
            # Validate response contains expected data
            if 'link' not in response_data:
                return BasicReturn(
                    success=False,
                    error='Checkout URL not found in API response.'
                )
            
            logger.info(f"Checkout link created successfully for user {user.id}")
            return BasicReturn(
                success=True,
                data={**response_data, 'id' : process_id},
                message="Checkout link created successfully"
            )
            
        except CoinFlowAPIError as e:
            logger.error(f"CoinFlow API error during checkout link creation for user {user.id}: {e}")
            return BasicReturn(success=False, error=str(e))
        except Exception as e:
            logger.error(f"Unexpected error during checkout link creation for user {user.id}: {e}")
            return BasicReturn(
                success=False,
                error='An unexpected error occurred during checkout link creation. Please try again.'
            )

    def create_bank_registration_link(self, user: Users) -> BasicReturn:

        key_data = self.get_session_auth(user=user)
        if key_data.error:
            return key_data
        
        url = quote(self.config.redirection_url, safe="")
        data = f'https://sandbox.coinflow.cash/solana/withdraw/{self.merchant_id}?sessionKey={key_data.data}&bankAccountLinkRedirect={url}'
        return BasicReturn(success=True, data=data)
    
    def get_totals(self, user: Users, cents: int) -> BasicReturn:
        
        data = self.get_session_auth(user)
        if data.error:
            return data
        
        try:
            payload = {
                'subtotal' : {
                    "currency": "USD",
                    "cents": cents
                }
            }
            res = self._make_api_request(
                method='POST',
                url=self.endpoints.get_totals + self.merchant_id,
                headers=self._build_headers(auth=False, auth_session_key=data.data),
                json=payload
            )
            print(res.text)
            res = res.json()
        except CoinFlowAPIError as e:
            logger.critical(f'Error: >> could not create totals: {e}')
            return BasicReturn(success=False, error='Could not generate an estimation total right now. Please try again later.')

        totals = {}
        
        for method in ["card", "ach"]:
            if method not in res:
                continue
            entry = res[method]
            totals[method] = {
                "subtotal": round(entry["subtotal"]["cents"] / 100, 2),
                "creditCardFees": round(entry["creditCardFees"]["cents"] / 100, 2),
                "chargebackProtectionFees": round(entry["chargebackProtectionFees"]["cents"] / 100, 2),
                "gasFees": round(entry["gasFees"]["cents"] / 100, 2),
                "total": round(entry["total"]["cents"] / 100, 2)
            }
            
            totals['bonus'] = cents *  50
        
        return BasicReturn(success=True, data=totals)
    
    def get_cards_banks(self, user: Users) -> BasicReturn:
        try:
            data = self._make_api_request(
                method='GET',
                url=self.endpoints.get_withdrawers,
                headers=self._build_headers(auth_user_id=self._generate_user_id(user))
            ).json()
        except CoinFlowAPIError as e:
            return BasicReturn(success=False, error='Withdraws are not available right now. Please try again later.')
        
        withdrawer = data.get("withdrawer", {})

        TTL_SECONDS = 1800

        result = {
            "cards": [],
            "bankAccounts": []
        }

        # Process cards
        for card in withdrawer.get("cards", []):
            card_id = str(uuid4())
            redis_client.setex(f"card:{card_id}", TTL_SECONDS, json.dumps(card))
            result["cards"].append({
                "cardId": card_id,
                "type": card.get("type"),
                "last4": card.get("last4"),
                "disbursementStatus": card.get("disbursementStatus"),
                "createdAt": card.get("createdAt")
            })

        # Process bank accounts
        for bank in withdrawer.get("bankAccounts", []):
            bank_id = str(uuid4())
            redis_client.setex(f"bank:{bank_id}", TTL_SECONDS, json.dumps(bank))
            result["bankAccounts"].append({
                "bankId": bank_id,
                "alias": bank.get("alias"),
                "last4": bank.get("last4"),
                "rtpEligible": bank.get("rtpEligible")
            })
        
        
        return BasicReturn(success=True, data=result)

    def handle_purchases(self, data) -> BasicReturn:
        
        # Check if all the variables needed exist
        l_data = data.get('data', None)
        if l_data is None:
            return BasicReturn(success=False, error='The data is none')
        eventType = data.get('eventType', None)
        if eventType is None:
            return BasicReturn(success=False, error='The data.eventype is none')
        eventType = str(eventType)
        tid = l_data.get('webhookInfo', {}).get('transaction_id')
        if tid is None:
            logger.critical('The webhook is not retorning the transacction id, no webhook handling can be done')
            return BasicReturn(success=False, error='transacction if is not returned on the webhook')
        transaction_qs = Transactions.objects.filter(txn_id=tid).order_by('-created')
        if not transaction_qs.exists():
            return BasicReturn(success=False, error='transacction was not registered')
        money = l_data.get('subtotal', {}).get('cents')
        if money is None:
            return BasicReturn(success=False, error='Money is none')
        cid = l_data.get('customerId')
        if cid is None:
            return BasicReturn(success=False, error='User id was not found on the webhook')
        user = self._parse_user_id(cid)
        if user is None:
            return BasicReturn(success=False, error='User does not exist. Or does not belong to this game instance.')
        
        
        if eventType in {"Settled", "Card Payment Authorized", "USDC Payment Received", "ACH Batched"}:
            # Settled: Payment completed and funds have been sent to the merchant.
            # CPA: Card issuer authorized the payer's credit card.
            # UPR: Merchant received USDC payment via Solana.
            # AB : The ACH has been accepted and it is processing.
            transaction = transaction_qs.filter(status='pending_charge').first()
            if not transaction:
                return BasicReturn(success=False, error='Deduplication this transaction was already claimed')
            transaction.status='charged'
            transaction.amount=Decimal(money/100)
            transaction.previous_balance=user.balance
            transaction.description = eventType
            old_balance = user.balance
            new_balance = old_balance + Decimal(money)/100
            transaction.new_balance = new_balance
            user.balance = new_balance
            user.save()
            transaction.save()
        elif eventType in {"Card Payment Declined", "Card Payment Suspected Fraud", "ACH Failed", "ACH Returned", "PIX Failed"}:
            # Card issuer declined the payer's credit card.
            # Payment rejected due to suspected fraud.
            # PIX payment failed during processing.
            transaction = transaction_qs.filter(status='pending_charge').first()
            if not transaction:
                return BasicReturn(success=False, error='Deduplication this transaction was already claimed')
            # Card issuer authorized the payer's credit card.
            status = 'failed_reject' if eventType in {"Card Payment Suspected Fraud", "ACH Failed"} else 'failed_charge'
            transaction.status=status
            transaction.amount=Decimal(money/100)
            transaction.previous_balance=user.balance
            transaction.new_balance = user.balance
            transaction.save()
        elif eventType == "Payment Pending Review":
            # Payment under review, awaiting merchant approval.
            transaction = transaction_qs.filter(status='pending_charge').first()
            if transaction is None:
                return BasicReturn(success=False, error='The transaction is not on the expected state')
            transaction.confirms_needed = 1
            transaction.save()
        elif eventType == "Card Payment Chargeback Opened":
            # Chargeback investigation initiated.
            pass
        elif eventType == "Card Payment Chargeback Lost":
            # Chargeback resolved in favor of cardholder.
            pass
        elif eventType == "Refund":
            # Payment has been refunded.
            pass
        elif eventType == "Card Payment Chargeback Won":
            # Chargeback resolved in favor of merchant.
            pass
        elif eventType == "ACH Initiated":
            # ACH payment has been started.
            pass
        elif eventType in ["PIX Expiration", "Payment Expiration"]:
            # PIX payment expired before completion.
            # Payment expired before completion.
            pass
        else:
            # Unknown eventType.
            pass
        return BasicReturn(success=False, error='This function is not fully implemented')

    def handle_webhook(self, data, authorization: str) -> BasicReturn:
        
        if authorization is None or authorization != self.config.auth_header:
            return BasicReturn(success=False, error='Auth header does not match.')
        
        web_hook_options: Dict[str, Callable[..., BasicReturn]] = {
            'KYC' : lambda: BasicReturn(success=True),
            'Purchase' : lambda: self.handle_purchases(data=data),
            'Withdraw' : lambda: BasicReturn(success=True),
        }
        
        k = data.get('category', 'Purchase')
        
        return web_hook_options[k]()