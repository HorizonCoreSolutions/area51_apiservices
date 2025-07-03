from dataclasses import dataclass
from typing import Optional

@dataclass
class BasicReturn:
    success: bool
    error: Optional[str] = None
