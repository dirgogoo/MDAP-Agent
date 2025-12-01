"""
Interrupt Handler - Gerencia interrupções do usuário

Permite pausar, continuar, modificar e cancelar o pipeline
de forma controlada.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, TYPE_CHECKING, Callable, Awaitable
from enum import Enum

if TYPE_CHECKING:
    from .orchestrator import MDAPOrchestrator


class InterruptType(Enum):
    """Tipos de interrupção."""
    PAUSE = "pause"          # Pausar execução
    RESUME = "resume"        # Retomar execução
    CANCEL = "cancel"        # Cancelar pipeline
    EXPLAIN = "explain"      # Explicar ação atual
    MODIFY = "modify"        # Modificar output atual
    SKIP = "skip"            # Pular passo atual
    RETRY = "retry"          # Refazer passo atual


class InterruptResult(Enum):
    """Resultado do processamento de interrupção."""
    HANDLED = "handled"      # Interrupção processada
    DEFERRED = "deferred"    # Aguardando ponto seguro
    REJECTED = "rejected"    # Não pode processar agora
    ERROR = "error"          # Erro ao processar


@dataclass
class InterruptRequest:
    """Requisição de interrupção."""
    type: InterruptType
    data: Optional[dict] = None
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "user"  # "user", "keyboard", "budget", "error"

    @classmethod
    def pause(cls, source: str = "user") -> "InterruptRequest":
        return cls(type=InterruptType.PAUSE, source=source)

    @classmethod
    def resume(cls) -> "InterruptRequest":
        return cls(type=InterruptType.RESUME)

    @classmethod
    def cancel(cls) -> "InterruptRequest":
        return cls(type=InterruptType.CANCEL)

    @classmethod
    def explain(cls, target: Optional[str] = None) -> "InterruptRequest":
        return cls(type=InterruptType.EXPLAIN, data={"target": target})


@dataclass
class InterruptResponse:
    """Resposta a uma interrupção."""
    result: InterruptResult
    message: str
    data: Optional[dict] = None


class InterruptHandler:
    """
    Gerencia interrupções durante execução do pipeline.

    Responsabilidades:
    - Detectar pontos seguros para pausa
    - Processar diferentes tipos de interrupção
    - Coordenar com orchestrator
    """

    def __init__(self, orchestrator: "MDAPOrchestrator"):
        """
        Args:
            orchestrator: Referência ao orquestrador
        """
        self.orchestrator = orchestrator
        self._pending: Optional[InterruptRequest] = None
        self._handlers: dict[InterruptType, Callable] = {
            InterruptType.PAUSE: self._handle_pause,
            InterruptType.RESUME: self._handle_resume,
            InterruptType.CANCEL: self._handle_cancel,
            InterruptType.EXPLAIN: self._handle_explain,
            InterruptType.SKIP: self._handle_skip,
            InterruptType.RETRY: self._handle_retry,
        }

    def request(self, interrupt: InterruptRequest) -> None:
        """
        Registra requisição de interrupção.

        Interrupções são processadas no próximo ponto seguro.
        """
        self._pending = interrupt

    def has_pending(self) -> bool:
        """Verifica se há interrupção pendente."""
        return self._pending is not None

    def get_pending(self) -> Optional[InterruptRequest]:
        """Retorna interrupção pendente sem removê-la."""
        return self._pending

    def clear_pending(self) -> None:
        """Limpa interrupção pendente."""
        self._pending = None

    async def check_and_process(self) -> Optional[InterruptResponse]:
        """
        Verifica e processa interrupção pendente se estiver em ponto seguro.

        Returns:
            Resposta da interrupção ou None se não havia pendente
        """
        if not self._pending:
            return None

        if not self.is_safe_pause_point():
            return InterruptResponse(
                result=InterruptResult.DEFERRED,
                message="Aguardando ponto seguro para processar interrupção",
            )

        return await self.process(self._pending)

    async def process(self, request: InterruptRequest) -> InterruptResponse:
        """
        Processa uma interrupção imediatamente.

        Args:
            request: Requisição de interrupção

        Returns:
            Resposta do processamento
        """
        handler = self._handlers.get(request.type)
        if not handler:
            return InterruptResponse(
                result=InterruptResult.ERROR,
                message=f"Tipo de interrupção não suportado: {request.type.value}",
            )

        try:
            response = await handler(request)
            if request == self._pending:
                self._pending = None
            return response
        except Exception as e:
            return InterruptResponse(
                result=InterruptResult.ERROR,
                message=f"Erro ao processar interrupção: {e}",
            )

    def is_safe_pause_point(self) -> bool:
        """
        Verifica se está em um ponto seguro para pausar.

        Pontos seguros são:
        - Entre fases do pipeline
        - Entre iterações de geração
        - Aguardando decisão do usuário
        """
        from .state import PipelineState, EXECUTION_PHASES

        state = self.orchestrator.state.current

        # Sempre seguro se não está executando
        if state not in EXECUTION_PHASES:
            return True

        # TODO: Verificar se está entre iterações
        # Por enquanto, considera sempre seguro
        return True

    # === Handlers ===

    async def _handle_pause(self, request: InterruptRequest) -> InterruptResponse:
        """Handler para PAUSE."""
        success = await self.orchestrator.pause()
        if success:
            return InterruptResponse(
                result=InterruptResult.HANDLED,
                message="Pipeline pausado com sucesso",
            )
        else:
            return InterruptResponse(
                result=InterruptResult.REJECTED,
                message="Não foi possível pausar (estado inválido)",
            )

    async def _handle_resume(self, request: InterruptRequest) -> InterruptResponse:
        """Handler para RESUME."""
        success = await self.orchestrator.resume()
        if success:
            return InterruptResponse(
                result=InterruptResult.HANDLED,
                message="Pipeline retomado",
            )
        else:
            return InterruptResponse(
                result=InterruptResult.REJECTED,
                message="Não foi possível retomar (não estava pausado)",
            )

    async def _handle_cancel(self, request: InterruptRequest) -> InterruptResponse:
        """Handler para CANCEL."""
        success = await self.orchestrator.cancel()
        if success:
            return InterruptResponse(
                result=InterruptResult.HANDLED,
                message="Pipeline cancelado",
            )
        else:
            return InterruptResponse(
                result=InterruptResult.REJECTED,
                message="Não foi possível cancelar",
            )

    async def _handle_explain(self, request: InterruptRequest) -> InterruptResponse:
        """Handler para EXPLAIN."""
        target = request.data.get("target") if request.data else None

        if target:
            # Explicar decisão específica
            explanation = self.orchestrator.explain_current()  # TODO: por ID
        else:
            # Explicar estado atual
            explanation = self.orchestrator.explain_current()

        return InterruptResponse(
            result=InterruptResult.HANDLED,
            message=explanation,
        )

    async def _handle_skip(self, request: InterruptRequest) -> InterruptResponse:
        """Handler para SKIP."""
        # TODO: Implementar skip de passo atual
        return InterruptResponse(
            result=InterruptResult.REJECTED,
            message="Skip ainda não implementado",
        )

    async def _handle_retry(self, request: InterruptRequest) -> InterruptResponse:
        """Handler para RETRY."""
        # TODO: Implementar retry de passo atual
        return InterruptResponse(
            result=InterruptResult.REJECTED,
            message="Retry ainda não implementado",
        )


def create_keyboard_interrupt_handler(handler: InterruptHandler) -> Callable:
    """
    Cria callback para tratar Ctrl+C.

    Returns:
        Função callback para signal handler
    """
    def on_keyboard_interrupt():
        handler.request(InterruptRequest.pause(source="keyboard"))

    return on_keyboard_interrupt
