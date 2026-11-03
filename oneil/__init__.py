"""O'Neil CAN SLIM screening funnel.

Stages: universe -> weekly trend gate -> C/A/N/L/I/M fundamentals -> chart
audit (SMA alignment, RS line, volume dry-up, contraction, 3M excess return)
-> weighted rank with a sector boost -> market deploy gate.

Thresholds live in oneil.rules.
"""

from . import chart, pipeline, rules, score, synthetic, weekly  # noqa: F401
from .pipeline import Funnel, Result, screen  # noqa: F401

__version__ = "1.0.0"
