"""
Claude LLM Client - Wrapper assíncrono para Anthropic API

Fornece interface simplificada para:
- Geração de código (com temperature configurável)
- Comparação semântica (discriminator)
- Streaming opcional
"""
import asyncio
import os
from typing import Optional
from dataclasses import dataclass

import anthropic

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


class ClaudeClient:
    """Cliente assíncrono para Claude API."""

    def __init__(self, config: Optional[MDAPConfig] = None):
        self.config = config or MDAPConfig()
        self.client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY")
        )
        self._async_client: Optional[anthropic.AsyncAnthropic] = None

    @property
    def async_client(self) -> anthropic.AsyncAnthropic:
        """Lazy init do cliente async."""
        if self._async_client is None:
            self._async_client = anthropic.AsyncAnthropic(
                api_key=os.environ.get("ANTHROPIC_API_KEY")
            )
        return self._async_client

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
    ) -> LLMResponse:
        """
        Gera resposta do Claude.

        Args:
            prompt: Mensagem do usuário
            system: System prompt opcional
            temperature: Override da temperatura
            max_tokens: Override do max tokens
            model: Override do modelo

        Returns:
            LLMResponse com conteúdo e métricas
        """
        messages = [{"role": "user", "content": prompt}]

        response = await self.async_client.messages.create(
            model=model or self.config.model,
            max_tokens=max_tokens or self.config.max_tokens_response,
            temperature=temperature if temperature is not None else self.config.temperature,
            system=system or "",
            messages=messages,
        )

        content = ""
        if response.content:
            content = response.content[0].text

        return LLMResponse(
            content=content,
            tokens_input=response.usage.input_tokens,
            tokens_output=response.usage.output_tokens,
            model=response.model,
            stop_reason=response.stop_reason,
        )

    async def generate_code(
        self,
        specification: str,
        context: str = "",
        language: str = "python",
    ) -> LLMResponse:
        """
        Gera código baseado em especificação.

        Args:
            specification: O que deve ser implementado
            context: Contexto adicional (imports, dependências)
            language: Linguagem alvo

        Returns:
            LLMResponse com código gerado
        """
        system = f"""You are an expert {language} developer.
Generate ONLY the code requested, no explanations.
Output clean, well-formatted code that follows best practices.
Use type hints where appropriate."""

        prompt = f"""Context:
{context}

Specification:
{specification}

Generate the code:"""

        return await self.generate(
            prompt=prompt,
            system=system,
            max_tokens=self.config.max_tokens_response,
        )

    async def compare_semantic(
        self,
        code_a: str,
        code_b: str,
        context: str = "",
    ) -> bool:
        """
        Compara dois códigos semanticamente.

        Args:
            code_a: Primeiro código
            code_b: Segundo código
            context: Contexto da tarefa

        Returns:
            True se semanticamente equivalentes
        """
        system = """You are a code analysis expert.
Determine if two code snippets are SEMANTICALLY EQUIVALENT.
They are equivalent if they produce the same output for all valid inputs.
Minor differences in formatting, variable names, or implementation details
do not matter - only the behavior matters.
Answer ONLY "YES" or "NO"."""

        prompt = f"""Context: {context}

Code A:
```
{code_a}
```

Code B:
```
{code_b}
```

Are these two codes semantically equivalent? (YES/NO)"""

        response = await self.generate(
            prompt=prompt,
            system=system,
            temperature=0.0,  # determinístico para comparação
            max_tokens=10,
        )

        return response.content.strip().upper() == "YES"

    async def decide_next_step(
        self,
        context: str,
        options: list[str],
    ) -> int:
        """
        Decide o próximo passo dado o contexto.

        Args:
            context: Estado atual da tarefa
            options: Lista de opções possíveis

        Returns:
            Índice da opção escolhida
        """
        system = """You are a task planning expert.
Given the current context and options, choose the best next step.
Answer with ONLY the number of your choice."""

        options_text = "\n".join(f"{i}. {opt}" for i, opt in enumerate(options))

        prompt = f"""Current context:
{context}

Available options:
{options_text}

Which option should be next? (number only)"""

        response = await self.generate(
            prompt=prompt,
            system=system,
            temperature=0.0,
            max_tokens=5,
        )

        try:
            return int(response.content.strip())
        except ValueError:
            return 0  # default para primeira opção

    async def close(self):
        """Fecha conexões."""
        if self._async_client:
            await self._async_client.close()
            self._async_client = None


# Singleton global (opcional)
_default_client: Optional[ClaudeClient] = None


def get_client(config: Optional[MDAPConfig] = None) -> ClaudeClient:
    """Retorna cliente singleton ou cria novo."""
    global _default_client
    if _default_client is None:
        _default_client = ClaudeClient(config)
    return _default_client


async def cleanup():
    """Limpa recursos globais."""
    global _default_client
    if _default_client:
        await _default_client.close()
        _default_client = None
