from decimal import Decimal
from typing import Any, ClassVar

from apps.users.models import Configs
from apps.core.concurrency import redis_client


class PlatformConfigHandler:
    """Handles platform configuration with Redis caching and DB persistence."""

    # Here should be the default config values

    INFLUENCER_MINIMUM_AMOUNT: Decimal = Decimal("0.00")

    _SERIALIZATION_TABLE: ClassVar[dict[type, str]] = {
        int: "int ",
        str: "str ",
        bool: "bool",
        Decimal: "dcml",
    }

    _DESERIALIZATION_TABLE: ClassVar[dict[str, type]] = {
        "int ": int,
        "str ": str,
        "bool": bool,
        "dcml": Decimal,
    }

    def _serialize_data(self, data: Any) -> str:
        table = object.__getattribute__(self, "_SERIALIZATION_TABLE")
        type_ = type(data)
        type_name = table.get(type_)

        if type_name is None:
            raise ValueError(f"Unsupported type: {type_}")

        if type_ is bool:
            return f"{type_name}|{'1' if data else '0'}"

        return f"{type_name}|{data}"

    def _deserialize_data(self, value: str) -> Any:
        if not isinstance(value, str) or "|" not in value:
            raise ValueError("Invalid serialized data format")

        table = object.__getattribute__(self, "_DESERIALIZATION_TABLE")
        type_name, raw_value = value.split("|", 1)

        converter = table.get(type_name)
        if converter is None:
            raise ValueError(f"Unknown type marker: {type_name}")

        if converter is bool:
            return raw_value == "1"

        return converter(raw_value)

    def _validate_type(self, name: str, value: Any) -> None:
        """Validate that value matches the type of the class default, if one exists."""
        cls = object.__getattribute__(self, "__class__")

        # Check if there's a default defined on the class
        if not hasattr(cls, name):
            raise AttributeError(f"Config '{name}' not found")

        default_value = getattr(cls, name)

        # Skip validation for internal attributes
        if callable(default_value):
            return

        expected_type = type(default_value)
        actual_type = type(value)

        if actual_type is not expected_type:
            raise TypeError(
                f"Config '{name}' expects {expected_type.__name__}, "
                f"got {actual_type.__name__}"
            )

    def __getattribute__(self, name: str) -> Any:
        # Internal/private attributes bypass config lookup
        if name.startswith("_"):
            return object.__getattribute__(self, name)

        # Try Redis first
        data = redis_client.get(f"config:{name}")
        if data:
            return object.__getattribute__(self, "_deserialize_data")(data)

        # Try database
        try:
            config = Configs.objects.get(name=name)
            return object.__getattribute__(self, "_deserialize_data")(config.value)
        except Configs.DoesNotExist:
            pass

        # Fall back to class attribute (default) or raise AttributeError
        return object.__getattribute__(self, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return

        # Validate type matches the default (if one exists)
        validate = object.__getattribute__(self, "_validate_type")
        validate(name, value)

        serialize = object.__getattribute__(self, "_serialize_data")
        data = serialize(value)

        redis_client.set(f"config:{name}", data)
        Configs.objects.update_or_create(name=name, defaults={"value": data})


config = PlatformConfigHandler()