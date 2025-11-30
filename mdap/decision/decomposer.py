"""
Decomposer - Organiza requisitos em funções/módulos

DECOMPOSIÇÃO (top-down): divide em partes estruturadas.
Recebe requisitos expandidos e organiza em funções.

Exemplo:
  Input: ["Login com email", "Senha mínimo 8 chars", ...]
  Output: [
    Step(signature="def validate_email(email: str) -> bool", ...),
    Step(signature="def validate_password(password: str) -> bool", ...),
    Step(signature="def create_user(email: str, password: str) -> User", ...),
  ]
"""
from typing import Optional
import json
import re

from ..types import Context, ContextSnapshot, Step, StepType, MDAPConfig, Language
from ..llm.client import ClaudeClient, LLMResponse
from ..mdap.voter import Voter


DECOMPOSE_SYSTEM = """You are an expert software architect.
Given requirements, decompose them into functions/methods.

IMPORTANT:
- Each function must be ATOMIC (one responsibility)
- Each function must have a CLEAR signature
- Include type hints
- Order functions by dependency (dependencies first)
- Keep functions SMALL (< 30 lines ideally)

Output format: JSON array of objects with:
- signature: function signature with types
- description: what the function does
- dependencies: list of other function names it calls
- requirements: list of requirement indices it implements

Example:
[
  {
    "signature": "def validate_email(email: str) -> bool",
    "description": "Validates email format using regex",
    "dependencies": [],
    "requirements": [0]
  }
]"""

DECOMPOSE_PROMPT = """Requirements:
{requirements}

Language: {language}

Decompose these requirements into functions.
Each function should implement one or more requirements.
Order by dependencies (implement base functions first).

Output as JSON array:"""


class Decomposer:
    """Decompõe requisitos em funções usando MDAP."""

    def __init__(
        self,
        client: ClaudeClient,
        config: Optional[MDAPConfig] = None,
    ):
        self.client = client
        self.config = config or MDAPConfig()
        self.voter = Voter(client, config)

    async def decompose(
        self,
        requirements: list[str],
        language: Language = Language.PYTHON,
        context: Optional[ContextSnapshot] = None,
        use_mdap: bool = True,
    ) -> list[Step]:
        """
        Decompõe requisitos em funções.

        Args:
            requirements: Lista de requisitos atômicos
            language: Linguagem alvo
            context: Contexto adicional
            use_mdap: Se True, usa votação MDAP

        Returns:
            Lista de Steps (funções a implementar)
        """
        reqs_text = "\n".join(f"{i}. {r}" for i, r in enumerate(requirements))

        prompt = DECOMPOSE_PROMPT.format(
            requirements=reqs_text,
            language=language.value,
        )

        if use_mdap:
            return await self._decompose_with_mdap(prompt, language)
        else:
            return await self._decompose_single(prompt)

    async def _decompose_single(self, prompt: str) -> list[Step]:
        """Decomposição sem MDAP."""
        response = await self.client.generate(
            prompt=prompt,
            system=DECOMPOSE_SYSTEM,
            temperature=self.config.temperature,
            max_tokens=2000,
        )

        return self._parse_functions(response.content)

    async def _decompose_with_mdap(
        self,
        prompt: str,
        language: Language,
    ) -> list[Step]:
        """Decomposição com votação MDAP."""
        step = Step(
            type=StepType.DECOMPOSE,
            description="Decompose requirements into functions",
        )

        async def generator(s: Step, ctx: str) -> LLMResponse:
            return await self.client.generate(
                prompt=prompt,
                system=DECOMPOSE_SYSTEM,
                temperature=self.config.temperature,
                max_tokens=2000,
            )

        result = await self.voter.vote(
            step=step,
            context=prompt,
            generator=generator,
            language=language,
            k=self.config.k,
        )

        return self._parse_functions(result.winner.code)

    def _parse_functions(self, text: str) -> list[Step]:
        """Parse resposta em lista de Steps."""
        text = text.strip()
        steps = []

        # Tenta parse JSON
        try:
            json_match = re.search(r'\[[\s\S]*\]', text)
            if json_match:
                data = json.loads(json_match.group())
                if isinstance(data, list):
                    for i, item in enumerate(data):
                        if isinstance(item, dict):
                            steps.append(Step(
                                type=StepType.GENERATE,
                                description=item.get("description", ""),
                                signature=item.get("signature", ""),
                                context=json.dumps({
                                    "dependencies": item.get("dependencies", []),
                                    "requirements": item.get("requirements", []),
                                }),
                            ))
                    return steps
        except json.JSONDecodeError:
            pass

        # Fallback: procura por padrões de função
        patterns = [
            r'def\s+\w+\s*\([^)]*\)\s*(?:->.*?)?:',
            r'async\s+def\s+\w+\s*\([^)]*\)\s*(?:->.*?)?:',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text):
                sig = match.group().rstrip(':')
                steps.append(Step(
                    type=StepType.GENERATE,
                    signature=sig,
                    description=f"Implement {sig}",
                ))

        return steps

    async def decompose_hierarchical(
        self,
        requirements: list[str],
        language: Language = Language.PYTHON,
    ) -> dict[str, list[Step]]:
        """
        Decomposição hierárquica - agrupa por módulo.

        Returns:
            Dict de módulo -> lista de funções
        """
        prompt = f"""Requirements:
{chr(10).join(f"{i}. {r}" for i, r in enumerate(requirements))}

Language: {language.value}

1. First, group requirements by logical module
2. Then decompose each module into functions
3. Order by dependencies

Output as JSON:
{{
  "module_name": [
    {{"signature": "...", "description": "..."}},
    ...
  ]
}}"""

        response = await self.client.generate(
            prompt=prompt,
            system=DECOMPOSE_SYSTEM,
            temperature=self.config.temperature,
            max_tokens=3000,
        )

        try:
            json_match = re.search(r'\{[\s\S]*\}', response.content)
            if json_match:
                data = json.loads(json_match.group())
                result = {}
                for module, funcs in data.items():
                    result[module] = [
                        Step(
                            type=StepType.GENERATE,
                            signature=f.get("signature", ""),
                            description=f.get("description", ""),
                        )
                        for f in funcs if isinstance(f, dict)
                    ]
                return result
        except:
            pass

        # Fallback: módulo único
        steps = await self.decompose(requirements, language, use_mdap=False)
        return {"main": steps}
