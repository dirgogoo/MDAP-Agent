"""
Test Runner - Executa testes

Operação determinística (não usa MDAP).
"""
import asyncio
import subprocess
import os
from typing import Optional
from dataclasses import dataclass

from ..types import ExecutionResult
from .tools import Tool, ToolType, register_tool


@dataclass
class TestResult:
    """Resultado de execução de testes."""
    passed: int
    failed: int
    errors: int
    skipped: int
    output: str
    duration_seconds: float


class PytestTool(Tool):
    """Executa testes com pytest."""

    @property
    def name(self) -> str:
        return "pytest"

    @property
    def tool_type(self) -> ToolType:
        return ToolType.TEST

    async def execute(self, **kwargs) -> ExecutionResult:
        path = kwargs.get("path", ".")
        pattern = kwargs.get("pattern", "")
        verbose = kwargs.get("verbose", False)
        timeout = int(kwargs.get("timeout", 60))

        cmd = ["python", "-m", "pytest"]

        if pattern:
            cmd.append(pattern)
        else:
            cmd.append(path)

        if verbose:
            cmd.append("-v")

        cmd.extend(["--tb=short", "-q"])

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=path if os.path.isdir(path) else None,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                return ExecutionResult(
                    success=False,
                    error=f"Tests timed out after {timeout}s",
                )

            output = stdout.decode() + stderr.decode()

            # Parse resultado (simplificado)
            passed = failed = errors = 0
            for line in output.split("\n"):
                if "passed" in line:
                    try:
                        passed = int(line.split()[0])
                    except:
                        pass
                if "failed" in line:
                    try:
                        failed = int(line.split()[0])
                    except:
                        pass
                if "error" in line:
                    try:
                        errors = int(line.split()[0])
                    except:
                        pass

            success = process.returncode == 0

            return ExecutionResult(
                success=success,
                output=output,
                data=TestResult(
                    passed=passed,
                    failed=failed,
                    errors=errors,
                    skipped=0,
                    output=output,
                    duration_seconds=0,
                ),
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"Failed to run tests: {e}",
            )


class PythonCheckTool(Tool):
    """Verifica sintaxe Python."""

    @property
    def name(self) -> str:
        return "python_check"

    @property
    def tool_type(self) -> ToolType:
        return ToolType.TEST

    async def execute(self, **kwargs) -> ExecutionResult:
        code = kwargs.get("code", "")
        path = kwargs.get("path", "")

        if path and not code:
            try:
                with open(path, "r") as f:
                    code = f.read()
            except Exception as e:
                return ExecutionResult(
                    success=False,
                    error=f"Failed to read {path}: {e}",
                )

        if not code:
            return ExecutionResult(
                success=False,
                error="No code to check",
            )

        try:
            compile(code, "<string>", "exec")
            return ExecutionResult(
                success=True,
                output="Syntax OK",
            )
        except SyntaxError as e:
            return ExecutionResult(
                success=False,
                output=f"Syntax error at line {e.lineno}: {e.msg}",
                error=str(e),
            )


class ImportCheckTool(Tool):
    """Verifica se imports são válidos."""

    @property
    def name(self) -> str:
        return "import_check"

    @property
    def tool_type(self) -> ToolType:
        return ToolType.TEST

    async def execute(self, **kwargs) -> ExecutionResult:
        module = kwargs.get("module", "")

        if not module:
            return ExecutionResult(
                success=False,
                error="No module specified",
            )

        try:
            process = await asyncio.create_subprocess_exec(
                "python", "-c", f"import {module}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=10,
            )

            if process.returncode == 0:
                return ExecutionResult(
                    success=True,
                    output=f"Module '{module}' imports successfully",
                )
            else:
                return ExecutionResult(
                    success=False,
                    output=stderr.decode(),
                    error=f"Failed to import '{module}'",
                )

        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"Import check failed: {e}",
            )


def init_test_tools():
    """Inicializa e registra ferramentas de teste."""
    register_tool(PytestTool())
    register_tool(PythonCheckTool())
    register_tool(ImportCheckTool())
