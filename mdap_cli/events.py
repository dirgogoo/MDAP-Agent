"""
Sistema de Eventos para MDAP CLI

Pub/Sub desacoplado para comunicacao entre o agent loop e a interface.
"""

from dataclasses import dataclass, field
from typing import Callable, Any
from enum import Enum
import time


class EventType(Enum):
    """Tipos de eventos do MDAP"""
    # Fases do pipeline
    PHASE_START = "phase_start"
    PHASE_END = "phase_end"

    # Passos individuais
    STEP_START = "step_start"
    STEP_END = "step_end"

    # Votacao MDAP
    VOTE_START = "vote_start"
    CANDIDATE_GENERATED = "candidate_generated"
    CANDIDATE_COMPARED = "candidate_compared"
    GROUP_FORMED = "group_formed"
    VOTE_COMPLETE = "vote_complete"

    # Chamadas aninhadas
    DEPTH_INCREASE = "depth_increase"
    DEPTH_DECREASE = "depth_decrease"

    # Logs e status
    LOG = "log"
    LOG_DEBUG = "log_debug"
    LOG_INFO = "log_info"
    LOG_WARNING = "log_warning"
    LOG_ERROR = "log_error"

    # Controle
    TASK_START = "task_start"
    TASK_COMPLETE = "task_complete"
    TASK_ERROR = "task_error"
    CHECKPOINT = "checkpoint"

    # Orchestrator
    ORCHESTRATOR_STATE_CHANGE = "orchestrator_state_change"
    ORCHESTRATOR_PROGRESS = "orchestrator_progress"
    ORCHESTRATOR_INTERRUPT = "orchestrator_interrupt"
    ORCHESTRATOR_CHECKPOINT = "orchestrator_checkpoint"
    ORCHESTRATOR_EXPLAIN = "orchestrator_explain"
    ORCHESTRATOR_BUDGET_WARNING = "orchestrator_budget_warning"
    ORCHESTRATOR_DECISION = "orchestrator_decision"


@dataclass
class Event:
    """Um evento do sistema"""
    type: EventType
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class EventBus:
    """
    Pub/Sub para eventos do MDAP.

    Permite desacoplar o agent loop da interface,
    facilitando diferentes displays (CLI, GUI, logs).

    Exemplo:
        bus = EventBus()

        # Subscriber
        def on_vote(event):
            print(f"Votacao: {event.data}")
        bus.subscribe(EventType.VOTE_COMPLETE, on_vote)

        # Publisher
        bus.emit(Event(EventType.VOTE_COMPLETE, {"winner": "group_0"}))
    """

    def __init__(self):
        self._handlers: dict[EventType, list[Callable[[Event], None]]] = {}
        self._global_handlers: list[Callable[[Event], None]] = []
        self._history: list[Event] = []
        self._record_history = False

    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]):
        """Registra handler para um tipo de evento"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def subscribe_all(self, handler: Callable[[Event], None]):
        """Registra handler para todos os eventos"""
        self._global_handlers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: Callable[[Event], None]):
        """Remove handler de um tipo de evento"""
        if event_type in self._handlers:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h != handler
            ]

    def emit(self, event: Event):
        """Emite evento para todos os handlers registrados"""
        # Salva no historico se habilitado
        if self._record_history:
            self._history.append(event)

        # Handlers globais
        for handler in self._global_handlers:
            try:
                handler(event)
            except Exception as e:
                print(f"[EventBus] Error in global handler: {e}")

        # Handlers especificos
        for handler in self._handlers.get(event.type, []):
            try:
                handler(event)
            except Exception as e:
                print(f"[EventBus] Error in handler for {event.type}: {e}")

    def emit_simple(self, event_type: EventType, **data):
        """Atalho para emitir evento simples"""
        self.emit(Event(type=event_type, data=data))

    def start_recording(self):
        """Inicia gravacao de historico"""
        self._record_history = True
        self._history = []

    def stop_recording(self) -> list[Event]:
        """Para gravacao e retorna historico"""
        self._record_history = False
        return self._history

    def get_history(self) -> list[Event]:
        """Retorna historico gravado"""
        return self._history.copy()

    def clear_history(self):
        """Limpa historico"""
        self._history = []


# Singleton para uso global (opcional)
_global_bus: EventBus | None = None


def get_global_bus() -> EventBus:
    """Retorna EventBus global singleton"""
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus


def emit(event_type: EventType, **data):
    """Atalho para emitir no bus global"""
    get_global_bus().emit_simple(event_type, **data)
