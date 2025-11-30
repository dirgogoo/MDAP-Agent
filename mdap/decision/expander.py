"""
Expander - Gera requisitos atômicos

EXPANSÃO (bottom-up): descobre requisitos que não estavam explícitos.
Diferente de DECOMPOSIÇÃO (top-down) que divide algo grande.

Exemplo:
  Input: "Sistema de autenticação"
  Output: [
    "Login com email e senha",
    "Senha mínimo 8 caracteres",
    "Token expira em 24h",
    "Suporta refresh token",
    ...
  ]
"""
from typing import Optional
import json
import re

from ..types import Context, ContextSnapshot, Step, StepType, MDAPConfig
from ..llm.client import ClaudeClient, LLMResponse
from ..mdap.voter import Voter


EXPAND_SYSTEM = """You are an expert requirements analyst.
Given a task description, expand it into atomic requirements.

IMPORTANT:
- Each requirement must be ATOMIC (one single thing)
- Each requirement must be TESTABLE
- Each requirement must be INDEPENDENT (can be implemented alone)
- Do NOT include implementation details
- Focus on WHAT not HOW

Output format: JSON array of strings, one requirement per line.
Example: ["User can login with email", "Password has minimum 8 chars", ...]"""

EXPAND_PROMPT = """Task: {task}

{context}

List ALL atomic requirements needed to complete this task.
Be thorough - missing requirements cause bugs later.

Output as JSON array:"""


class Expander:
    """Expande tarefa em requisitos atômicos usando MDAP."""

    def __init__(
        self,
        client: ClaudeClient,
        config: Optional[MDAPConfig] = None,
    ):
        self.client = client
        self.config = config or MDAPConfig()
        self.voter = Voter(client, config)

    async def expand(
        self,
        task: str,
        context: Optional[ContextSnapshot] = None,
        use_mdap: bool = True,
    ) -> list[str]:
        """
        Expande tarefa em requisitos atômicos.

        Args:
            task: Descrição da tarefa
            context: Contexto adicional
            use_mdap: Se True, usa votação MDAP

        Returns:
            Lista de requisitos atômicos
        """
        context_text = context.to_prompt_context() if context else ""

        prompt = EXPAND_PROMPT.format(
            task=task,
            context=context_text,
        )

        if use_mdap:
            return await self._expand_with_mdap(task, prompt)
        else:
            return await self._expand_single(prompt)

    async def _expand_single(self, prompt: str) -> list[str]:
        """Expansão sem MDAP (single shot)."""
        response = await self.client.generate(
            prompt=prompt,
            system=EXPAND_SYSTEM,
            temperature=self.config.temperature,
            max_tokens=1000,
        )

        return self._parse_requirements(response.content)

    async def _expand_with_mdap(self, task: str, prompt: str) -> list[str]:
        """Expansão com votação MDAP."""
        step = Step(
            type=StepType.EXPAND,
            description=f"Expand requirements for: {task}",
        )

        async def generator(s: Step, ctx: str) -> LLMResponse:
            return await self.client.generate(
                prompt=prompt,
                system=EXPAND_SYSTEM,
                temperature=self.config.temperature,
                max_tokens=1000,
            )

        result = await self.voter.vote(
            step=step,
            context=prompt,
            generator=generator,
            k=self.config.k,
        )

        return self._parse_requirements(result.winner.code)

    def _parse_requirements(self, text: str) -> list[str]:
        """Parse resposta em lista de requisitos."""
        text = text.strip()

        # Tenta parse JSON
        try:
            # Extrai JSON de markdown se necessário
            json_match = re.search(r'\[[\s\S]*\]', text)
            if json_match:
                data = json.loads(json_match.group())
                if isinstance(data, list):
                    return [str(r).strip() for r in data if r]
        except json.JSONDecodeError:
            pass

        # Fallback: parse linha por linha
        requirements = []
        for line in text.split('\n'):
            line = line.strip()
            # Remove prefixos comuns
            line = re.sub(r'^[-*•]\s*', '', line)
            line = re.sub(r'^\d+\.\s*', '', line)
            line = re.sub(r'^"(.+)"$', r'\1', line)

            if line and len(line) > 5:
                requirements.append(line)

        return requirements

    async def expand_iterative(
        self,
        task: str,
        max_iterations: int = 3,
    ) -> list[str]:
        """
        Expansão iterativa - refina requisitos em múltiplas rodadas.

        Args:
            task: Tarefa
            max_iterations: Máximo de iterações

        Returns:
            Lista final de requisitos
        """
        requirements: list[str] = []

        for i in range(max_iterations):
            # Contexto com requisitos já encontrados
            context_text = ""
            if requirements:
                context_text = "Requirements found so far:\n"
                for j, r in enumerate(requirements, 1):
                    context_text += f"{j}. {r}\n"
                context_text += "\nFind additional requirements NOT in this list."

            prompt = EXPAND_PROMPT.format(task=task, context=context_text)
            new_reqs = await self._expand_single(prompt)

            # Adiciona novos (sem duplicados)
            before = len(requirements)
            for r in new_reqs:
                if r not in requirements:
                    requirements.append(r)

            # Para se não encontrou novos
            if len(requirements) == before:
                break

        return requirements
