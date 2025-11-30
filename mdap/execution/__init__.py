"""Execution Layer - Ferramentas determinísticas."""
from .tools import (
    Tool,
    ToolType,
    ToolRegistry,
    register_tool,
    get_tool,
    get_registry,
    execute_tool,
)
from .file_ops import ReadTool, WriteTool, init_file_tools
from .search import GrepTool, GlobTool, FindFunctionTool, init_search_tools
from .test_runner import PytestTool, PythonCheckTool, init_test_tools


def init_all_tools():
    """Inicializa todas as ferramentas."""
    init_file_tools()
    init_search_tools()
    init_test_tools()


__all__ = [
    "Tool",
    "ToolType",
    "ToolRegistry",
    "register_tool",
    "get_tool",
    "get_registry",
    "execute_tool",
    "init_all_tools",
    "ReadTool",
    "WriteTool",
    "GrepTool",
    "GlobTool",
    "FindFunctionTool",
    "PytestTool",
    "PythonCheckTool",
]
