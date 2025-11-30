"""
Tools Interface - Base para ferramentas de execução

Ferramentas de execução são DETERMINÍSTICAS (não usam MDAP):
- READ: ler arquivos
- SEARCH: buscar código
- TEST: rodar testes
- APPLY: aplicar edições
"""
from abc import ABC, abstractmethod
from typing import Any, Optional
from enum import Enum

from ..types import ExecutionResult, Step


class ToolType(Enum):
    """Tipos de ferramentas disponíveis."""
    READ = "read"
    WRITE = "write"
    SEARCH = "search"
    TEST = "test"
    APPLY = "apply"


class Tool(ABC):
    """Interface base para ferramentas."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Nome da ferramenta."""
        pass

    @property
    @abstractmethod
    def tool_type(self) -> ToolType:
        """Tipo da ferramenta."""
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> ExecutionResult:
        """
        Executa a ferramenta.

        Returns:
            ExecutionResult com sucesso/falha e dados
        """
        pass

    def validate_args(self, **kwargs) -> Optional[str]:
        """
        Valida argumentos. Retorna mensagem de erro ou None.
        """
        return None


class ToolRegistry:
    """Registro de ferramentas disponíveis."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Registra uma ferramenta."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """Retorna ferramenta pelo nome."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """Lista nomes de ferramentas registradas."""
        return list(self._tools.keys())

    def get_by_type(self, tool_type: ToolType) -> list[Tool]:
        """Retorna ferramentas de um tipo."""
        return [t for t in self._tools.values() if t.tool_type == tool_type]


# Registry global
_registry = ToolRegistry()


def register_tool(tool: Tool) -> None:
    """Registra ferramenta no registry global."""
    _registry.register(tool)


def get_tool(name: str) -> Optional[Tool]:
    """Obtém ferramenta do registry global."""
    return _registry.get(name)


def get_registry() -> ToolRegistry:
    """Retorna registry global."""
    return _registry


async def execute_tool(step: Step) -> ExecutionResult:
    """
    Executa ferramenta baseado no step.

    Args:
        step: Step com action especificando ferramenta

    Returns:
        ExecutionResult
    """
    if not step.action:
        return ExecutionResult(
            success=False,
            error="Step has no action specified",
        )

    # Parse action: "tool_name:arg1:arg2" ou JSON
    parts = step.action.split(":", 1)
    tool_name = parts[0]
    args_str = parts[1] if len(parts) > 1 else ""

    tool = get_tool(tool_name)
    if not tool:
        return ExecutionResult(
            success=False,
            error=f"Unknown tool: {tool_name}",
        )

    # Parse args (simples por agora)
    kwargs = {}
    if args_str:
        if "=" in args_str:
            for pair in args_str.split(","):
                key, val = pair.split("=", 1)
                kwargs[key.strip()] = val.strip()
        else:
            kwargs["path"] = args_str  # default para paths

    # Valida
    validation_error = tool.validate_args(**kwargs)
    if validation_error:
        return ExecutionResult(
            success=False,
            error=validation_error,
        )

    # Executa
    try:
        return await tool.execute(**kwargs)
    except Exception as e:
        return ExecutionResult(
            success=False,
            error=str(e),
        )
