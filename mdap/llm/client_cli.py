"""
Claude CLI Client - Usa Claude Code CLI em modo headless

Ao invés de chamar a API HTTP, executa:
  claude --print "prompt"

Útil para testar localmente sem gastar tokens da API.
"""
import asyncio
import subprocess
import json
import os
from typing import Optional
from dataclasses import dataclass

from ..types import MDAPConfig


@dataclass
class LLMResponse:
    """Resposta do LLM."""
    content: str
    tokens_input: int
    tokens_output: int
    model: str
    stop_reason: str

    @property
    def tokens_total(self) -> int:
        return self.tokens_input + self.tokens_output


class ClaudeCLIClient:
    """Cliente que usa Claude Code CLI em modo headless."""

    def __init__(self, config: Optional[MDAPConfig] = None):
        self.config = config or MDAPConfig()
        self._call_count = 0

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
    ) -> LLMResponse:
        """
        Gera resposta usando Claude CLI.

        Args:
            prompt: Mensagem do usuário
            system: System prompt (será prefixado)
            temperature: Ignorado no CLI
            max_tokens: Ignorado no CLI
            model: Ignorado no CLI (usa o default do Claude Code)

        Returns:
            LLMResponse com conteúdo
        """
        self._call_count += 1

        # Executa claude CLI (system é combinado internamente)
        try:
            result = await self._run_claude_cli(prompt, system)

            # Estima tokens (aproximação)
            tokens_in = (len(prompt) + len(system or "")) // 4
            tokens_out = len(result) // 4

            return LLMResponse(
                content=result,
                tokens_input=tokens_in,
                tokens_output=tokens_out,
                model="claude-cli",
                stop_reason="end_turn",
            )

        except Exception as e:
            return LLMResponse(
                content=f"Error: {e}",
                tokens_input=0,
                tokens_output=0,
                model="claude-cli",
                stop_reason="error",
            )

    async def _run_claude_cli(self, prompt: str, system: str = "") -> str:
        """Executa o CLI do Claude Code."""
        import platform
        import tempfile

        # Combina system + prompt se necessário
        full_prompt = prompt
        if system:
            full_prompt = f"{system}\n\n{prompt}"

        # No Windows, precisa usar cmd.exe para encontrar claude no PATH
        if platform.system() == "Windows":
            cmd = ["cmd", "/c", "claude", "--print", full_prompt]
        else:
            cmd = ["claude", "--print", full_prompt]

        # Usa diretório temp para evitar ler CLAUDE.md do projeto
        temp_dir = tempfile.gettempdir()

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=temp_dir,  # Diretório neutro
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=120,  # 2 minutos timeout
            )

            if process.returncode == 0:
                return stdout.decode("utf-8").strip()
            else:
                error = stderr.decode("utf-8").strip()
                raise RuntimeError(f"Claude CLI error: {error}")

        except asyncio.TimeoutError:
            process.kill()
            raise RuntimeError("Claude CLI timeout")

    async def generate_code(
        self,
        specification: str,
        context: str = "",
        language: str = "python",
    ) -> LLMResponse:
        """
        Gera código baseado em especificação.
        """
        # Prompt simples e direto
        ctx = f" Contexto: {context}" if context else ""
        prompt = f"{specification}{ctx} Escreva apenas o codigo {language}, sem explicacao."

        return await self.generate(prompt=prompt)

    async def compare_semantic(
        self,
        code_a: str,
        code_b: str,
        context: str = "",
    ) -> bool:
        """
        Compara dois códigos semanticamente.
        """
        # Prompt em linha única (CLI não lida bem com multilinhas)
        a = code_a.replace('\n', ' ').strip()
        b = code_b.replace('\n', ' ').strip()
        prompt = f"Estes dois codigos fazem a mesma coisa? Codigo A: {a} -- Codigo B: {b} -- Responda apenas YES ou NO."

        response = await self.generate(prompt=prompt)
        answer = response.content.strip().upper()
        return "YES" in answer or "SIM" in answer

    async def close(self):
        """Nada a fechar no CLI."""
        pass

    @property
    def call_count(self) -> int:
        """Número de chamadas feitas."""
        return self._call_count


# Factory para escolher entre API e CLI
def get_client(
    use_cli: bool = False,
    config: Optional[MDAPConfig] = None
):
    """
    Retorna cliente apropriado.

    Args:
        use_cli: Se True, usa CLI. Se False, usa API.
        config: Configuração MDAP

    Returns:
        ClaudeCLIClient ou ClaudeClient
    """
    if use_cli:
        return ClaudeCLIClient(config)
    else:
        from .client import ClaudeClient
        return ClaudeClient(config)
