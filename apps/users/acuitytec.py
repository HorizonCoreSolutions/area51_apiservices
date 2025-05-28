"""
AcuityTec Customer Registration API Client
Simple Python implementation for customer registration verification
"""
import requests
import json
from datetime import datetime
from typing import Dict, Any, Optional
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
        self.base_url = settings.ACUATYTEC_API.rstrip('/')
        self.user = user
        self.enpoints = {
            "register_user" : f"{self.base_url}/customerregistration",
            }
    
    def register_customer(self, 
                         user_name: str,
                         user_number: str,
                         reg_date: str,
                         reg_ip_address: str,
                         customer_info: Dict[str, Any],
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
        
        # Build the request payload
        payload = {
            # Credentials
            'merchant_id': self.merchant_id,
            'password': self.password,
            
            # Required fields
            'user_name': user_name,
            'user_number': user_number,
            'reg_date': reg_date,
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
            response = requests.post(self.enpoints['register_user'], data=payload, timeout=30)
            response.raise_for_status()
            
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

def create_customer_info(first_name: str, 
                        last_name: str, 
                        email: str,
                        **optional_info) -> Dict[str, Any]:
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
        'first_name': first_name,
        'last_name': last_name,
        'email': email
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

# Example usage
if __name__ == "__main__":
    # Configuration
    BASE_URL = "https://api.acuitytec.com"  # Replace with actual API URL
    MERCHANT_ID = "your_merchant_id"        # Replace with your merchant ID
    PASSWORD = "your_password"              # Replace with your password
    
    # Initialize API client
    api_client = AcuityTecAPI(BASE_URL, MERCHANT_ID, PASSWORD)
    
    # Create customer information
    customer_data = create_customer_info(
        first_name="John",
        last_name="Doe",
        email="john.doe@example.com",
        address1="123 Main St",
        city="New York",
        province="NY",
        postal_code="10001",
        country="US",
        phone1="5551234567",
        dob="1990-01-15",
        gender="M",
        marital_status="1"  # Single
    )
    
    # Register customer
    result = api_client.register_customer(
        user_name="johndoe123",
        user_number="USER_12345",
        reg_date=datetime.now().strftime("%Y-%m-%d"),
        reg_ip_address="192.168.1.100",
        customer_info=customer_data,
        source="internet",
        how_did_you_hear="Google Search"
    )
    
    # Process response
    if 'error' in result:
        print(f"Error: {result['message']}")
    else:
        print("Registration processed successfully!")
        print(f"Status: {result.get('status', 'Unknown')}")
        print(f"Description: {result.get('description', 'No description')}")
        print(f"Risk Score: {result.get('score', 'No score')}")
        print(f"Registration ID: {result.get('id', 'No ID')}")
        
        if 'rules_triggered' in result:
            print("Rules Triggered:")
            for rule in result['rules_triggered']:
                print(f"  - {rule}")