"""
REPL Adapter - Integra orquestrador com o REPL

Ponte entre comandos REPL e o orquestrador.
"""
from typing import TYPE_CHECKING

from .orchestrator import MDAPOrchestrator
from .tracker import DecisionTracker
from .resources import ResourceManager, ResourceBudget
from .interrupts import InterruptHandler
from .meta import MetaIntelligence
from .state import PipelineState

if TYPE_CHECKING:
    from ..repl.session import REPLSession


class OrchestratorAdapter:
    """
    Adapta o orquestrador para uso no REPL.

    Responsabilidades:
    - Inicializa todos os componentes
    - Fornece interface simplificada para comandos
    - Gerencia integração com session
    """

    def __init__(self, session: "REPLSession"):
        """
        Args:
            session: Sessão REPL
        """
        self.session = session

        # Inicializa componentes
        self.tracker = DecisionTracker()
        self.resources = ResourceManager()
        self.orchestrator = MDAPOrchestrator(session)
        self.interrupts = InterruptHandler(self.orchestrator)
        self.meta = MetaIntelligence(
            orchestrator=self.orchestrator,
            tracker=self.tracker,
            resources=self.resources,
        )

        # Conecta componentes ao orchestrator
        self.orchestrator._tracker = self.tracker
        self.orchestrator._resources = self.resources
        self.orchestrator._interrupts = self.interrupts
        self.orchestrator._meta = self.meta

    # === API para Comandos ===

    async def run(self, task: str) -> None:
        """
        Executa pipeline para uma tarefa.

        Equivale a: /run <task>
        """
        from ..repl.ui import show_info, show_error

        if self.orchestrator.state.is_running():
            show_error(self.session.console, "Pipeline já em execução. Use /pause ou /cancel primeiro.")
            return

        show_info(self.session.console, f"Iniciando pipeline para: {task}")
        self.resources.start_tracking()

        try:
            result = await self.orchestrator.start_task(task)

            if result.error:
                show_error(self.session.console, f"Pipeline falhou: {result.error}")
            else:
                show_info(
                    self.session.console,
                    f"Concluído! {len(result.requirements)} requisitos, "
                    f"{len(result.functions)} funções, {len(result.code)} implementações."
                )
        finally:
            self.resources.stop_tracking()

    async def pause(self) -> None:
        """
        Pausa pipeline.

        Equivale a: /pause
        """
        from ..repl.ui import show_info, show_error

        success = await self.orchestrator.pause()
        if success:
            show_info(
                self.session.console,
                f"Pausado em: {self.orchestrator.state.get_phase_name()}"
            )
        else:
            show_error(self.session.console, "Não foi possível pausar (não está em execução)")

    async def resume(self) -> None:
        """
        Retoma pipeline.

        Equivale a: /resume
        """
        from ..repl.ui import show_info, show_error

        success = await self.orchestrator.resume()
        if success:
            show_info(self.session.console, "Pipeline retomado")
            # Continua execução
            result = await self.orchestrator.start_task(self.orchestrator.state.task)
            if result.error:
                show_error(self.session.console, f"Erro: {result.error}")
        else:
            show_error(self.session.console, "Não foi possível retomar (não estava pausado)")

    async def cancel(self) -> None:
        """
        Cancela pipeline.

        Equivale a: /cancel
        """
        from ..repl.ui import show_info

        await self.orchestrator.cancel()
        show_info(self.session.console, "Pipeline cancelado")

    def status(self) -> None:
        """
        Mostra status atual.

        Equivale a: /status
        """
        from ..repl.ui import show_info
        from rich.panel import Panel
        from rich import box

        status = self.orchestrator.get_status()

        # Progress bar
        progress = int(status.progress_percent / 10)
        progress_bar = "█" * progress + "░" * (10 - progress)

        content = f"""Task: {status.task or '(none)'}
State: {status.state_name}
Progress: [{progress_bar}] {status.progress_percent:.0f}%

Results:
  Requirements: {status.requirements_count}
  Functions: {status.functions_count}
  Code: {status.code_count}

Time: {status.elapsed_seconds:.1f}s"""

        self.session.console.print(Panel(
            content,
            title="MDAP Orchestrator Status",
            border_style="cyan",
            box=box.ROUNDED,
        ))

    def explain(self, target: str = "") -> None:
        """
        Explica estado atual ou decisão específica.

        Equivale a: /explain [target]
        """
        from rich.panel import Panel
        from rich import box

        if target:
            # Tenta encontrar decisão por ID
            decision = self.tracker.get_by_id(target)
            if decision:
                explanation = decision.to_explanation()
                title = f"Decisão {target}"
            else:
                explanation = self.meta.explain_phase(target)
                title = f"Fase {target}"
        else:
            explanation = self.orchestrator.explain_current()
            title = "Estado Atual"

        self.session.console.print(Panel(
            explanation,
            title=title,
            border_style="blue",
            box=box.ROUNDED,
        ))

    def history(self, limit: int = 10) -> None:
        """
        Mostra histórico de decisões.

        Equivale a: /history [limit]
        """
        from rich.panel import Panel
        from rich import box

        decisions = self.tracker.get_history(limit)

        if not decisions:
            self.session.console.print("[dim]Nenhuma decisão registrada ainda.[/dim]")
            return

        lines = []
        for d in decisions:
            lines.append(d.to_summary())

        self.session.console.print(Panel(
            "\n".join(lines),
            title=f"Últimas {len(decisions)} Decisões",
            border_style="yellow",
            box=box.ROUNDED,
        ))

    def show_resources(self) -> None:
        """
        Mostra uso de recursos.

        Equivale a: /resources
        """
        from rich.panel import Panel
        from rich import box

        summary = self.resources.to_summary()

        self.session.console.print(Panel(
            summary,
            title="Recursos",
            border_style="green",
            box=box.ROUNDED,
        ))

    def set_budget(
        self,
        max_tokens: int = None,
        max_cost: float = None,
        max_time: float = None,
    ) -> None:
        """
        Define budget de recursos.

        Equivale a: /budget <tokens|cost|time> <value>
        """
        from ..repl.ui import show_info

        self.resources.set_budget(
            max_tokens=max_tokens,
            max_cost_usd=max_cost,
            max_time_seconds=max_time,
        )

        parts = []
        if max_tokens:
            parts.append(f"tokens={max_tokens}")
        if max_cost:
            parts.append(f"custo=${max_cost}")
        if max_time:
            parts.append(f"tempo={max_time}s")

        if parts:
            show_info(self.session.console, f"Budget definido: {', '.join(parts)}")
        else:
            show_info(self.session.console, "Budget removido")

    # === Estado ===

    @property
    def is_running(self) -> bool:
        """Verifica se pipeline está em execução."""
        return self.orchestrator.state.is_running()

    @property
    def is_paused(self) -> bool:
        """Verifica se pipeline está pausado."""
        return self.orchestrator.state.current == PipelineState.PAUSED

    @property
    def current_state(self) -> PipelineState:
        """Retorna estado atual."""
        return self.orchestrator.state.current
