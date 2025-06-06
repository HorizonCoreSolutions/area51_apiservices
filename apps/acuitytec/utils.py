from urllib.parse import quote_plus

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
