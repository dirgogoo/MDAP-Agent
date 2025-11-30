"""
Validator - Verifica correção do código

Valida se código gerado:
- Compila/parseia corretamente
- Implementa os requisitos
- Segue boas práticas
"""
from typing import Optional
from dataclasses import dataclass
import ast
import re

from ..types import Step, ContextSnapshot, MDAPConfig, Language
from ..llm.client import ClaudeClient, LLMResponse
from ..mdap.voter import Voter


@dataclass
class ValidationResult:
    """Resultado de validação."""
    is_valid: bool
    errors: list[str]
    warnings: list[str]
    suggestions: list[str]

    @property
    def passed(self) -> bool:
        return self.is_valid and len(self.errors) == 0


VALIDATE_SYSTEM = """You are an expert code reviewer.
Review the code for correctness, bugs, and best practices.

Check for:
1. Logic errors
2. Edge cases not handled
3. Type mismatches
4. Missing error handling
5. Security issues
6. Performance problems

Be thorough but fair. Only flag real issues.

Output format:
VALID: yes/no
ERRORS: [list of errors]
WARNINGS: [list of warnings]
SUGGESTIONS: [list of improvements]"""

VALIDATE_PROMPT = """Code to review:
```
{code}
```

Specification:
{specification}

Context:
{context}

Review this code:"""


class Validator:
    """Valida código usando análise estática e LLM."""

    def __init__(
        self,
        client: ClaudeClient,
        config: Optional[MDAPConfig] = None,
    ):
        self.client = client
        self.config = config or MDAPConfig()
        self.voter = Voter(client, config)

    async def validate(
        self,
        code: str,
        step: Step,
        context: Optional[ContextSnapshot] = None,
        language: Language = Language.PYTHON,
    ) -> ValidationResult:
        """
        Valida código gerado.

        Args:
            code: Código a validar
            step: Step com especificação
            context: Contexto
            language: Linguagem

        Returns:
            ValidationResult
        """
        errors = []
        warnings = []
        suggestions = []

        # 1. Validação estática
        static_errors = self._static_validate(code, language)
        errors.extend(static_errors)

        # 2. Validação semântica com LLM
        if not static_errors:  # só se passou no estático
            llm_result = await self._llm_validate(code, step, context, language)
            errors.extend(llm_result.get("errors", []))
            warnings.extend(llm_result.get("warnings", []))
            suggestions.extend(llm_result.get("suggestions", []))

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions,
        )

    def _static_validate(self, code: str, language: Language) -> list[str]:
        """Validação estática (sintaxe)."""
        errors = []

        if language == Language.PYTHON:
            try:
                ast.parse(code)
            except SyntaxError as e:
                errors.append(f"Syntax error at line {e.lineno}: {e.msg}")

        return errors

    async def _llm_validate(
        self,
        code: str,
        step: Step,
        context: Optional[ContextSnapshot],
        language: Language,
    ) -> dict:
        """Validação semântica com LLM."""
        context_text = context.to_prompt_context() if context else ""

        prompt = VALIDATE_PROMPT.format(
            code=code,
            specification=f"{step.signature}\n{step.description}",
            context=context_text,
        )

        response = await self.client.generate(
            prompt=prompt,
            system=VALIDATE_SYSTEM,
            temperature=0.0,  # determinístico
            max_tokens=500,
        )

        return self._parse_validation(response.content)

    def _parse_validation(self, text: str) -> dict:
        """Parse resposta de validação."""
        result = {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "suggestions": [],
        }

        lines = text.strip().split('\n')

        current_section = None
        for line in lines:
            line = line.strip()

            if line.upper().startswith('VALID:'):
                value = line.split(':', 1)[1].strip().lower()
                result["is_valid"] = value in ('yes', 'true', '1')
            elif line.upper().startswith('ERRORS:'):
                current_section = "errors"
                # Pode ter conteúdo na mesma linha
                rest = line.split(':', 1)[1].strip()
                if rest and rest != '[]':
                    result["errors"].extend(self._parse_list(rest))
            elif line.upper().startswith('WARNINGS:'):
                current_section = "warnings"
                rest = line.split(':', 1)[1].strip()
                if rest and rest != '[]':
                    result["warnings"].extend(self._parse_list(rest))
            elif line.upper().startswith('SUGGESTIONS:'):
                current_section = "suggestions"
                rest = line.split(':', 1)[1].strip()
                if rest and rest != '[]':
                    result["suggestions"].extend(self._parse_list(rest))
            elif current_section and line.startswith('-'):
                item = line.lstrip('- ').strip()
                if item:
                    result[current_section].append(item)

        return result

    def _parse_list(self, text: str) -> list[str]:
        """Parse lista de items."""
        text = text.strip()

        # Tenta JSON
        if text.startswith('['):
            try:
                import json
                return json.loads(text)
            except:
                pass

        # Remove brackets e split por vírgula
        text = text.strip('[]')
        items = [i.strip().strip('"\'') for i in text.split(',')]
        return [i for i in items if i]

    async def validate_with_mdap(
        self,
        code: str,
        step: Step,
        context: Optional[ContextSnapshot] = None,
        language: Language = Language.PYTHON,
    ) -> bool:
        """
        Validação com votação MDAP.

        Múltiplos revisores votam se código está correto.
        Mais rigoroso que validação single-shot.
        """
        mdap_step = Step(
            type=step.type,
            description=f"Validate: {step.description}",
            specification=f"Is this code correct?\n{code}",
        )

        async def generator(s: Step, ctx: str) -> LLMResponse:
            prompt = f"""Is this code correct and complete?
Code:
```
{code}
```

Specification: {step.signature}
{step.description}

Answer ONLY "VALID" or "INVALID" followed by reason."""

            return await self.client.generate(
                prompt=prompt,
                system="You are a code reviewer. Be strict.",
                temperature=self.config.temperature,
                max_tokens=100,
            )

        result = await self.voter.vote(
            step=mdap_step,
            context=code,
            generator=generator,
            language=language,
            k=self.config.k,
        )

        return "VALID" in result.winner.code.upper()
