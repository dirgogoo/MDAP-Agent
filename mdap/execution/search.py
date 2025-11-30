"""
Search Tools - Busca em código

Operações determinísticas de busca (não usam MDAP).
"""
import os
import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from ..types import ExecutionResult
from .tools import Tool, ToolType, register_tool


@dataclass
class SearchMatch:
    """Um match de busca."""
    file: str
    line: int
    content: str
    context_before: list[str]
    context_after: list[str]


class GrepTool(Tool):
    """Busca por padrão em arquivos."""

    @property
    def name(self) -> str:
        return "grep"

    @property
    def tool_type(self) -> ToolType:
        return ToolType.SEARCH

    def validate_args(self, **kwargs) -> Optional[str]:
        if "pattern" not in kwargs:
            return "Missing 'pattern' argument"
        return None

    async def execute(self, **kwargs) -> ExecutionResult:
        pattern = kwargs["pattern"]
        path = kwargs.get("path", ".")
        file_pattern = kwargs.get("files", "*.py")
        context = int(kwargs.get("context", 2))
        max_matches = int(kwargs.get("max", 50))

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return ExecutionResult(
                success=False,
                error=f"Invalid regex pattern: {e}",
            )

        matches: list[SearchMatch] = []

        try:
            p = Path(path)
            for file_path in p.rglob(file_pattern):
                if len(matches) >= max_matches:
                    break

                if not file_path.is_file():
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                except:
                    continue

                for i, line in enumerate(lines):
                    if regex.search(line):
                        matches.append(SearchMatch(
                            file=str(file_path),
                            line=i + 1,
                            content=line.rstrip(),
                            context_before=[
                                l.rstrip() for l in lines[max(0, i - context):i]
                            ],
                            context_after=[
                                l.rstrip() for l in lines[i + 1:i + 1 + context]
                            ],
                        ))

                        if len(matches) >= max_matches:
                            break

            # Formata output
            output_lines = []
            for m in matches:
                output_lines.append(f"{m.file}:{m.line}: {m.content}")

            return ExecutionResult(
                success=True,
                output="\n".join(output_lines) if output_lines else "No matches found",
                data=[{
                    "file": m.file,
                    "line": m.line,
                    "content": m.content,
                    "context_before": m.context_before,
                    "context_after": m.context_after,
                } for m in matches],
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"Search failed: {e}",
            )


class GlobTool(Tool):
    """Encontra arquivos por padrão glob."""

    @property
    def name(self) -> str:
        return "glob"

    @property
    def tool_type(self) -> ToolType:
        return ToolType.SEARCH

    async def execute(self, **kwargs) -> ExecutionResult:
        pattern = kwargs.get("pattern", "**/*.py")
        path = kwargs.get("path", ".")
        max_files = int(kwargs.get("max", 100))

        try:
            p = Path(path)
            files = list(p.glob(pattern))[:max_files]

            file_list = []
            for f in files:
                if f.is_file():
                    file_list.append({
                        "path": str(f),
                        "size": f.stat().st_size,
                        "modified": f.stat().st_mtime,
                    })

            return ExecutionResult(
                success=True,
                output=f"Found {len(file_list)} files matching '{pattern}'",
                data=file_list,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"Glob failed: {e}",
            )


class FindFunctionTool(Tool):
    """Encontra definição de função/classe."""

    @property
    def name(self) -> str:
        return "find_function"

    @property
    def tool_type(self) -> ToolType:
        return ToolType.SEARCH

    async def execute(self, **kwargs) -> ExecutionResult:
        name = kwargs.get("name", "")
        path = kwargs.get("path", ".")
        file_pattern = kwargs.get("files", "*.py")

        if not name:
            return ExecutionResult(
                success=False,
                error="Missing 'name' argument",
            )

        # Padrões para Python
        patterns = [
            rf"^\s*def\s+{re.escape(name)}\s*\(",
            rf"^\s*async\s+def\s+{re.escape(name)}\s*\(",
            rf"^\s*class\s+{re.escape(name)}\s*[:\(]",
        ]

        matches = []

        try:
            p = Path(path)
            for file_path in p.rglob(file_pattern):
                if not file_path.is_file():
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                except:
                    continue

                for i, line in enumerate(lines):
                    for pattern in patterns:
                        if re.match(pattern, line):
                            # Pega contexto (próximas 10 linhas)
                            body = lines[i:i + 15]
                            matches.append({
                                "file": str(file_path),
                                "line": i + 1,
                                "definition": line.rstrip(),
                                "body": "".join(body),
                            })
                            break

            if matches:
                return ExecutionResult(
                    success=True,
                    output=f"Found {len(matches)} definition(s) of '{name}'",
                    data=matches,
                )
            else:
                return ExecutionResult(
                    success=True,
                    output=f"No definitions found for '{name}'",
                    data=[],
                )

        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"Find function failed: {e}",
            )


def init_search_tools():
    """Inicializa e registra ferramentas de busca."""
    register_tool(GrepTool())
    register_tool(GlobTool())
    register_tool(FindFunctionTool())
