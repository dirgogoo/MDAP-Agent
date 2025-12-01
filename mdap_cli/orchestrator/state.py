"""
Orchestrator State Machine

Define estados do pipeline e transições válidas.
"""
from enum import Enum
from typing import Optional, Set
from dataclasses import dataclass, field
from datetime import datetime


class PipelineState(Enum):
    """Estados possíveis do orquestrador."""
    IDLE = "idle"                    # Aguardando tarefa
    EXPANDING = "expanding"          # Fase EXPAND - gerando requisitos
    DECOMPOSING = "decomposing"      # Fase DECOMPOSE - planejando funções
    GENERATING = "generating"        # Fase GENERATE - implementando código
    VALIDATING = "validating"        # Fase VALIDATE - verificando correção
    PAUSED = "paused"               # Pausado pelo usuário
    AWAITING_DECISION = "awaiting"  # Checkpoint aguardando input
    COMPLETED = "completed"          # Pipeline concluído com sucesso
    ERROR = "error"                  # Pipeline falhou


# Transições válidas entre estados
VALID_TRANSITIONS: dict[PipelineState, Set[PipelineState]] = {
    PipelineState.IDLE: {
        PipelineState.EXPANDING,      # /run inicia pipeline
    },
    PipelineState.EXPANDING: {
        PipelineState.DECOMPOSING,    # Avança para próxima fase
        PipelineState.PAUSED,         # Ctrl+C ou /pause
        PipelineState.ERROR,          # Falha
        PipelineState.AWAITING_DECISION,  # Checkpoint
    },
    PipelineState.DECOMPOSING: {
        PipelineState.GENERATING,     # Avança para próxima fase
        PipelineState.PAUSED,         # Ctrl+C ou /pause
        PipelineState.ERROR,          # Falha
        PipelineState.AWAITING_DECISION,  # Checkpoint
    },
    PipelineState.GENERATING: {
        PipelineState.VALIDATING,     # Avança para próxima fase
        PipelineState.COMPLETED,      # Se não houver validação
        PipelineState.PAUSED,         # Ctrl+C ou /pause
        PipelineState.ERROR,          # Falha
        PipelineState.AWAITING_DECISION,  # Checkpoint
    },
    PipelineState.VALIDATING: {
        PipelineState.COMPLETED,      # Sucesso
        PipelineState.GENERATING,     # Volta para corrigir
        PipelineState.PAUSED,         # Ctrl+C ou /pause
        PipelineState.ERROR,          # Falha
        PipelineState.AWAITING_DECISION,  # Checkpoint
    },
    PipelineState.PAUSED: {
        PipelineState.EXPANDING,      # Resume para EXPANDING
        PipelineState.DECOMPOSING,    # Resume para DECOMPOSING
        PipelineState.GENERATING,     # Resume para GENERATING
        PipelineState.VALIDATING,     # Resume para VALIDATING
        PipelineState.IDLE,           # /cancel
    },
    PipelineState.AWAITING_DECISION: {
        PipelineState.EXPANDING,      # Continua após decisão
        PipelineState.DECOMPOSING,    # Continua após decisão
        PipelineState.GENERATING,     # Continua após decisão
        PipelineState.VALIDATING,     # Continua após decisão
        PipelineState.PAUSED,         # Pausa durante decisão
        PipelineState.IDLE,           # Cancela durante decisão
    },
    PipelineState.COMPLETED: {
        PipelineState.IDLE,           # Reset para nova tarefa
    },
    PipelineState.ERROR: {
        PipelineState.IDLE,           # Reset após erro
    },
}

# Fases de execução (estados que processam ativamente)
EXECUTION_PHASES = {
    PipelineState.EXPANDING,
    PipelineState.DECOMPOSING,
    PipelineState.GENERATING,
    PipelineState.VALIDATING,
}


@dataclass
class StateTransition:
    """Registro de uma transição de estado."""
    from_state: PipelineState
    to_state: PipelineState
    reason: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class OrchestratorState:
    """
    Estado completo do orquestrador.

    Mantém estado atual, histórico de transições,
    e estado anterior (para resume após pause).
    """
    current: PipelineState = PipelineState.IDLE
    previous: Optional[PipelineState] = None  # Para resume
    task: str = ""
    current_phase_detail: str = ""  # Ex: "requisito 3 de 5"
    transition_history: list[StateTransition] = field(default_factory=list)
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def can_transition(self, to: PipelineState) -> bool:
        """Verifica se transição é válida."""
        valid = VALID_TRANSITIONS.get(self.current, set())
        return to in valid

    def transition(self, to: PipelineState, reason: str = "") -> bool:
        """
        Realiza transição de estado.

        Args:
            to: Estado destino
            reason: Motivo da transição

        Returns:
            True se transição foi realizada, False se inválida
        """
        if not self.can_transition(to):
            return False

        # Registra transição
        transition = StateTransition(
            from_state=self.current,
            to_state=to,
            reason=reason,
        )
        self.transition_history.append(transition)

        # Salva estado anterior se pausando
        if to == PipelineState.PAUSED:
            self.previous = self.current

        # Atualiza timestamps
        if to in EXECUTION_PHASES and self.started_at is None:
            self.started_at = datetime.now()
        elif to == PipelineState.COMPLETED:
            self.completed_at = datetime.now()

        self.current = to
        return True

    def get_resume_state(self) -> Optional[PipelineState]:
        """Retorna estado para resume após pause."""
        if self.current != PipelineState.PAUSED:
            return None
        return self.previous

    def is_running(self) -> bool:
        """Verifica se está em execução ativa."""
        return self.current in EXECUTION_PHASES

    def is_pausable(self) -> bool:
        """Verifica se pode ser pausado."""
        return self.current in EXECUTION_PHASES or self.current == PipelineState.AWAITING_DECISION

    def is_terminal(self) -> bool:
        """Verifica se está em estado terminal."""
        return self.current in {PipelineState.COMPLETED, PipelineState.ERROR, PipelineState.IDLE}

    def reset(self) -> None:
        """Reseta para estado inicial."""
        self.current = PipelineState.IDLE
        self.previous = None
        self.task = ""
        self.current_phase_detail = ""
        self.error_message = None
        self.started_at = None
        self.completed_at = None
        # Mantém histórico para análise

    def get_elapsed_seconds(self) -> float:
        """Retorna tempo decorrido em segundos."""
        if self.started_at is None:
            return 0.0
        end = self.completed_at or datetime.now()
        return (end - self.started_at).total_seconds()

    def get_phase_name(self) -> str:
        """Retorna nome amigável da fase atual."""
        names = {
            PipelineState.IDLE: "Aguardando",
            PipelineState.EXPANDING: "Expandindo Requisitos",
            PipelineState.DECOMPOSING: "Decompondo Funções",
            PipelineState.GENERATING: "Gerando Código",
            PipelineState.VALIDATING: "Validando",
            PipelineState.PAUSED: "Pausado",
            PipelineState.AWAITING_DECISION: "Aguardando Decisão",
            PipelineState.COMPLETED: "Concluído",
            PipelineState.ERROR: "Erro",
        }
        return names.get(self.current, str(self.current.value))
