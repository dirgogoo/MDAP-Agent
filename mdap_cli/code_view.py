"""
Visualizacao de Codigo para MDAP CLI

Renderiza codigo com syntax highlight estilo Claude Code.
"""

from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
from rich.text import Text
from rich import box


def clean_code(code: str) -> str:
    """Remove marcadores de codigo markdown"""
    code = code.strip()

    # Remove ```python ou ```
    if code.startswith("```python"):
        code = code[9:]
    elif code.startswith("```"):
        code = code[3:]

    # Remove ``` final
    if code.endswith("```"):
        code = code[:-3]

    return code.strip()


def render_code(
    code: str,
    language: str = "python",
    title: str = "Codigo",
    line_numbers: bool = True,
    theme: str = "monokai"
) -> Panel:
    """
    Renderiza codigo com syntax highlight em um Panel.

    Args:
        code: Codigo fonte
        language: Linguagem para highlight
        title: Titulo do panel
        line_numbers: Mostrar numeros de linha
        theme: Tema do highlight (monokai, dracula, github-dark, etc)

    Returns:
        Panel do Rich com codigo formatado
    """
    code_clean = clean_code(code)

    syntax = Syntax(
        code_clean,
        language,
        theme=theme,
        line_numbers=line_numbers,
        word_wrap=True
    )

    return Panel(
        syntax,
        title=title,
        border_style="green",
        box=box.ROUNDED
    )


def render_code_diff(
    old_code: str,
    new_code: str,
    language: str = "python"
) -> Panel:
    """
    Renderiza diff entre dois codigos.

    TODO: Implementar diff real
    """
    old_clean = clean_code(old_code)
    new_clean = clean_code(new_code)

    # Por ora, mostra os dois lado a lado
    content = Text()
    content.append("OLD:\n", style="red")
    content.append(old_clean + "\n\n")
    content.append("NEW:\n", style="green")
    content.append(new_clean)

    return Panel(content, title="Diff", border_style="yellow")


def render_function_signature(signature: str) -> Text:
    """Renderiza assinatura de funcao com cores"""
    text = Text()

    # Parse simples da assinatura
    if signature.startswith("def "):
        text.append("def ", style="keyword")
        rest = signature[4:]

        # Nome da funcao
        if "(" in rest:
            name, params = rest.split("(", 1)
            text.append(name, style="function")
            text.append("(", style="punctuation")

            # Parametros
            if ")" in params:
                params_str, return_part = params.split(")", 1)

                # Processa parametros
                for i, param in enumerate(params_str.split(",")):
                    if i > 0:
                        text.append(", ", style="punctuation")
                    param = param.strip()
                    if ":" in param:
                        pname, ptype = param.split(":", 1)
                        text.append(pname.strip(), style="parameter")
                        text.append(": ", style="punctuation")
                        text.append(ptype.strip(), style="type")
                    else:
                        text.append(param, style="parameter")

                text.append(")", style="punctuation")

                # Return type
                if "->" in return_part:
                    text.append(" -> ", style="punctuation")
                    return_type = return_part.split("->")[1].strip().rstrip(":")
                    text.append(return_type, style="type")
        else:
            text.append(rest)
    else:
        text.append(signature)

    return text


def print_code_block(
    console: Console,
    code: str,
    title: str = None,
    language: str = "python"
):
    """
    Imprime bloco de codigo no console.

    Args:
        console: Console do Rich
        code: Codigo fonte
        title: Titulo opcional
        language: Linguagem para highlight
    """
    panel = render_code(code, language=language, title=title or "")
    console.print(panel)


def print_function_list(
    console: Console,
    functions: list[str],
    title: str = "Funcoes"
):
    """
    Imprime lista de funcoes com formatacao.

    Args:
        console: Console do Rich
        functions: Lista de assinaturas
        title: Titulo da lista
    """
    console.print(f"\n[bold]{title}:[/bold]")
    for i, func in enumerate(functions, 1):
        sig_text = render_function_signature(func)
        console.print(f"  [cyan]{i}.[/cyan] ", end="")
        console.print(sig_text)


class CodeViewer:
    """
    Visualizador de codigo interativo.

    Permite navegar por multiplos arquivos/funcoes.
    """

    def __init__(self, console: Console = None):
        self.console = console or Console()
        self.codes: dict[str, str] = {}

    def add_code(self, name: str, code: str):
        """Adiciona codigo ao viewer"""
        self.codes[name] = code

    def show(self, name: str = None):
        """Mostra codigo especifico ou todos"""
        if name:
            if name in self.codes:
                print_code_block(self.console, self.codes[name], title=name)
            else:
                self.console.print(f"[red]Codigo '{name}' nao encontrado[/red]")
        else:
            for name, code in self.codes.items():
                print_code_block(self.console, code, title=name)
                self.console.print()

    def show_all(self):
        """Mostra todos os codigos"""
        self.show()

    def list_codes(self):
        """Lista codigos disponiveis"""
        self.console.print("\n[bold]Codigos disponiveis:[/bold]")
        for i, name in enumerate(self.codes.keys(), 1):
            self.console.print(f"  {i}. {name}")

    def export_to_file(self, filepath: str):
        """Exporta todos os codigos para um arquivo"""
        with open(filepath, "w", encoding="utf-8") as f:
            for name, code in self.codes.items():
                f.write(f"# {name}\n")
                f.write(clean_code(code))
                f.write("\n\n")

        self.console.print(f"[green]Codigo exportado para: {filepath}[/green]")
