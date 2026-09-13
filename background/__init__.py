"""
PROJECT-ALPHA — Background Module.

Provides async task scheduling, health monitoring, performance analytics,
backtesting pipelines, and self-calibrating feedback loops.
"""

from .scheduler.scheduler import BackgroundScheduler
from .analytics.engine import AnalyticsEngine
from .journal.service import JournalService
from .feedback.service import FeedbackService
from .feedback.orchestrator import FeedbackOrchestrator
from .learning.engine import LearningEngine
from .learning.service import LearningService
from .backtest.engine import BacktestEngine
from .backtest.service.service import BacktestService
from .production.service import ProductionService
from .production.controller import ProductionController, DeploymentMode
from .production.watchdog import ProductionWatchdog
from .portfolio.service import PortfolioService
from .ai.service import AIIntelligenceService
from .monitoring.health import HealthChecker

# Aliases
Scheduler = BackgroundScheduler

__all__ = [
    "BackgroundScheduler",
    "Scheduler",
    "AnalyticsEngine",
    "JournalService",
    "FeedbackService",
    "FeedbackOrchestrator",
    "LearningEngine",
    "LearningService",
    "BacktestEngine",
    "BacktestService",
    "ProductionService",
    "ProductionController",
    "ProductionWatchdog",
    "DeploymentMode",
    "PortfolioService",
    "AIIntelligenceService",
    "HealthChecker",
]
