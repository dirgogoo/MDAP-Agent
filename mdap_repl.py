#!/usr/bin/env python3
"""
MDAP Agent REPL - Interactive CLI

Uma CLI interativa para trabalhar com projetos usando o MDAP Agent.
Similar ao Claude Code, permite chat continuo e iteracao sobre projetos.

Uso:
    python mdap_repl.py [working_directory]

Exemplos:
    python mdap_repl.py
    python mdap_repl.py ./my-project
    python mdap_repl.py C:\\Users\\myuser\\projects\\app
"""

import asyncio
import sys
from pathlib import Path

from rich.console import Console


def main():
    """Entry point do REPL."""
    console = Console()

    # Parse argumentos
    if len(sys.argv) > 1:
        if sys.argv[1] in ["-h", "--help"]:
            console.print(__doc__)
            return
        working_dir = sys.argv[1]
    else:
        working_dir = "."

    # Valida diretorio
    working_path = Path(working_dir).resolve()
    if not working_path.exists():
        console.print(f"[red]Error:[/red] Directory not found: {working_path}")
        sys.exit(1)

    if not working_path.is_dir():
        console.print(f"[red]Error:[/red] Not a directory: {working_path}")
        sys.exit(1)

    # Importa e executa REPL
    try:
        from mdap_cli.repl import REPLSession

        session = REPLSession(str(working_path))
        asyncio.run(session.run())

    except ImportError as e:
        console.print(f"[red]Error:[/red] Failed to import REPL module: {e}")
        console.print("[dim]Make sure you're running from the MDAP-Agent directory.[/dim]")
        sys.exit(1)

    except KeyboardInterrupt:
        console.print("\n[dim]Goodbye![/dim]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
