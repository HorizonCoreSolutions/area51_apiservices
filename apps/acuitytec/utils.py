from typing import Dict, Union
from urllib.parse import quote_plus

from apps.acuitytec.models import IPLog

def generate_qr_code_url(data: str, size: str = "150x150") -> str:
    """
    Generate a QR code image URL using qrserver.com API.

    Args:
        data (str): The data/text to encode in the QR code.
        size (str): The size of the QR code image (e.g., "150x150").

    Returns:
        str: URL to the QR code image.
    """
    encoded_data = quote_plus(data)
    return f"https://api.qrserver.com/v1/create-qr-code/?size={size}&data={encoded_data}"



def cache_ips_geo(func):
    """This is a wrapper to cache the is_geo_verified 
    Args:
        func (is_geo_verified): 
    """
    def wrapper(*args, **kwargs) -> Dict[str, Union[str, int]]:
        ip = kwargs.get('ip')
        if not ip:
            raise ValueError("ip must be provided as a keyword argument: ip='1.1.1.1'")
        
        ip_obj = IPLog.objects.filter(ip=ip).first()
        
        if ip_obj is None:
            res = func(*args, **kwargs)
            status = res.get('status')
            if status not in {0, -1}:
                return res
            ip_obj = IPLog.use_or_create(
                ip=ip,
                defaults={
                    "status": status,
                    "error_name" : res.pop("rule"),
                    "display_message" : res.get('message')
                }
            )
        return ip_obj.parse_geo()
    
    return wrapper