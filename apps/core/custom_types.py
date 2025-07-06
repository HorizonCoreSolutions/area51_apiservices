from dataclasses import dataclass
from typing import Any, Optional

@dataclass
class BasicReturn:
    success: bool
    error: Optional[str] = None
    message: Optional[str] = None
    data: Optional[Any] = None
