"""
Prompts Interativos para MDAP CLI

Checkpoints que permitem ao usuario validar e modificar decisoes.
"""

from typing import Optional
from rich.console import Console
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.text import Text
from rich import box


class InteractivePrompt:
    """
    Gerencia checkpoints interativos durante o pipeline MDAP.

    Permite ao usuario:
    - Aprovar/rejeitar requisitos
    - Modificar lista de funcoes
    - Regenerar codigo
    - Editar codigo manualmente
    """

    def __init__(self, console: Console = None):
        self.console = console or Console()

    def ask_expand_approval(self, requisitos: list[str]) -> tuple[str, Optional[list[str]]]:
        """
        Checkpoint apos EXPAND.

        Retorna:
            (acao, dados_modificados)
            acao: "continuar", "adicionar", "remover", "refazer"
        """
        self.console.print()
        self.console.print(Panel(
            "[bold cyan]CHECKPOINT: Requisitos Encontrados[/bold cyan]",
            box=box.DOUBLE
        ))

        # Lista requisitos
        table = Table(show_header=False, box=None, padding=(0, 1))
        for i, req in enumerate(requisitos, 1):
            table.add_row(f"[cyan]{i}.[/cyan]", req)

        self.console.print(Panel(table, title=f"{len(requisitos)} Requisitos", border_style="green"))
        self.console.print()

        # Opcoes
        self.console.print("[bold]Opcoes:[/bold]")
        self.console.print("  [1] Continuar com estes requisitos")
        self.console.print("  [2] Adicionar mais requisitos")
        self.console.print("  [3] Remover alguns requisitos")
        self.console.print("  [4] Refazer EXPAND")
        self.console.print()

        choice = Prompt.ask(
            "Escolha",
            choices=["1", "2", "3", "4"],
            default="1"
        )

        if choice == "1":
            return ("continuar", None)

        elif choice == "2":
            self.console.print("\n[dim]Digite requisitos adicionais (linha vazia para terminar):[/dim]")
            novos = []
            while True:
                req = Prompt.ask("", default="")
                if not req:
                    break
                novos.append(req)
            return ("adicionar", novos)

        elif choice == "3":
            indices = Prompt.ask(
                "Numeros dos requisitos a remover (separados por virgula)",
                default=""
            )
            if indices:
                try:
                    nums = [int(x.strip()) - 1 for x in indices.split(",")]
                    return ("remover", nums)
                except ValueError:
                    self.console.print("[red]Numeros invalidos[/red]")
                    return ("continuar", None)
            return ("continuar", None)

        elif choice == "4":
            return ("refazer", None)

        return ("continuar", None)

    def ask_decompose_approval(self, funcoes: list[str]) -> tuple[str, Optional[any]]:
        """
        Checkpoint apos DECOMPOSE.

        Retorna:
            (acao, dados_modificados)
            acao: "continuar", "adicionar", "remover", "renomear", "refazer"
        """
        self.console.print()
        self.console.print(Panel(
            "[bold cyan]CHECKPOINT: Funcoes Planejadas[/bold cyan]",
            box=box.DOUBLE
        ))

        # Lista funcoes
        for i, func in enumerate(funcoes, 1):
            self.console.print(f"  [cyan]{i}.[/cyan] [green]{func}[/green]")

        self.console.print()

        # Opcoes
        self.console.print("[bold]Opcoes:[/bold]")
        self.console.print("  [1] Aprovar e gerar codigo")
        self.console.print("  [2] Adicionar funcao")
        self.console.print("  [3] Remover funcao")
        self.console.print("  [4] Renomear funcao")
        self.console.print("  [5] Refazer DECOMPOSE")
        self.console.print()

        choice = Prompt.ask(
            "Escolha",
            choices=["1", "2", "3", "4", "5"],
            default="1"
        )

        if choice == "1":
            return ("continuar", None)

        elif choice == "2":
            nova = Prompt.ask("Assinatura da nova funcao")
            if nova:
                return ("adicionar", nova)
            return ("continuar", None)

        elif choice == "3":
            idx = IntPrompt.ask("Numero da funcao a remover", default=0)
            if 1 <= idx <= len(funcoes):
                return ("remover", idx - 1)
            return ("continuar", None)

        elif choice == "4":
            idx = IntPrompt.ask("Numero da funcao a renomear", default=0)
            if 1 <= idx <= len(funcoes):
                nova = Prompt.ask("Nova assinatura")
                if nova:
                    return ("renomear", (idx - 1, nova))
            return ("continuar", None)

        elif choice == "5":
            return ("refazer", None)

        return ("continuar", None)

    def ask_generate_approval(
        self,
        funcao: str,
        codigo: str,
        votacao_info: Optional[dict] = None
    ) -> tuple[str, Optional[str]]:
        """
        Checkpoint apos cada GENERATE.

        Retorna:
            (acao, codigo_modificado)
            acao: "continuar", "regenerar", "editar", "pular"
        """
        self.console.print()
        self.console.print(Panel(
            f"[bold cyan]CHECKPOINT: Codigo Gerado[/bold cyan]",
            box=box.DOUBLE
        ))

        # Info da funcao
        self.console.print(f"[bold]Funcao:[/bold] [green]{funcao}[/green]")
        self.console.print()

        # Codigo com syntax highlight
        # Remove marcadores de codigo se existirem
        codigo_limpo = codigo
        if codigo_limpo.startswith("```python"):
            codigo_limpo = codigo_limpo[9:]
        if codigo_limpo.startswith("```"):
            codigo_limpo = codigo_limpo[3:]
        if codigo_limpo.endswith("```"):
            codigo_limpo = codigo_limpo[:-3]
        codigo_limpo = codigo_limpo.strip()

        syntax = Syntax(
            codigo_limpo,
            "python",
            theme="monokai",
            line_numbers=True,
            word_wrap=True
        )
        self.console.print(Panel(syntax, title="Codigo", border_style="green"))

        # Info de votacao
        if votacao_info:
            info_text = Text()
            info_text.append("Votacao: ", style="bold")
            info_text.append(f"{votacao_info.get('samples', '?')} candidatos", style="cyan")
            info_text.append(", ", style="dim")
            info_text.append(f"{votacao_info.get('grupos', '?')} grupos", style="yellow")
            info_text.append(", ", style="dim")
            votos = votacao_info.get('votos', {})
            info_text.append(f"{votos}", style="green")
            self.console.print(info_text)

        self.console.print()

        # Opcoes
        self.console.print("[bold]Opcoes:[/bold]")
        self.console.print("  [Enter/1] Aprovar e continuar")
        self.console.print("  [2] Regenerar (nova votacao)")
        self.console.print("  [3] Editar codigo manualmente")
        self.console.print("  [4] Pular esta funcao")
        self.console.print()

        choice = Prompt.ask(
            "Escolha",
            choices=["", "1", "2", "3", "4"],
            default=""
        )

        if choice in ["", "1"]:
            return ("continuar", None)

        elif choice == "2":
            return ("regenerar", None)

        elif choice == "3":
            self.console.print("\n[dim]Cole o codigo editado (linha vazia + 'FIM' para terminar):[/dim]")
            linhas = []
            while True:
                linha = input()
                if linha.strip() == "FIM":
                    break
                linhas.append(linha)
            codigo_editado = "\n".join(linhas)
            if codigo_editado.strip():
                return ("editar", codigo_editado)
            return ("continuar", None)

        elif choice == "4":
            return ("pular", None)

        return ("continuar", None)

    def ask_final_approval(self, resultado: dict) -> bool:
        """
        Checkpoint final antes de salvar.

        Retorna:
            True se aprovado, False para revisar
        """
        self.console.print()
        self.console.print(Panel(
            "[bold cyan]CHECKPOINT: Resultado Final[/bold cyan]",
            box=box.DOUBLE
        ))

        # Resumo
        table = Table(show_header=False, box=None)
        table.add_row("Tarefa:", resultado.get("tarefa", ""))
        table.add_row("Requisitos:", str(len(resultado.get("requisitos", []))))
        table.add_row("Funcoes:", str(len(resultado.get("funcoes", []))))
        table.add_row("Codigos:", str(len(resultado.get("codigos", {}))))

        self.console.print(Panel(table, title="Resumo", border_style="green"))
        self.console.print()

        return Confirm.ask("Salvar resultado?", default=True)

    def show_code_preview(self, codigos: dict[str, str]):
        """Mostra preview de todos os codigos gerados"""
        self.console.print()
        self.console.print(Panel(
            "[bold cyan]Codigo Gerado[/bold cyan]",
            box=box.DOUBLE
        ))

        for funcao, codigo in codigos.items():
            self.console.print(f"\n[bold green]# {funcao}[/bold green]")

            # Limpa marcadores
            codigo_limpo = codigo
            if codigo_limpo.startswith("```python"):
                codigo_limpo = codigo_limpo[9:]
            if codigo_limpo.startswith("```"):
                codigo_limpo = codigo_limpo[3:]
            if codigo_limpo.endswith("```"):
                codigo_limpo = codigo_limpo[:-3]
            codigo_limpo = codigo_limpo.strip()

            syntax = Syntax(
                codigo_limpo,
                "python",
                theme="monokai",
                line_numbers=True
            )
            self.console.print(syntax)

    def ask_continue(self, message: str = "Continuar?") -> bool:
        """Pergunta simples de continuacao"""
        return Confirm.ask(message, default=True)

    def show_error(self, error: str):
        """Mostra erro"""
        self.console.print(Panel(
            f"[bold red]ERRO:[/bold red] {error}",
            border_style="red"
        ))

    def show_success(self, message: str):
        """Mostra sucesso"""
        self.console.print(Panel(
            f"[bold green]OK:[/bold green] {message}",
            border_style="green"
        ))
