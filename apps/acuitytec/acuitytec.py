"""
AcuityTec Customer Registration API Client
Simple Python implementation for customer registration verification
"""
import time
import json
import random
import string
import base64
import requests
from io import BytesIO
from uuid import uuid4
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from urllib.parse import urlparse
from apps.acuitytec.logger import logger
from apps.core.concurrency import limiter
from typing import Dict, Any, Optional, Union
from apps.acuitytec.utils import cache_ips_geo
from apps.core.custom_types import BasicReturn
from apps.acuitytec.models import VerificationStateChoise, VerificationItem
from apps.users.models import (
        VERIFICATION_APPROVED,
        # VERIFICATION_PENDING,
        VERIFICATION_PROCESSING,
        Users)


def generate_code(length=4):
    characters = string.ascii_letters + string.digits  # a-zA-Z0-9
    return ''.join(random.choices(characters, k=length))


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

        logger.info(f"init_success user_id={user.id} username={user.username}")

        self.enpoints = {
            "register_user": f"{self.base_url}/customerregistration",
            "photo_id": f"{self.base_url}/photoIdOnlineVerification",
            "get_assets": f"{self.base_url}/photoIdOnlineVerification/assets",
            }
        if user is None:
            logger.error("init_failed reason=missing_user")
            raise ValueError('User must not be None')

    @staticmethod
    def get_headers():
        return {"User-Agent": "AcuityTec-API/1.0 (rv:202509)"}

    def register_customer(self,
                          reg_ip_address: str,
                          check_info: bool = False,
                          **optional_params) -> Dict[str, Any]:
        """
        Register a customer and get risk assessment

        Args:
            (*) : required
            user_name: Username (*)
            user_number: Unique identifier at merchant's website (*)
            reg_date: Registration date in YYYY-MM-DD format (*)
            reg_ip_address: Registration IP address (*)
            customer_info: Dictionary containing customer information (*)
            **optional_params: Optional params like reg_device_id or source.

        Returns:
            Dictionary containing the API response
            error: API/USER error
            message: The message to be diplayed
            status: enum
              - 0 : OK
              - -1: Should retry
              - -2: External Error
              - -3: Unkown error
              - -4: Retry after delay
        """
        start_time = time.time()
        logger.info(("register_customer_start "
                     f"user_id={self.user.id} ip={reg_ip_address}"))

        customer_info = self.create_customer_info()
        if check_info:
            error = self.validate_customer_info(customer_info=customer_info)
            if error:
                return error

        is_allowed = limiter.allow(
                key=f"user:{self.user.id}:register_customer",
                limit=5,  # 2 request / (window)
                window=15,  # 5 seconds
                sliding=True
                )

        if not is_allowed:
            logger.warning(f"User {self.user.id}-{self.user.username}"
                           "has reached register_customer r/s limit.")
            return {
                    'error': True,
                    "message": ("Please wait a few seconds. "
                                "Request limit reached"),
                    "status": -4
                }

        # Build the request payload
        payload = {
            # Credentials
            'merchant_id': self.merchant_id,
            'password': self.password,

            # Required fields
            'user_name': self.user.username,
            "user_number": f"{settings.ENV_POSTFIX}-{self.user.id}",
            'reg_date': self.user.created.strftime("%Y-%m-%d"),
            'reg_ip_address': reg_ip_address,
            'site_skin_name': self.site,
            'affiliate_id': 'cr',
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

            response = requests.post(
                self.enpoints['register_user'],
                headers=AcuityTecAPI.get_headers(),
                data=payload,
                timeout=30)
            response.raise_for_status()

            # Parse JSON response# Parse JSON response
            data = response.json()
            duration = round(time.time() - start_time, 3)

            if data.get('status', -1) != 0:
                logger.error(f"register_customer_fail "
                             f"user_id={self.user.id} "
                             f"status={data.get('status')} "
                             f"duration={duration}")
                return {
                    'error': True,
                    "message": ("This service is down, "
                                "Please try again in a few minuts."),
                    "status": -4
                }

            logger.info(f"register_customer_success user_id={self.user.id} "
                        f"duration={duration}")
            return {
                'error': False,
                "message": "OK",
                "status": 0
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"register_customer_http_error user_id={self.user.id}"
                         f" error={str(e)}")
            return {
                'error': True,
                'message': f'Request failed: {str(e)}',
                'status': -2
            }
        except json.JSONDecodeError as e:
            logger.error(f"register_customer_json_error user_id={self.user.id}"
                         f" error={str(e)}")
            return {
                'error': True,
                'message': f'Invalid JSON response: {str(e)}',
                'status': -2
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
            'country': self.user.country_obj.code_cca2 if self.user.country_obj else None,
            'dob': self.user.dob,
            'province': self.user.state,
            'city': self.user.city,
            'address1': self.user.complete_address,
            'postal_code': self.user.zip_code,
            'phone1': (self.user.country_code if self.user.country_code else '') + str(self.user.phone_number if self.user.phone_number else '')
        }

        # Add optional fields if provided
        optional_fields = [
            'address2', 'city', 'province', 'postal_code',
            'country', 'phone1', 'phone2', 'dob', 'id_type',
            'id_value', 'gender', 'marital_status'
        ]

        if customer_info['phone1'] == '' or len(customer_info['phone1']) < 4:
            del customer_info['phone1']

        for field in optional_fields:
            if field in optional_info:
                customer_info[field] = optional_info[field]

        return customer_info

    def validate_customer_info(self,
                               customer_info: dict) -> Optional[dict]:
        for k, v in customer_info.items():
            if v is None:
                logger.warning(
                    f"profile_incomplete user_id={self.user.id} field={k}"
                )
                return {
                    "error": True,
                    "message": (
                        "Please complete your profile "
                        f"({self.normalize(k)}) before taking any extra steps."
                    ),
                    "status": -4,
                }

            if len(str(v)) < 2:
                logger.warning(
                    f"profile_invalid user_id={self.user.id} "
                    f"field={k} value={v}"
                )
                return {
                    "error": True,
                    "message": (
                        "Please complete your profile "
                        f"{self.normalize(k)} before taking any extra steps."
                    ),
                    "status": -4,
                }
        return None

    def normalize(self, k: str):
        {
            'province': 'state',
            'address1': 'complete_address',
            'postal_code': 'zip_code',
            'phone1': 'phone_number',
        }.get(k, k).replace('_', ' ')

    def getLink(self, language):
        document = ("0000" + str(self.user.id))[6:] + generate_code(length=8)

        try:
            logger.info(f"user:{self.user.id} started a get_link action")
            qs = VerificationItem.objects.filter(
                user=self.user,
                status=VerificationStateChoise.pending,
                created__gte=timezone.now() - timedelta(hours=24)
                )

            if qs.exists():
                vi = qs.first()
                if vi is not None and vi.url:
                    logger.debug(f"getLink used cache: user:{self.user.id}")
                    return vi.url

            is_allowed = limiter.allow(
                    key=f"user:{self.user.id}:ac:get_link",
                    sliding=True,
                    window=3600,
                    limit=5,
                    )
            if not is_allowed:
                logger.warning(f"user:{self.user.id} excided their request "
                               "rate for get_link")
                return "error" + "Request Rate excided"

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
            response = requests.post(
                self.enpoints['photo_id'],
                headers=AcuityTecAPI.get_headers(),
                timeout=30,
                data=data)

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

                    logger.info(f"user:{self.user.id} has "
                                "succesfully generated a link")

                    return result['verification_source']
                else:
                    logger.critical("API responded with error:"
                                    f"{result.get('description')}")
                    return 'error' + result.get("description")
            else:
                logger.warning(f"HTTP error: {response.status_code}")
                return 'error' + str(response.status_code)
        except Exception as e:
            logger.warning(f"{type(e).__name__} on User:{self.user.id}")
            print(e)
            return 'error' + 'Something wrong has happend'

    def get_user_assets(self) -> BasicReturn:
        if self.user.document_verified != VERIFICATION_APPROVED:
            return BasicReturn(
                    success=False,
                    error=("The verification state on the user "
                           f"profile is {self.user.document_verified}"))

        vi = VerificationItem.objects.filter(
            user=self.user,
            status=VerificationStateChoise.accepted
            ).order_by('-created').first()

        if vi is None or vi.reference_id is None:
            return BasicReturn(
                    success=False,
                    error=("There is no VerificationItem "
                           "even when user is document_verified"))

        payload = {
            'merchant_id': self.merchant_id,
            'password': self.password,
            'reference': vi.reference_id
        }

        mime = 'image/jpeg'

        res = requests.post(
            self.enpoints['get_assets'],
            headers=AcuityTecAPI.get_headers(),
            data=payload)

        res_data = {
            'document_type': vi.document_type
        }

        try:
            res.raise_for_status()
            data = res.json()
            docs = data.get('documents')
            if docs is None:
                return BasicReturn(success=False, error=f"Acuitytec has no documents for reference id: {vi.reference_id}")

            for k in docs.keys():
                if docs.get(k) is None:
                    continue
                if k not in ['document_id_front_photo', 'document_id_back_photo']:
                    continue
                name = f'{k}.jpeg'
                file_img = BytesIO(base64.b64decode(docs.get(k)))
                file_img.seek(0)
                res_data[k] = (name, file_img, mime)

            return BasicReturn(success=True, data=res_data)
        except Exception as e:
            trace_back = uuid4()
            print(f'TracebackID: {trace_back}\n{e}')
            return BasicReturn(success=False, error=f"Unspected error traceback id: {trace_back}", data=e)

    @staticmethod
    def parse_user_to_geo(user: Users, ip: str):
        names, full_name = sync_names(user.first_name, user.last_name, '')

        return {
            'first_name': names[0],
            'last_name': names[1],
            'user_name': user.username,
            'email': user.email,
            'city': user.city,
            'id': str(user.id),
            'cca2': user.country_obj.code_cca2 if user.country_obj else user.country,
            'ip': ip
        }

    @staticmethod
    @cache_ips_geo(logger)
    def is_geo_verified(first_name: str,
                        last_name: str,
                        user_name: str,
                        email: str,
                        city: str,
                        id: str,
                        cca2: str,
                        ip: str) -> Dict[str, Union[str, int]]:

        endpoint = f"{settings.ACUITYTEC_API.rstrip('/')}/customerregistration"

        merchant_id = settings.ACUITYTEC_MERCHANT_ID
        password = settings.ACUITYTEC_PASSWORD

        customer_info = {
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'country': cca2,
            'city': city,
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
            'site_skin_name': urlparse(settings.DOMAIN_URL).hostname,
            'affiliate_id': 'lg',
        }

        # Add customer information with proper tags
        for key, value in customer_info.items():
            payload[f'customer_information[{key}]'] = value

        # Set default device ID if not provided
        payload.setdefault('reg_device_id', '00:00:00:00:00:00')

        # Set default device fingerprint if not provided
        payload.setdefault('device_fingerprint', 'N/A')

        try:
            payload = {k: v for k, v in payload.items() if v is not None}

            response = requests.post(
                endpoint,
                headers=AcuityTecAPI.get_headers(),
                data=payload,
                timeout=30)
            try:
                response.raise_for_status()
            except requests.RequestException:
                logger.critical("Acuitytec had error code "
                                f"{response.status_code}")
                return {
                    'error': True,
                    'message': ("The Geo service is down, "
                                "please try again in a few hours."),
                    'status': -2
                }

            # Parse JSON response# Parse JSON response
            data = response.json()

            try:
                risk = float(data.get('score', 0.1))
            except (ValueError, TypeError):
                risk = 0.1

            rules: Optional[list[Dict[str, str]]] = data.get('rules_triggered')

            rules = rules or [] if risk == 0 else rules

            if data is None or rules is None:
                return {
                    "error": True,
                    "message": "The Geo Verification service is not available.",
                    "status": -2
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
                            "error": False,
                            "message": message,
                            "rule": name,
                            "status": -1
                        }

            if risk > 90:
                return {
                        "error": False,
                        "message": 'Login has been categorized as risky',
                        "rule": "risk score > 90",
                        "status": -1
                    }

            return {
                'error': False,
                "message": "OK",
                "rule": "",
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
            # data = x_forwarded_for
        else:
            ip = request.META.get('REMOTE_ADDR')
            # data = [ip]

        # file = "acuitytec_request_log.txt"
        # ts = str(time.time())
        # from pprint import pformat
        # data = pformat(data)

        # entry = (
        #     f"\n--- {ts} ---\n"
        #     f"URL: USER IP \n"
        #     f"DATA:\n{data}\n"
        # )

        # with open(file, 'a') as f:
        #     f.write(entry)

        return ip

    @staticmethod
    def format_response(
        message: str,
        extra_message: str,
        status: int,
        expiration: Optional[int]
    ):
        return {
            'message': message,
            'status': status,
            'expiration': expiration
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
