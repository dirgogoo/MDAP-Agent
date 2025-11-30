"""
Red Flag Filter - Filtros de qualidade para candidatos

Baseado no paper MAKER, descarta respostas que:
- São muito longas (indicam confusão)
- Estão mal formatadas
- Não parseiam como código válido
"""
import ast
import re
from typing import Optional
from dataclasses import dataclass

from ..types import Candidate, MDAPConfig, Language


@dataclass
class RedFlagResult:
    """Resultado da verificação de red flags."""
    passed: bool
    reason: Optional[str] = None
    checks: dict[str, bool] = None

    def __post_init__(self):
        if self.checks is None:
            self.checks = {}


class RedFlagFilter:
    """Filtro de qualidade para candidatos de código."""

    def __init__(self, config: Optional[MDAPConfig] = None):
        self.config = config or MDAPConfig()

    def check(
        self,
        candidate: Candidate,
        language: Language = Language.PYTHON,
    ) -> RedFlagResult:
        """
        Verifica se candidato passa nos filtros.

        Args:
            candidate: Candidato a verificar
            language: Linguagem do código

        Returns:
            RedFlagResult indicando se passou e por quê
        """
        checks = {}

        # 1. Verificar tamanho
        if self.config.enable_length_check:
            length_ok = self._check_length(candidate)
            checks["length"] = length_ok
            if not length_ok:
                return RedFlagResult(
                    passed=False,
                    reason=f"Response too long ({candidate.tokens_used} tokens > {self.config.max_tokens_response})",
                    checks=checks,
                )

        # 2. Verificar formato
        if self.config.enable_format_check:
            format_ok, format_reason = self._check_format(candidate)
            checks["format"] = format_ok
            if not format_ok:
                return RedFlagResult(
                    passed=False,
                    reason=format_reason,
                    checks=checks,
                )

        # 3. Verificar sintaxe
        if self.config.enable_syntax_check:
            syntax_ok, syntax_reason = self._check_syntax(candidate, language)
            checks["syntax"] = syntax_ok
            if not syntax_ok:
                return RedFlagResult(
                    passed=False,
                    reason=syntax_reason,
                    checks=checks,
                )

        return RedFlagResult(passed=True, checks=checks)

    def _check_length(self, candidate: Candidate) -> bool:
        """Verifica se resposta não é muito longa."""
        return candidate.tokens_used <= self.config.max_tokens_response

    def _check_format(self, candidate: Candidate) -> tuple[bool, Optional[str]]:
        """Verifica formato básico do código."""
        code = candidate.code.strip()

        # Código vazio
        if not code:
            return False, "Empty code"

        # Muito curto para ser útil
        if len(code) < 10:
            return False, "Code too short"

        # Contém explicação ao invés de código
        explanation_patterns = [
            r"^Here'?s?\s+(the|a|an)\s+",
            r"^I'?ll\s+",
            r"^This\s+(function|code|implementation)",
            r"^The\s+following",
        ]
        for pattern in explanation_patterns:
            if re.match(pattern, code, re.IGNORECASE):
                return False, "Contains explanation instead of code"

        return True, None

    def _check_syntax(
        self,
        candidate: Candidate,
        language: Language,
    ) -> tuple[bool, Optional[str]]:
        """Verifica se código parseia corretamente."""
        code = self._extract_code(candidate.code)

        if language == Language.PYTHON:
            return self._check_python_syntax(code)
        elif language == Language.TYPESCRIPT:
            return self._check_typescript_syntax(code)
        else:
            # Linguagem não suportada, assume OK
            return True, None

    def _extract_code(self, text: str) -> str:
        """Extrai código de blocos markdown se presente."""
        # Procura por blocos ```language ... ```
        pattern = r"```(?:python|typescript|javascript|js|ts)?\n?(.*?)```"
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            return matches[0].strip()

        # Se não tem bloco, retorna texto limpo
        return text.strip()

    def _check_python_syntax(self, code: str) -> tuple[bool, Optional[str]]:
        """Verifica sintaxe Python usando ast.parse."""
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            return False, f"Python syntax error: {e.msg} at line {e.lineno}"
        except Exception as e:
            return False, f"Python parse error: {str(e)}"

    def _check_typescript_syntax(self, code: str) -> tuple[bool, Optional[str]]:
        """
        Verifica sintaxe TypeScript (básico).
        Nota: verificação completa requer ts-morph ou similar.
        """
        # Verificação básica de balanceamento
        brackets = {'{': '}', '[': ']', '(': ')'}
        stack = []

        in_string = False
        string_char = None

        for char in code:
            if char in '"\'`' and not in_string:
                in_string = True
                string_char = char
            elif char == string_char and in_string:
                in_string = False
                string_char = None
            elif not in_string:
                if char in brackets:
                    stack.append(brackets[char])
                elif char in brackets.values():
                    if not stack or stack.pop() != char:
                        return False, f"Unbalanced brackets at '{char}'"

        if stack:
            return False, f"Unclosed brackets: {stack}"

        return True, None


def quick_check(
    code: str,
    language: Language = Language.PYTHON,
    max_tokens: int = 500,
) -> bool:
    """
    Verificação rápida sem criar Candidate.

    Args:
        code: Código a verificar
        language: Linguagem
        max_tokens: Limite de tokens (aproximado por chars/4)

    Returns:
        True se passou nos checks básicos
    """
    candidate = Candidate(
        code=code,
        tokens_used=len(code) // 4,  # aproximação
    )

    config = MDAPConfig(max_tokens_response=max_tokens)
    filter_ = RedFlagFilter(config)
    result = filter_.check(candidate, language)

    return result.passed
