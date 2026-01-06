import datetime
from decimal import Decimal
from typing import Any, Dict, Tuple


def generate_reference(user):
    now = str(datetime.datetime.now())
    return user.username + now


def validate_date(date):
    try:
        datetime.datetime.strptime(date, "%Y-%m-%d")
        return True
    except ValueError:
        return False

def serialize_wr_data(data: Dict[int, Tuple[Decimal, Decimal]]) -> Dict[str, Tuple[str, str]]:
    """
    Function to serialize the wagering requirements data

    Args:
        data (Dict[str, Decimal]):

    Returns:
        Dict[str, str]: Serialized data
    """
    def serialize_value(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (list, tuple)):
            return [serialize_value(v) for v in value]
        return value

    return {str(k): serialize_value(v) for k, v in data.items()}


def deserialize_wr_data(data: Dict[str, Tuple[str, str]]) -> Dict[int, Tuple[Decimal, Decimal]]:
    """
    Function to deserialize the wagering requirements data

    Args:
        data (Dict[str, str]): Serialized data

    Returns:
        Dict[int, Decimal]: Deserialized data
    """
    def deserialize_value(value: Any) -> Any:
        if isinstance(value, str):
            try:
                return Decimal(value)
            except Exception:
                return value
        if isinstance(value, list):
            return tuple(deserialize_value(v) for v in value)
        return value

    return {int(k): deserialize_value(v) for k, v in data.items()}
