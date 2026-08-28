"""
V2 AI Intelligence Service Package.

Exports AIIntelligenceService, GeminiClient, and FallbackEvaluator.
"""

from .service import AIIntelligenceService
from .client import GeminiClient
from .evaluator import FallbackEvaluator
from .prompt_templates import AI_EVALUATION_SCHEMA, SYSTEM_INSTRUCTION, build_signal_prompt

__all__ = [
    "AIIntelligenceService",
    "GeminiClient",
    "FallbackEvaluator",
    "AI_EVALUATION_SCHEMA",
    "SYSTEM_INSTRUCTION",
    "build_signal_prompt",
]
