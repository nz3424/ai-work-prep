from dataclasses import dataclass
from typing import Optional


@dataclass
class ScoreResult:
    score: Optional[float]
    pass_fail: Optional[str]
    raw_output: str
    error: Optional[str] = None
