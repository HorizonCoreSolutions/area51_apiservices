"""
AcuityTec Customer Registration API Client
Simple Python implementation for customer registration verification
"""
import requests
import json
from datetime import datetime
from typing import Dict, Any, Optional
from apps.acuitytec.models import AcuitytecUser
from apps.users.models import Users
from django.conf import settings


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
        self.base_url = settings.ACUITYTEC_API.rstrip('/')
        self.user = user
        
        self.merchant_id = settings.ACUITYTEC_MERCHANT_ID
        self.password = settings.ACUITYTEC_PASSWORD
        
        self.enpoints = {
            "register_user" : f"{self.base_url}/customerregistration",
            "photo_id" : f"{self.base_url}/photoIdOnlineVerification",
            }
    
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
            'reg_date': self.user.created,
            'reg_ip_address': reg_ip_address,
        }
        
        # Add customer information with proper tags
        for key, value in customer_info.items():
            payload[f'customer_information[{key}]'] = value
        
        # Add optional parameters
        optional_fields = [
            'reg_device_id', 'device_fingerprint', 'source', 'bonus_code',
            'bonus_submission_date', 'bonus_amount', 'site_skin_name',
            'how_did_you_hear', 'affiliate_id'
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
            
            AcuitytecUser.objects.create(
                user=self.user,
                login_ip=reg_ip_address
                )
            
            # Parse JSON response
            return response.json()
            
        except requests.exceptions.RequestException as e:
            return {
                'error': True,
                'message': f'Request failed: {str(e)}',
                'status': -1
            }
        except json.JSONDecodeError as e:
            return {
                'error': True,
                'message': f'Invalid JSON response: {str(e)}',
                'status': -1
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
        }
        
        
        
        # Add optional fields if provided
        optional_fields = [
            'address1', 'address2', 'city', 'province', 'postal_code',
            'country', 'phone1', 'phone2', 'dob', 'id_type', 'id_value',
            'gender', 'marital_status'
        ]
        
        for field in optional_fields:
            if field in optional_info:
                customer_info[field] = optional_info[field]
        
        return customer_info

    def getLink(self, document, language):
        try:
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

            response = requests.post(self.enpoints['photo_id'], data=data, timeout=30)

            if response.status_code == 200:
                result = response.json()
                if result.get("status") == 0:
                    print("Verification initiated successfully.")
                    print("Reference ID:", result["reference_id"])
                    print("Verification URL:", result["verification_source"])
                    return result['verification_source']
                else:
                    print("API responded with error:", result.get("description"))
                    return 'error' + result.get("description")
            else:
                print("HTTP error:", response.status_code)
                return 'error' + str(response.status_code)
        except:
            return 'error' + 'Something wrong has happend'

# Example usage
if __name__ == "__main__":
    
    user = Users.objects.filter(username='test').first()
    
    if user is not None:
        
        # Initialize API client
        api_client = AcuityTecAPI(user)
        
        # Create customer information
        result = api_client.register_customer(reg_ip_address='139.2.4.5')