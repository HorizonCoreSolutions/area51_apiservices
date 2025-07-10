"""
AcuityTec Customer Registration API Client
Simple Python implementation for customer registration verification
"""
import time
import json
import base64
from uuid import uuid4
import requests
from io import BytesIO
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, Union
from apps.acuitytec.models import AcuitytecUser, VerificationStateChoise, VerificationItem
from apps.core.custom_types import BasicReturn
from apps.users.models import VERIFICATION_APPROVED, VERIFICATION_PENDING, VERIFICATION_PROCESSING, Users
from django.conf import settings
from django.utils import timezone
from urllib.parse import urlparse


class AcuityTecAPI:
    """
    AcuityTec API Client for Customer Registration
    """
    
    def __init__(self, user: Users):
        """
        Initialize the AcuityTec API client
        
        Args:
            base_url: The base URL for the AcuityTec API
            merchant_id: Merchant account ID provided by AcuityTec
            password: Merchant password provided by AcuityTec
        """
        self.site = urlparse(settings.DOMAIN_URL).hostname
        self.base_url = settings.ACUITYTEC_API.rstrip('/')
        self.user = user
        
        self.merchant_id = settings.ACUITYTEC_MERCHANT_ID
        self.password = settings.ACUITYTEC_PASSWORD
        
        print(self.merchant_id)
        print(self.password)
        
        self.enpoints = {
            "register_user" : f"{self.base_url}/customerregistration",
            "photo_id" : f"{self.base_url}/photoIdOnlineVerification",
            "get_assets" : f"{self.base_url}/photoIdOnlineVerification/assets",
            }
        if user is None:
            raise ValueError('User must not be None')
    
    def register_customer(self,
                         reg_ip_address: str,
                         **optional_params) -> Dict[str, Any]:
        """
        Register a customer and get risk assessment
        
        Args:
            user_name: Username (required)
            user_number: Unique identifier at merchant's website (required)
            reg_date: Registration date in YYYY-MM-DD format (required)
            reg_ip_address: Registration IP address (required)
            customer_info: Dictionary containing customer information (required)
            **optional_params: Optional parameters like reg_device_id, source, etc.
        
        Returns:
            Dictionary containing the API response
        """
        customer_info = self.create_customer_info()
        
        # Build the request payload
        payload = {
            # Credentials
            'merchant_id': self.merchant_id,
            'password': self.password,
            
            # Required fields
            'user_name': self.user.username,
            'user_number':  '-'.join([
                                settings.ENV_POSTFIX,
                                str(self.user.id),
                            ]),
            'reg_date': self.user.created.strftime("%Y-%m-%d"),
            'reg_ip_address': reg_ip_address,
            'site_skin_name' : self.site,
            'affiliate_id' : 'cr',
        }
        
        # Add customer information with proper tags
        for key, value in customer_info.items():
            payload[f'customer_information[{key}]'] = value
        
        # Add optional parameters
        optional_fields = [
            'reg_device_id', 'device_fingerprint', 'source', 'bonus_code',
            'bonus_submission_date', 'bonus_amount',
            'how_did_you_hear'
        ]
        
        for field in optional_fields:
            if field in optional_params:
                payload[field] = optional_params[field]
        
        # Set default device ID if not provided
        if 'reg_device_id' not in payload:
            payload['reg_device_id'] = '00:00:00:00:00:00'
        
        # Set default device fingerprint if not provided
        if 'device_fingerprint' not in payload:
            payload['device_fingerprint'] = 'N/A'
        
        try:
            # Make the POST request
            payload = {k: v for k, v in payload.items() if v is not None}

            response = requests.post(self.enpoints['register_user'], data=payload, timeout=30)
            response.raise_for_status()
            
            # Parse JSON response# Parse JSON response
            data = response.json()
            
            if data.get('status', -1) != 0:
                return {
                    'error' : True,
                    "message": "This service is down, Please try again in a few minuts.",
                    "status": -1
                }

            return {
                'error' : False,
                "message": "OK",
                "status": 0
            }
            
        except requests.exceptions.RequestException as e:
            return {
                'error': True,
                'message': f'Request failed: {str(e)}',
                'status': -2
            }
        except json.JSONDecodeError as e:
            return {
                'error': True,
                'message': f'Invalid JSON response: {str(e)}',
                'status': -3
            }

    def create_customer_info(self, **optional_info) -> Dict[str, Any]:
        """
        Helper function to create customer information dictionary
        
        Args:
            first_name: Customer's first name (required)
            last_name: Customer's last name (required)
            email: Customer's email address (required)
            **optional_info: Optional customer information
        
        Returns:
            Dictionary with customer information
        """
        customer_info = {
            'first_name': self.user.first_name,
            'last_name': self.user.last_name,
            'email': self.user.email,
            'country' : self.user.country_obj.code_cca2 if self.user.country_obj else None,
            'dob' : self.user.dob,
            'province' : self.user.state,
            'city' : self.user.city,
            'address1' : self.user.complete_address,
            'postal_code' : self.user.zip_code,
            'phone1' : self.user.phone_number
        }
        
        
        
        # Add optional fields if provided
        optional_fields = [
            'address2', 'city', 'province', 'postal_code',
            'country', 'phone1', 'phone2', 'dob', 'id_type',
            'id_value', 'gender', 'marital_status'
        ]
        
        for field in optional_fields:
            if field in optional_info:
                customer_info[field] = optional_info[field]
        
        return customer_info

    def getLink(self, document, language):
        try:
            qs = VerificationItem.objects.filter(
                user=self.user,
                status=VerificationStateChoise.pending,
                created__gte=timezone.now() - timedelta(hours=24)
                )
            
            if qs.exists():
                vi = qs.first()
                if not vi is None and vi.url:
                    return vi.url

            data = {
                "merchant_id": self.merchant_id,
                "password": self.password,
                "reference": document,
                "usernumber":  '-'.join([
                                    settings.ENV_POSTFIX,
                                    str(self.user.id),
                                ]),
                "email": self.user.email,
                "country": self.user.country_obj.code_cca2 if self.user.country_obj else None,
                "language": language,
                "selected_service": "face"
            }

            print(data)
            response = requests.post(self.enpoints['photo_id'], data=data, timeout=30)

            if response.status_code == 200:
                result = response.json()
                if result.get("status") == 0:
                    reference_id: str = str(result["reference_id"]).strip()
                    print("Verification initiated successfully.")
                    print("Reference ID:", reference_id)
                    print("Verification URL:", result["verification_source"])
                    
                    VerificationItem.objects.create(
                        user=self.user,
                        url=result['verification_source'],
                        reference_id=reference_id,
                    )
                    self.user.document_verified = VERIFICATION_PROCESSING
                    self.user.save()
                    
                    return result['verification_source']
                else:
                    print("API responded with error:", result.get("description"))
                    return 'error' + result.get("description")
            else:
                print("HTTP error:", response.status_code)
                return 'error' + str(response.status_code)
        except Exception as e:
            print(e)
            return 'error' + 'Something wrong has happend'

    def get_user_assets(self) -> BasicReturn:
        if self.user.document_verified != VERIFICATION_APPROVED:
            return BasicReturn(success=False, error=f"The verification state on the user profile is {self.user.document_verified}")
        
        vi = VerificationItem.objects.filter(
            user=self.user,
            status=VerificationStateChoise.accepted
            ).order_by('-created').first()
        
        if vi is None or vi.reference_id is None:
            return BasicReturn(success=False, error=f"There is no VerificationItem even when user is document_verified")
        
        payload = {
            'merchant_id' : self.merchant_id,
            'password' : self.password,
            'reference' : vi.reference_id
        }
        
        mime = 'image/jpeg'
        
        res = requests.post(self.enpoints['get_assets'], data=payload)
        
        res_data = {
            'document_type' : vi.document_type
        }
        
        try:
            res.raise_for_status()
            data = res.json()
            docs = data.get('documents')
            if docs is None:
                return BasicReturn(success=False, error=f"Acuitytec has no documents for reference id: {vi.reference_id}")
        
            
            for k in docs.keys():
                if k not in ['document_id_front_photo', 'document_id_back_photo']:
                    continue
                name = f'{k}.jpeg'
                file_img = BytesIO(base64.b64decode(docs.get(k)))
                file_img.seek(0)
                res_data[k] =  (name, file_img, mime)
                
            return BasicReturn(success=True, data=res_data)
        except Exception as e:
            trace_back = uuid4()
            print(f'TracebackID: {trace_back}\n{e}')
            return BasicReturn(success=False, error=f"Unspected error traceback id: {trace_back}")

    @staticmethod
    def parse_user_to_geo(user: Users, ip: str):
        
        def sync_names(first_name=None, last_name=None, full_name=None):
            # Normalize empty strings to None
            first_name = first_name or None
            last_name = last_name or None
            full_name = full_name or None

            # Case 1: full_name exists and others do not
            if full_name and not first_name and not last_name:
                names = full_name.strip().split(None, 1)
                first_name = names[0]
                last_name = names[1] if len(names) > 1 else ''
            
            # Case 2: first_name or last_name exists but full_name does not
            elif (first_name or last_name) and not full_name:
                full_name = f"{first_name or ''} {last_name or ''}".strip()
            
            # Case 3: all are present or some conflict; prefer full_name
            elif full_name:
                names = full_name.strip().split(None, 1)
                first_name = names[0]
                last_name = names[1] if len(names) > 1 else ''

            # Create names tuple
            names = (first_name or '', last_name or '')
            return names, full_name
        
        names, full_name = sync_names(user.first_name, user.last_name, user.full_name)
        
        return {
            'first_name' : names[0],
            'last_name' : names[1],
            'user_name' : user.username,
            'email' : user.email,
            'city' : user.city,
            'id' : str(user.id),
            'cca2' : user.country_obj.code_cca2 if user.country_obj else user.country,
            'ip' : ip
        }
        
    @staticmethod
    def is_geo_verified(first_name: str, last_name: str, user_name: str, email: str, city: str, id: str, cca2: str, ip: str) -> Dict[str, Union[str, int]]:
        
        endpoint = f"{settings.ACUITYTEC_API.rstrip('/')}/customerregistration"
        
        merchant_id = settings.ACUITYTEC_MERCHANT_ID
        password = settings.ACUITYTEC_PASSWORD
        
        customer_info = {
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'country' : cca2,
            'city' : city,
        }
        
        # Build the request payload
        payload = {
            # Credentials
            'merchant_id': merchant_id,
            'password': password,
            
            # Required fields
            'user_name': user_name,
            'user_number':  '-'.join([
                                settings.ENV_POSTFIX,
                                str(id),
                            ]),
            'reg_date': timezone.now().strftime("%Y-%m-%d"),
            'reg_ip_address': ip,
            'site_skin_name' : urlparse(settings.DOMAIN_URL).hostname,
            'affiliate_id' : 'lg',
        }
        
        # Add customer information with proper tags
        for key, value in customer_info.items():
            payload[f'customer_information[{key}]'] = value
        
        # Set default device ID if not provided
        if 'reg_device_id' not in payload:
            payload['reg_device_id'] = '00:00:00:00:00:00'
        
        # Set default device fingerprint if not provided
        if 'device_fingerprint' not in payload:
            payload['device_fingerprint'] = 'N/A'
        
        try:
            payload = {k: v for k, v in payload.items() if v is not None}

            response = requests.post(endpoint, data=payload, timeout=30)
            try:
                response.raise_for_status()
            except:
                return {
                    'error' : True,
                    'message' : "The Geo service is down, please try again in a few hours.",
                    'status' : -2
                }
                
            
            # Parse JSON response# Parse JSON response
            data = response.json()

            try:
                risk = float(data.get('score', 0.0))
            except (ValueError, TypeError):
                risk = 0.0
                
            rules: Optional[list[Dict[str, str]]] = data.get('rules_triggered')
        
            if data is None or rules is None:
                return {
                    "error" : True,
                    "message" : "The Geo Verification service is not available.",
                    "status" : -2
                }
            
            checks = [
                (
                    (
                        'Blocked Geo IP State',
                        'Blocked Profile State',
                    ),
                    "You cannot use this site. The state you are in is not available.",
                ),
                (
                    (
                        'Geo - Anonymous Proxy Usage',
                        'Geo - Public Proxy Usage Detected',
                    ),
                    "Please disable the proxy to continue playing.",
                ),
                (
                    (
                        'Geo - Anonymous VPN Usage',
                        'Geo - IP City Mismatch',
                        'Geo - IP Country Mismatch',
                        'Geo - IP User Type - Hosting',
                        'Geo - IP User Type - Government',
                        'Geo - IP User Type - Content Delivery Network',
                        'Geo - VPN Provider Usage Detected',
                    ),
                    "Please disable the VPN to continue playing.",
                ),
                (
                    (
                        'Geo - IP User Type - Search Engine Spider',
                        # 'Geo - Suspicious Network Usage',
                    ),
                    "Please disable the VPN to continue playing.|",
                ),
                (
                    (
                        'Geo IP is not US',
                    ),
                    "Only US players can access our platform.",
                )
            ]

            for rule in rules:
                name = rule.get('name', '')
                for prefixes, message in checks:
                    if name.startswith(prefixes):
                        return {
                            "error" : False,
                            "message": message,
                            "status": -1
                        }
                
            if risk > 90:
                return {
                        "error" : False,
                        "message": 'Login has been categorized as risky',
                        "status": -1
                    }

            return {
                'error' : False,
                "message": "OK",
                "status": 0
            }
            
        except requests.exceptions.RequestException as e:
            return {
                'error': True,
                'message': f'Request failed: {str(e)}',
                'status': -2
            }
        except json.JSONDecodeError as e:
            return {
                'error': True,
                'message': f'Invalid JSON response: {str(e)}',
                'status': -3
            }
    
    @staticmethod
    def get_ip_from_request(request) -> str:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')

        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()  # client’s real IP
            data = x_forwarded_for
        else:
            ip = request.META.get('REMOTE_ADDR')
            data = [ip]
        
        file = "acuitytec_request_log.txt"
        ts = str(time.time())
        from pprint import pformat
        data = pformat(data)

        entry = (
            f"\n--- {ts} ---\n"
            f"URL: USER IP \n"
            f"DATA:\n{data}\n"
        )

        with open(file, 'a') as f:
            f.write(entry)
            
        return ip
    
    @staticmethod
    def format_response(
        message: str,
        extra_message: str,
        status: int,
        expiration: Optional[int]
    ):
        return {
            'message' : message,
            'status' : status,
            'expiration' : expiration
        }
    
    @staticmethod
    def save_request(request, is_response=False):
        file = "acuitytec_request_log.txt"
        ts = str(time.time())
        full_url = request.build_absolute_uri() if not is_response else "response:"
        from pprint import pformat
        data = pformat(request.data) if not is_response else pformat(request)

        entry = (
            f"\n--- {ts} ---\n"
            f"URL: {full_url}\n"
            f"DATA:\n{data}\n"
        )

        with open(file, 'a') as f:
            f.write(entry)


# Example usage
if __name__ == "__main__":
    
    user = Users.objects.filter(username='test').first()
    
    if user is not None:
        
        # Initialize API client
        api_client = AcuityTecAPI(user)
        
        # Create customer information
        result = api_client.register_customer(reg_ip_address='139.2.4.5')