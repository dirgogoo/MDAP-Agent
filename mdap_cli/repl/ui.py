"""
UI Components para MDAP REPL

Componentes visuais usando Rich.
"""
import re
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.text import Text
from rich import box


def show_welcome(console: Console, working_dir: Path) -> None:
    """Mostra banner de boas-vindas."""
    welcome_text = Text()
    welcome_text.append("MDAP Agent REPL\n", style="bold blue")
    welcome_text.append("\n")
    welcome_text.append(f"Working directory: ", style="dim")
    welcome_text.append(f"{working_dir}\n", style="white")
    welcome_text.append("Type ", style="dim")
    welcome_text.append("/help", style="cyan")
    welcome_text.append(" for commands, or just start chatting.", style="dim")

    console.print(Panel(
        welcome_text,
        box=box.DOUBLE,
        border_style="blue",
        padding=(1, 2)
    ))
    console.print()


def show_user_message(console: Console, content: str) -> None:
    """Mostra mensagem do usuario."""
    # Não mostra nada - o input já foi mostrado pelo Prompt.ask()
    pass


def show_assistant_message(console: Console, content: str) -> None:
    """Mostra resposta do assistente com syntax highlight para codigo."""
    console.print()

    # Detecta blocos de codigo e renderiza com syntax highlight
    parts = _split_code_blocks(content)

    for part in parts:
        if part["type"] == "code":
            syntax = Syntax(
                part["content"],
                part["language"],
                theme="monokai",
                line_numbers=True,
                word_wrap=True
            )
            console.print(Panel(
                syntax,
                title=part["language"],
                border_style="green",
                box=box.ROUNDED
            ))
        else:
            # Texto normal - usa Markdown
            console.print(Markdown(part["content"]))


def show_error(console: Console, message: str) -> None:
    """Mostra mensagem de erro."""
    console.print(Panel(
        f"[bold red]Error:[/bold red] {message}",
        border_style="red",
        box=box.ROUNDED
    ))


def show_info(console: Console, message: str) -> None:
    """Mostra mensagem informativa."""
    console.print(f"[dim]{message}[/dim]")


def show_help(console: Console, commands: dict) -> None:
    """Mostra ajuda com comandos disponiveis."""
    help_text = Text()
    help_text.append("Available Commands:\n\n", style="bold")

    for cmd, desc in commands.items():
        help_text.append(f"  {cmd}", style="cyan")
        help_text.append(f"  {desc}\n", style="dim")

    help_text.append("\n")
    help_text.append("Or just type your message to chat with the assistant.", style="dim")

    console.print(Panel(
        help_text,
        title="Help",
        border_style="blue",
        box=box.ROUNDED
    ))


def show_question_header(console: Console, task: str, total: int) -> None:
    """Mostra header do questionário."""
    console.print()
    console.print(Panel(
        f"[bold cyan]Analisando:[/bold cyan] {task}\n\n"
        f"[dim]Tenho {total} perguntas para entender melhor os requisitos.\n"
        f"Responda ou use /skip para pular, /skipall para pular todas.[/dim]",
        border_style="cyan",
        box=box.ROUNDED
    ))


def show_question(
    console: Console,
    question,  # Question dataclass
    current: int,
    total: int
) -> None:
    """Mostra uma pergunta do questionário com opções."""
    console.print()

    # Header com progresso
    progress = f"[{current}/{total}]"
    category = f"[bold magenta]{question.category}[/bold magenta]"

    console.print(f"{progress} {category}")
    console.print(f"   [bold]{question.question}[/bold]")
    console.print(f"   [dim italic]({question.why})[/dim italic]")

    # Mostra opções se existirem
    if question.options:
        console.print()
        for opt in question.options:
            if opt.key == "custom":
                console.print(f"   [yellow]{opt.key})[/yellow] [dim]{opt.label}[/dim]")
            else:
                console.print(f"   [cyan]{opt.key})[/cyan] {opt.label}")
        console.print(f"   [dim]/skip para pular[/dim]")


def show_question_skipped(console: Console) -> None:
    """Mostra que a pergunta foi pulada."""
    console.print("   [dim]Pulada[/dim]")


def show_questionnaire_summary(
    console: Console,
    answered: int,
    skipped: int,
    total: int
) -> None:
    """Mostra resumo do questionário."""
    console.print()

    if answered > 0:
        console.print(Panel(
            f"[bold green]Coletei {answered} respostas![/bold green]\n"
            f"[dim]({skipped} perguntas puladas)[/dim]",
            border_style="green",
            box=box.ROUNDED
        ))
    else:
        console.print(Panel(
            "[yellow]Nenhuma resposta coletada.[/yellow]\n"
            "[dim]A expansão será feita com informações limitadas.[/dim]",
            border_style="yellow",
            box=box.ROUNDED
        ))


def show_requirements(console: Console, requirements: list[str]) -> None:
    """Mostra lista de requisitos expandidos."""
    console.print()
    console.print(Panel(
        "[bold blue]Requisitos Encontrados[/bold blue]",
        border_style="blue",
        box=box.DOUBLE
    ))

    for i, req in enumerate(requirements, 1):
        console.print(f"  [cyan]{i}.[/cyan] {req}")

    console.print()


def show_expanding(console: Console) -> None:
    """Mostra que está expandindo requisitos."""
    console.print()
    console.print("[dim]Expandindo requisitos...[/dim]")


def _split_code_blocks(content: str) -> list[dict]:
    """
    Separa texto em blocos de codigo e texto normal.

    Detecta blocos ```language ... ```
    """
    parts = []
    pattern = r"```(\w*)\n?(.*?)```"

    last_end = 0
    for match in re.finditer(pattern, content, re.DOTALL):
        # Texto antes do bloco de codigo
        if match.start() > last_end:
            text = content[last_end:match.start()].strip()
            if text:
                parts.append({"type": "text", "content": text})

        # Bloco de codigo
        language = match.group(1) or "python"
        code = match.group(2).strip()
        parts.append({"type": "code", "language": language, "content": code})

        last_end = match.end()

    # Texto depois do ultimo bloco
    if last_end < len(content):
        text = content[last_end:].strip()
        if text:
            parts.append({"type": "text", "content": text})

    # Se nao encontrou blocos, retorna tudo como texto
    if not parts:
        parts.append({"type": "text", "content": content})

    return parts
