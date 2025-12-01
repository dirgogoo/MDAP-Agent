"""
MDAP Orchestrator Package

Coordena pipeline MDAP com modo híbrido (automático + interrupções)
e meta-inteligência para explicar decisões.
"""
from .state import (
    PipelineState,
    OrchestratorState,
    StateTransition,
    VALID_TRANSITIONS,
    EXECUTION_PHASES,
)
from .orchestrator import (
    MDAPOrchestrator,
    OrchestratorResult,
    OrchestratorStatus,
)
from .tracker import (
    DecisionTracker,
    DecisionRecord,
    DecisionPhase,
    VotingDetails,
)
from .resources import (
    ResourceManager,
    ResourceUsage,
    ResourceBudget,
    BudgetStatus,
)
from .interrupts import (
    InterruptHandler,
    InterruptRequest,
    InterruptType,
    InterruptResult,
)
from .meta import MetaIntelligence
from .adapter import OrchestratorAdapter
from .intent import IntentDetector, UserIntent, IntentResult

__all__ = [
    # State
    "PipelineState",
    "OrchestratorState",
    "StateTransition",
    "VALID_TRANSITIONS",
    "EXECUTION_PHASES",
    # Orchestrator
    "MDAPOrchestrator",
    "OrchestratorResult",
    "OrchestratorStatus",
    # Tracker
    "DecisionTracker",
    "DecisionRecord",
    "DecisionPhase",
    "VotingDetails",
    # Resources
    "ResourceManager",
    "ResourceUsage",
    "ResourceBudget",
    "BudgetStatus",
    # Interrupts
    "InterruptHandler",
    "InterruptRequest",
    "InterruptType",
    "InterruptResult",
    # Meta
    "MetaIntelligence",
    # Adapter
    "OrchestratorAdapter",
    # Intent
    "IntentDetector",
    "UserIntent",
    "IntentResult",
]
