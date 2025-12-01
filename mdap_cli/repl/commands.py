"""
Command Router para MDAP REPL

Gerencia comandos slash (/).
"""
from typing import TYPE_CHECKING, Callable, Awaitable, Optional
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from .session import REPLSession


@dataclass
class Command:
    """Definicao de um comando."""
    name: str
    description: str
    handler: Callable[["REPLSession", list[str]], Awaitable[None]]
    aliases: list[str] = field(default_factory=list)


class CommandRouter:
    """Router de comandos slash."""

    def __init__(self, session: "REPLSession"):
        self.session = session
        self._commands: dict[str, Command] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Registra comandos built-in."""
        self.register(Command(
            name="/help",
            description="Show available commands",
            handler=cmd_help,
            aliases=["/h", "/?"]
        ))

        self.register(Command(
            name="/clear",
            description="Clear screen and history",
            handler=cmd_clear,
            aliases=["/cls"]
        ))

        self.register(Command(
            name="/exit",
            description="Exit the REPL",
            handler=cmd_exit,
            aliases=["/quit", "/q"]
        ))

        self.register(Command(
            name="/expand",
            description="Expand task into requirements: /expand <task>",
            handler=cmd_expand,
            aliases=["/e", "/req"]
        ))

        # === Orchestrator Commands ===
        self.register(Command(
            name="/run",
            description="Run MDAP pipeline: /run <task>",
            handler=cmd_run,
            aliases=["/go", "/start"]
        ))

        self.register(Command(
            name="/pause",
            description="Pause pipeline execution",
            handler=cmd_pause,
            aliases=["/p"]
        ))

        self.register(Command(
            name="/resume",
            description="Resume paused pipeline",
            handler=cmd_resume,
            aliases=["/r"]
        ))

        self.register(Command(
            name="/cancel",
            description="Cancel pipeline and reset",
            handler=cmd_cancel,
            aliases=["/stop"]
        ))

        self.register(Command(
            name="/status",
            description="Show orchestrator status",
            handler=cmd_status,
            aliases=["/st"]
        ))

        self.register(Command(
            name="/explain",
            description="Explain current state: /explain [decision_id]",
            handler=cmd_explain,
            aliases=["/why"]
        ))

        self.register(Command(
            name="/history",
            description="Show decision history: /history [limit]",
            handler=cmd_history,
            aliases=["/hist"]
        ))

        self.register(Command(
            name="/resources",
            description="Show resource usage",
            handler=cmd_resources,
            aliases=["/res"]
        ))

        self.register(Command(
            name="/budget",
            description="Set budget: /budget tokens <n> | cost <n> | time <n>",
            handler=cmd_budget,
            aliases=[]
        ))

    def register(self, command: Command) -> None:
        """Registra um comando."""
        self._commands[command.name] = command
        for alias in command.aliases:
            self._commands[alias] = command

    def get_commands(self) -> dict[str, str]:
        """Retorna dict de comandos unicos para help."""
        seen = set()
        result = {}
        for cmd in self._commands.values():
            if cmd.name not in seen:
                seen.add(cmd.name)
                result[cmd.name] = cmd.description
        return result

    async def route(self, input_line: str) -> bool:
        """
        Tenta rotear input como comando.

        Args:
            input_line: Linha de input do usuario

        Returns:
            True se era um comando (processado), False se era chat
        """
        if not input_line.startswith("/"):
            return False

        parts = input_line.split(maxsplit=1)
        cmd_name = parts[0].lower()
        args = parts[1].split() if len(parts) > 1 else []

        if cmd_name in self._commands:
            command = self._commands[cmd_name]
            await command.handler(self.session, args)
            return True

        # Comando desconhecido
        from .ui import show_error
        show_error(
            self.session.console,
            f"Unknown command: {cmd_name}. Type /help for available commands."
        )
        return True


# === Command Handlers ===

async def cmd_help(session: "REPLSession", args: list[str]) -> None:
    """Handler para /help."""
    from .ui import show_help
    commands = session.commands.get_commands()
    show_help(session.console, commands)


async def cmd_clear(session: "REPLSession", args: list[str]) -> None:
    """Handler para /clear."""
    session.console.clear()
    session.history.clear()
    from .ui import show_welcome
    show_welcome(session.console, session.working_dir)


async def cmd_exit(session: "REPLSession", args: list[str]) -> None:
    """Handler para /exit."""
    session.console.print("\n[dim]Goodbye![/dim]")
    session.running = False


async def cmd_expand(session: "REPLSession", args: list[str]) -> None:
    """Handler para /expand."""
    if not args:
        from .ui import show_error
        show_error(session.console, "Usage: /expand <task description>")
        return

    task = " ".join(args)
    await session.handle_expand(task)


# === Orchestrator Command Handlers ===

async def cmd_run(session: "REPLSession", args: list[str]) -> None:
    """Handler para /run - executa pipeline MDAP."""
    if not args:
        from .ui import show_error
        show_error(session.console, "Usage: /run <task description>")
        return

    task = " ".join(args)
    await session.orch.run(task)


async def cmd_pause(session: "REPLSession", args: list[str]) -> None:
    """Handler para /pause."""
    await session.orch.pause()


async def cmd_resume(session: "REPLSession", args: list[str]) -> None:
    """Handler para /resume."""
    await session.orch.resume()


async def cmd_cancel(session: "REPLSession", args: list[str]) -> None:
    """Handler para /cancel."""
    await session.orch.cancel()


async def cmd_status(session: "REPLSession", args: list[str]) -> None:
    """Handler para /status."""
    session.orch.status()


async def cmd_explain(session: "REPLSession", args: list[str]) -> None:
    """Handler para /explain."""
    target = args[0] if args else ""
    session.orch.explain(target)


async def cmd_history(session: "REPLSession", args: list[str]) -> None:
    """Handler para /history."""
    limit = int(args[0]) if args else 10
    session.orch.history(limit)


async def cmd_resources(session: "REPLSession", args: list[str]) -> None:
    """Handler para /resources."""
    session.orch.show_resources()


async def cmd_budget(session: "REPLSession", args: list[str]) -> None:
    """Handler para /budget."""
    from .ui import show_error, show_info

    if not args:
        # Mostra budget atual
        session.orch.show_resources()
        return

    if len(args) < 2:
        show_error(session.console, "Usage: /budget tokens|cost|time <value>")
        return

    budget_type = args[0].lower()
    try:
        value = float(args[1])
    except ValueError:
        show_error(session.console, f"Invalid value: {args[1]}")
        return

    if budget_type == "tokens":
        session.orch.set_budget(max_tokens=int(value))
    elif budget_type == "cost":
        session.orch.set_budget(max_cost=value)
    elif budget_type == "time":
        session.orch.set_budget(max_time=value)
    else:
        show_error(session.console, f"Unknown budget type: {budget_type}. Use: tokens, cost, time")
