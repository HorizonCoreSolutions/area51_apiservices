import os
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
