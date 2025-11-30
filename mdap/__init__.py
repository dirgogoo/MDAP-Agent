"""
MDAP Agent - Framework de Coding com Votação

Combina conceitos do paper MAKER com agent loops modernos:
- Votação first-to-ahead-by-k
- Expansão de requisitos (não apenas decomposição)
- Separação entre Execução e Decisão
"""
from .types import (
    Language,
    StepType,
    Step,
    Candidate,
    VoteResult,
    ExecutionResult,
    Context,
    ContextSnapshot,
    MDAPConfig,
)

__version__ = "0.1.0"
__all__ = [
    "Language",
    "StepType",
    "Step",
    "Candidate",
    "VoteResult",
    "ExecutionResult",
    "Context",
    "ContextSnapshot",
    "MDAPConfig",
]
