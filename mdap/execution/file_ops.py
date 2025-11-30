"""
File Operations - READ e WRITE

Operações determinísticas de arquivo (não usam MDAP).
"""
import os
from pathlib import Path
from typing import Optional

from ..types import ExecutionResult
from .tools import Tool, ToolType, register_tool


class ReadTool(Tool):
    """Lê conteúdo de arquivo."""

    @property
    def name(self) -> str:
        return "read"

    @property
    def tool_type(self) -> ToolType:
        return ToolType.READ

    def validate_args(self, **kwargs) -> Optional[str]:
        path = kwargs.get("path")
        if not path:
            return "Missing 'path' argument"
        if not os.path.exists(path):
            return f"File not found: {path}"
        return None

    async def execute(self, **kwargs) -> ExecutionResult:
        path = kwargs["path"]

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            return ExecutionResult(
                success=True,
                output=f"Read {len(content)} bytes from {path}",
                data=content,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"Failed to read {path}: {e}",
            )


class WriteTool(Tool):
    """Escreve conteúdo em arquivo."""

    @property
    def name(self) -> str:
        return "write"

    @property
    def tool_type(self) -> ToolType:
        return ToolType.WRITE

    def validate_args(self, **kwargs) -> Optional[str]:
        if "path" not in kwargs:
            return "Missing 'path' argument"
        if "content" not in kwargs:
            return "Missing 'content' argument"
        return None

    async def execute(self, **kwargs) -> ExecutionResult:
        path = kwargs["path"]
        content = kwargs["content"]
        create_dirs = kwargs.get("create_dirs", True)

        try:
            if create_dirs:
                Path(path).parent.mkdir(parents=True, exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            return ExecutionResult(
                success=True,
                output=f"Wrote {len(content)} bytes to {path}",
                data={"path": path, "bytes": len(content)},
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"Failed to write {path}: {e}",
            )


class AppendTool(Tool):
    """Adiciona conteúdo ao final de arquivo."""

    @property
    def name(self) -> str:
        return "append"

    @property
    def tool_type(self) -> ToolType:
        return ToolType.WRITE

    async def execute(self, **kwargs) -> ExecutionResult:
        path = kwargs["path"]
        content = kwargs["content"]

        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(content)

            return ExecutionResult(
                success=True,
                output=f"Appended {len(content)} bytes to {path}",
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"Failed to append to {path}: {e}",
            )


class ListDirTool(Tool):
    """Lista conteúdo de diretório."""

    @property
    def name(self) -> str:
        return "ls"

    @property
    def tool_type(self) -> ToolType:
        return ToolType.READ

    async def execute(self, **kwargs) -> ExecutionResult:
        path = kwargs.get("path", ".")
        pattern = kwargs.get("pattern", "*")

        try:
            p = Path(path)
            if not p.exists():
                return ExecutionResult(
                    success=False,
                    error=f"Path not found: {path}",
                )

            files = list(p.glob(pattern))
            file_list = [str(f.relative_to(p)) for f in files]

            return ExecutionResult(
                success=True,
                output=f"Found {len(files)} items in {path}",
                data=file_list,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"Failed to list {path}: {e}",
            )


# Registra ferramentas
def init_file_tools():
    """Inicializa e registra ferramentas de arquivo."""
    register_tool(ReadTool())
    register_tool(WriteTool())
    register_tool(AppendTool())
    register_tool(ListDirTool())
