"""
10 Candidate Algorithmic Strategies for PROJECT-ALPHA.
"""

from __future__ import annotations

from .base import BaseStrategy, BacktestTradeSignal
from .vcp import VCPStrategy
from .nr7 import NR7Strategy
from .ppa import PPAStrategy
from .mtb import MTBStrategy
from .pmb import PMBStrategy
from .hda import HDAStrategy
from .ste import STEStrategy
from .bbs import BBSStrategy
from .mrb import MRBStrategy
from .vgx import VGXStrategy

ALL_CANDIDATE_STRATEGIES = [
    VCPStrategy(),
    NR7Strategy(),
    PPAStrategy(),
    MTBStrategy(),
    PMBStrategy(),
    HDAStrategy(),
    STEStrategy(),
    BBSStrategy(),
    MRBStrategy(),
    VGXStrategy(),
]

__all__ = [
    "BaseStrategy",
    "BacktestTradeSignal",
    "VCPStrategy",
    "NR7Strategy",
    "PPAStrategy",
    "MTBStrategy",
    "PMBStrategy",
    "HDAStrategy",
    "STEStrategy",
    "BBSStrategy",
    "MRBStrategy",
    "VGXStrategy",
    "ALL_CANDIDATE_STRATEGIES",
]
