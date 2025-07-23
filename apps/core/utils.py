import os
import time
from apps.core.file_logger import SimpleLogger
from django.core.exceptions import ImproperlyConfigured
from typing import Any, Type, Optional, Union

logger = SimpleLogger(name='EviromentVariables', log_file='logs/env_failure.log').get_logger()

def try_cast(value: Any, target_type: Optional[Type] = None) -> Union[Any, str]:
    if target_type is None:
        return value

    try:
        return target_type(value)
    except (ValueError, TypeError):
        logger.error(f"Failed to cast environment variable '{value}' to {target_type}")
        return value

def get_env_var(var_name: str, default: Any = None, cast: Optional[Type] = None) -> Any:
    try:
        value = os.environ.get(var_name, default)
    except KeyError:
        error_msg = f"Set the {var_name} environment variable"
        logger.critical(error_msg)
        raise ImproperlyConfigured(error_msg)

    if value is None:
        logger.warning(f"Set the {var_name} environment variable")
    result = try_cast(value, cast)
    return result


def save_request(service:str, request, is_response=False):
    file = f"{service}.txt"
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
        
def get_user_ip_from_request(request) -> str:
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')

    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()  # client’s real IP
        data = x_forwarded_for
    else:
        ip = request.META.get('REMOTE_ADDR')
        data = [ip]
    ip = data[0]
    return ip