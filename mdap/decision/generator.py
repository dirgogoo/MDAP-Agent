"""
Generator - Implementa código para um Step

Gera código usando MDAP para garantir qualidade.
"""
from typing import Optional
import re

from ..types import Step, StepType, ContextSnapshot, MDAPConfig, Language, VoteResult
from ..llm.client import ClaudeClient, LLMResponse
from ..mdap.voter import Voter


GENERATE_SYSTEM = """You are an expert {language} developer.
Generate ONLY the code requested - no explanations, no markdown.

Requirements:
- Clean, readable code
- Follow {language} best practices
- Include type hints
- Handle edge cases
- Keep it simple - don't over-engineer

Output the function/class directly, no ``` markers."""

GENERATE_PROMPT = """Function to implement:
{signature}

Description:
{description}

Context:
{context}

Implement this function:"""


class Generator:
    """Gera código usando MDAP."""

    def __init__(
        self,
        client: ClaudeClient,
        config: Optional[MDAPConfig] = None,
    ):
        self.client = client
        self.config = config or MDAPConfig()
        self.voter = Voter(client, config)

    async def generate(
        self,
        step: Step,
        context: Optional[ContextSnapshot] = None,
        language: Language = Language.PYTHON,
        use_mdap: bool = True,
    ) -> str:
        """
        Gera código para um Step.

        Args:
            step: Step com signature e description
            context: Contexto do projeto
            language: Linguagem
            use_mdap: Se True, usa votação

        Returns:
            Código gerado
        """
        context_text = ""
        if context:
            context_text = context.to_prompt_context()
        if step.context:
            context_text += f"\n\n{step.context}"

        prompt = GENERATE_PROMPT.format(
            signature=step.signature,
            description=step.description,
            context=context_text,
        )

        system = GENERATE_SYSTEM.format(language=language.value)

        if use_mdap:
            result = await self._generate_with_mdap(step, prompt, system, language)
            return self._clean_code(result.winner.code)
        else:
            response = await self._generate_single(prompt, system)
            return self._clean_code(response.content)

    async def _generate_single(self, prompt: str, system: str) -> LLMResponse:
        """Geração sem MDAP."""
        return await self.client.generate(
            prompt=prompt,
            system=system,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens_response,
        )

    async def _generate_with_mdap(
        self,
        step: Step,
        prompt: str,
        system: str,
        language: Language,
    ) -> VoteResult:
        """Geração com votação MDAP."""
        async def generator(s: Step, ctx: str) -> LLMResponse:
            return await self.client.generate(
                prompt=prompt,
                system=system,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens_response,
            )

        return await self.voter.vote(
            step=step,
            context=prompt,
            generator=generator,
            language=language,
            k=self.config.k,
        )

    def _clean_code(self, code: str) -> str:
        """Limpa código de artefatos."""
        code = code.strip()

        # Remove markdown code blocks
        code = re.sub(r'^```\w*\n?', '', code)
        code = re.sub(r'\n?```$', '', code)

        # Remove explicações antes do código
        lines = code.split('\n')
        code_started = False
        clean_lines = []

        for line in lines:
            if not code_started:
                # Procura início do código
                if line.strip().startswith(('def ', 'async def ', 'class ', 'import ', 'from ')):
                    code_started = True
                    clean_lines.append(line)
                elif line.strip().startswith('#') and not line.strip().startswith('# '):
                    # Comentário de código, não explicação
                    code_started = True
                    clean_lines.append(line)
            else:
                clean_lines.append(line)

        if clean_lines:
            return '\n'.join(clean_lines)

        return code

    async def generate_batch(
        self,
        steps: list[Step],
        context: Optional[ContextSnapshot] = None,
        language: Language = Language.PYTHON,
    ) -> dict[str, str]:
        """
        Gera código para múltiplos steps.

        Args:
            steps: Lista de Steps
            context: Contexto
            language: Linguagem

        Returns:
            Dict step_id -> código
        """
        results = {}

        for step in steps:
            code = await self.generate(
                step=step,
                context=context,
                language=language,
            )
            results[step.id] = code

            # Atualiza contexto com código gerado
            if context:
                context.generated_code[step.id] = code

        return results

    async def generate_with_tests(
        self,
        step: Step,
        context: Optional[ContextSnapshot] = None,
        language: Language = Language.PYTHON,
    ) -> tuple[str, str]:
        """
        Gera código e testes.

        Returns:
            Tuple (código, testes)
        """
        # Gera código
        code = await self.generate(step, context, language)

        # Gera testes
        test_step = Step(
            type=StepType.GENERATE,
            signature=f"test_{step.signature.split('(')[0].split()[-1]}",
            description=f"Unit tests for {step.signature}",
            context=f"Function to test:\n```\n{code}\n```",
        )

        test_system = f"""You are an expert {language.value} developer writing tests.
Generate pytest test functions for the given code.
Include:
- Happy path tests
- Edge case tests
- Error handling tests

Output only the test code, no explanations."""

        test_prompt = f"""Write tests for this function:
{code}

Generate pytest test functions:"""

        response = await self.client.generate(
            prompt=test_prompt,
            system=test_system,
            max_tokens=self.config.max_tokens_response,
        )

        return code, self._clean_code(response.content)
