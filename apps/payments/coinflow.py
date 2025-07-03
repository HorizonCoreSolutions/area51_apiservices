from typing import Optional
import requests
from apps.core.custom_types import BasicReturn
from apps.users.models import Users, VERIFICATION_PENDING, VERIFICATION_APPROVED, VERIFICATION_PROCESSING, VERIFICATION_REJECTED, VERIFICATION_FAILED, VERIFICATION_CANCELED, VERIFICATION_EXPIRED

from django.conf import settings


class CoinFlowEndpoints:
    def __init__(self, url: str):
        self._base_url: str = url.rstrip("")

    @property
    def get_merchant(self) -> str:
        return f'{self._base_url}/api/merchant'
    
    @property
    def register_user_attested(self) -> str:
        return f'{self._base_url}/api/withdraw/kyc/attested'


class CoinFlowClient:
    def __init__(self):
        self.coinflow_auth: str = settings.COINFLOW_AUTH
        self.coinflow_api_url: str = settings.COINFLOW_API_URL.rstrip("")
        self.endpoits: CoinFlowEndpoints = CoinFlowEndpoints(url=self.coinflow_api_url)
        self._merchant_id = self._get_merchant_id()
        
    def get_headers(self, auth: bool=True,
                    content_json: bool=True,
                    auth_blockchain: Optional[str]=None,
                    auth_session_key: Optional[str]=None,
                    auth_user_id: Optional[str]=None,
                    auth_wallet: Optional[str]=None,
                    device_id: Optional[str]=None) -> dict:
        header = {
            "accept": "application/json",
        }
        if auth:
            header['Authorization'] = self.coinflow_auth
        if auth:
            header['Authorization'] = self.coinflow_auth
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

    def _get_merchant_id(self) -> str:
        result = requests.get(self.endpoits.get_merchant, headers=self.get_headers())
        result.raise_for_status()
        result = result.json()
        return result['merchantId']

    def register_user(self, user: Users, ssn: str) -> BasicReturn:
        if user.document_verified != VERIFICATION_APPROVED:
            return BasicReturn(success=False, error='User must be registered on Accuitytec.')
        
        payload = {
            "email": user.email,
            "firstName": user.first_name,
            "surName": user.last_name,
            "physicalAddress": user.complete_address,
            "city": (user.city if user.city else ' ').rjust(1),
            "state": user.state,
            "ssn": ssn,
            "dob": user.dob,
            "country": "a",
            "zip": "a"
        }
        
        requests.get(self.endpoits.register_user_attested, headers=self.get_headers())
        
        return BasicReturn(success=True)