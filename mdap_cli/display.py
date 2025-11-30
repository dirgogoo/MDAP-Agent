"""
Display MDAP com Rich

Interface em tempo real usando Rich Live.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

from rich.console import Console, Group
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskID
from rich.table import Table
from rich.tree import Tree
from rich.text import Text
from rich.syntax import Syntax
from rich import box

from .events import EventBus, Event, EventType


@dataclass
class StepState:
    """Estado de um passo"""
    action: str
    target: str
    done: bool = False
    active: bool = False
    result: str = ""
    children: list = field(default_factory=list)


@dataclass
class VotingState:
    """Estado da votacao atual"""
    funcao: str = ""
    candidates: int = 0
    max_candidates: int = 5
    groups: dict = field(default_factory=dict)
    status: str = ""
    active: bool = False


@dataclass
class DisplayState:
    """Estado completo do display"""
    task: str = ""
    phase: str = ""
    steps: list[StepState] = field(default_factory=list)
    current_step: int = 0
    voting: VotingState = field(default_factory=VotingState)
    logs: list[tuple[str, str, str]] = field(default_factory=list)  # (time, level, msg)
    depth: int = 0
    cli_calls: int = 0
    start_time: float = field(default_factory=time.time)
    done: bool = False
    error: str = ""

    @property
    def elapsed(self) -> str:
        """Tempo decorrido formatado"""
        seconds = int(time.time() - self.start_time)
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    @property
    def progress_text(self) -> str:
        """Texto de progresso"""
        done = sum(1 for s in self.steps if s.done)
        total = len(self.steps)
        return f"[{done}/{total}]" if total > 0 else ""


class MDAPDisplay:
    """
    Display em tempo real para MDAP usando Rich.

    Mostra:
    - Header com tarefa e tempo
    - Fase atual e progresso
    - Lista de execucao (passos)
    - Votacao em tempo real
    - Logs
    - Footer com metricas
    """

    def __init__(self, event_bus: EventBus):
        self.console = Console()
        self.event_bus = event_bus
        self.state = DisplayState()
        self._live: Optional[Live] = None

        # Registra handlers de eventos
        self._register_handlers()

    def _register_handlers(self):
        """Registra handlers para eventos do MDAP"""
        self.event_bus.subscribe(EventType.TASK_START, self._on_task_start)
        self.event_bus.subscribe(EventType.TASK_COMPLETE, self._on_task_complete)
        self.event_bus.subscribe(EventType.TASK_ERROR, self._on_task_error)

        self.event_bus.subscribe(EventType.PHASE_START, self._on_phase_start)
        self.event_bus.subscribe(EventType.PHASE_END, self._on_phase_end)

        self.event_bus.subscribe(EventType.STEP_START, self._on_step_start)
        self.event_bus.subscribe(EventType.STEP_END, self._on_step_end)

        self.event_bus.subscribe(EventType.VOTE_START, self._on_vote_start)
        self.event_bus.subscribe(EventType.CANDIDATE_GENERATED, self._on_candidate)
        self.event_bus.subscribe(EventType.GROUP_FORMED, self._on_group)
        self.event_bus.subscribe(EventType.VOTE_COMPLETE, self._on_vote_complete)

        self.event_bus.subscribe(EventType.DEPTH_INCREASE, self._on_depth_increase)
        self.event_bus.subscribe(EventType.DEPTH_DECREASE, self._on_depth_decrease)

        self.event_bus.subscribe(EventType.LOG, self._on_log)
        self.event_bus.subscribe(EventType.LOG_INFO, self._on_log)
        self.event_bus.subscribe(EventType.LOG_WARNING, self._on_log)
        self.event_bus.subscribe(EventType.LOG_ERROR, self._on_log)

    # ==================== Event Handlers ====================

    def _on_task_start(self, event: Event):
        self.state.task = event.data.get("task", "")
        self.state.start_time = time.time()
        self._add_log("INFO", f"Iniciando: {self.state.task[:50]}...")

    def _on_task_complete(self, event: Event):
        self.state.done = True
        self._add_log("INFO", "Tarefa completa!")

    def _on_task_error(self, event: Event):
        self.state.error = event.data.get("error", "Erro desconhecido")
        self._add_log("ERROR", self.state.error)

    def _on_phase_start(self, event: Event):
        self.state.phase = event.data.get("phase", "")
        self._add_log("INFO", f"Fase: {self.state.phase}")

    def _on_phase_end(self, event: Event):
        result = event.data.get("result", "")
        self._add_log("INFO", f"Fase {self.state.phase} concluida: {result}")

    def _on_step_start(self, event: Event):
        action = event.data.get("action", "")
        target = event.data.get("target", "")

        # Marca step anterior como done
        if self.state.steps and self.state.current_step < len(self.state.steps):
            self.state.steps[self.state.current_step].active = False

        # Adiciona novo step
        step = StepState(action=action, target=target, active=True)
        self.state.steps.append(step)
        self.state.current_step = len(self.state.steps) - 1

        self.state.cli_calls += 1

    def _on_step_end(self, event: Event):
        if self.state.steps:
            self.state.steps[-1].done = True
            self.state.steps[-1].active = False
            self.state.steps[-1].result = event.data.get("result", "")

    def _on_vote_start(self, event: Event):
        self.state.voting = VotingState(
            funcao=event.data.get("funcao", ""),
            max_candidates=event.data.get("max_samples", 5),
            active=True,
            status="Gerando candidatos..."
        )

    def _on_candidate(self, event: Event):
        self.state.voting.candidates = event.data.get("count", self.state.voting.candidates + 1)
        self.state.voting.status = f"Candidato {self.state.voting.candidates} gerado"

    def _on_group(self, event: Event):
        groups = event.data.get("groups", {})
        self.state.voting.groups = groups
        self.state.voting.status = "Comparando candidatos..."

    def _on_vote_complete(self, event: Event):
        self.state.voting.active = False
        winner = event.data.get("winner", "")
        votes = event.data.get("votes", {})
        self.state.voting.status = f"Vencedor: {winner}"
        self.state.voting.groups = votes
        self._add_log("INFO", f"Votacao: {votes}")

    def _on_depth_increase(self, event: Event):
        self.state.depth = event.data.get("depth", self.state.depth + 1)

    def _on_depth_decrease(self, event: Event):
        self.state.depth = max(0, event.data.get("depth", self.state.depth - 1))

    def _on_log(self, event: Event):
        level = event.data.get("level", "INFO")
        message = event.data.get("message", str(event.data))
        self._add_log(level, message)

    def _add_log(self, level: str, message: str):
        """Adiciona entrada no log"""
        timestamp = time.strftime("%H:%M:%S")
        self.state.logs.append((timestamp, level, message))
        # Mantem apenas ultimas 50 entradas
        if len(self.state.logs) > 50:
            self.state.logs = self.state.logs[-50:]

    # ==================== Rendering ====================

    def _build_layout(self) -> Layout:
        """Constroi layout da interface"""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=4),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=3),
        )

        layout["body"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=1),
        )

        layout["left"].split_column(
            Layout(name="execution", ratio=2),
            Layout(name="voting", ratio=1),
        )

        layout["right"].update(self._render_logs())

        return layout

    def _render_header(self) -> Panel:
        """Renderiza header"""
        title = Text()
        title.append("MDAP Agent", style="bold blue")
        title.append(" v1.0", style="dim")

        info = Text()
        info.append(f"  {self.state.task[:50]}", style="white")
        if len(self.state.task) > 50:
            info.append("...", style="dim")

        status = Text()
        status.append(f"  {self.state.elapsed}", style="cyan")
        status.append(f"  {self.state.progress_text}", style="green")
        if self.state.phase:
            status.append(f"  {self.state.phase}", style="yellow")

        content = Group(title, info, status)

        return Panel(
            content,
            box=box.ROUNDED,
            border_style="blue",
        )

    def _render_execution(self) -> Panel:
        """Renderiza lista de execucao"""
        tree = Tree("[bold]Execucao[/bold]")

        for i, step in enumerate(self.state.steps):
            # Icone de status
            if step.done:
                icon = "[green]OK[/green]"
            elif step.active:
                icon = "[yellow]>>[/yellow]"
            else:
                icon = "[dim]--[/dim]"

            # Texto do step
            target_short = step.target[:40] + "..." if len(step.target) > 40 else step.target
            step_text = f"{icon} [{i+1}] {step.action}: {target_short}"

            if step.result:
                step_text += f" [dim]({step.result})[/dim]"

            branch = tree.add(step_text)

            # Filhos (chamadas aninhadas)
            for child in step.children:
                child_icon = "[green]OK[/green]" if child.done else "[yellow]>>[/yellow]"
                branch.add(f"{child_icon} {child.action}: {child.target[:30]}")

        return Panel(tree, title="Passos", border_style="cyan")

    def _render_voting(self) -> Panel:
        """Renderiza estado da votacao"""
        if not self.state.voting.active and not self.state.voting.groups:
            return Panel("[dim]Aguardando votacao...[/dim]", title="Votacao MDAP")

        content = []

        # Funcao sendo votada
        funcao_short = self.state.voting.funcao[:50]
        content.append(Text(f"Funcao: {funcao_short}", style="bold"))
        content.append(Text(""))

        # Progress bar de candidatos
        progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
        )
        task = progress.add_task(
            "Candidatos",
            total=self.state.voting.max_candidates,
            completed=self.state.voting.candidates
        )
        content.append(progress)
        content.append(Text(""))

        # Grupos e votos
        if self.state.voting.groups:
            table = Table(show_header=False, box=None)
            for group, votes in self.state.voting.groups.items():
                bar = "=" * min(votes * 5, 20)
                table.add_row(f"{group}", f"[green]{bar}[/green]", f"{votes} votos")
            content.append(table)

        # Status
        content.append(Text(""))
        content.append(Text(self.state.voting.status, style="dim"))

        return Panel(Group(*content), title="Votacao MDAP", border_style="magenta")

    def _render_logs(self) -> Panel:
        """Renderiza log viewer"""
        table = Table(show_header=False, box=None, padding=(0, 1))

        # Mostra ultimas N entradas
        for timestamp, level, message in self.state.logs[-15:]:
            style = {
                "INFO": "white",
                "WARNING": "yellow",
                "ERROR": "red",
                "DEBUG": "dim",
            }.get(level, "white")

            table.add_row(
                Text(timestamp, style="dim"),
                Text(message[:60], style=style)
            )

        return Panel(table, title="Log", border_style="green")

    def _render_footer(self) -> Panel:
        """Renderiza footer com metricas"""
        metrics = Text()
        metrics.append(f"CLI Calls: {self.state.cli_calls}", style="cyan")
        metrics.append("  |  ", style="dim")
        metrics.append(f"Depth: {self.state.depth}", style="yellow")
        metrics.append("  |  ", style="dim")
        metrics.append(f"Steps: {len(self.state.steps)}", style="green")
        metrics.append("  |  ", style="dim")
        metrics.append("Press Ctrl+C to stop", style="dim")

        return Panel(metrics, box=box.ROUNDED, border_style="dim")

    def render(self) -> Layout:
        """Renderiza interface completa"""
        layout = self._build_layout()
        layout["header"].update(self._render_header())
        layout["execution"].update(self._render_execution())
        layout["voting"].update(self._render_voting())
        layout["right"].update(self._render_logs())
        layout["footer"].update(self._render_footer())
        return layout

    async def run(self):
        """Roda display em modo live"""
        with Live(self.render(), refresh_per_second=4, console=self.console) as live:
            self._live = live
            while not self.state.done:
                live.update(self.render())
                await asyncio.sleep(0.25)
            # Render final
            live.update(self.render())

    def print_final_summary(self):
        """Imprime resumo final"""
        self.console.print()
        self.console.print("[bold green]MDAP Pipeline Completo![/bold green]")
        self.console.print(f"Tempo total: {self.state.elapsed}")
        self.console.print(f"Passos executados: {len(self.state.steps)}")
        self.console.print(f"Chamadas CLI: {self.state.cli_calls}")
        self.console.print()
