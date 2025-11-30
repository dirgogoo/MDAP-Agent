"""
Decider - Decide próximo passo do agente

Dado o contexto atual, decide qual ação tomar:
- EXPAND (mais requisitos)
- DECOMPOSE (organizar em funções)
- GENERATE (implementar)
- VALIDATE (verificar)
- EXECUTE (rodar ferramenta)
- DONE (finalizar)
"""
from typing import Optional
from dataclasses import dataclass
from enum import Enum

from ..types import Step, StepType, ContextSnapshot, MDAPConfig
from ..llm.client import ClaudeClient, LLMResponse
from ..mdap.voter import Voter


class DecisionType(Enum):
    """Tipos de decisão."""
    EXPAND = "expand"
    DECOMPOSE = "decompose"
    GENERATE = "generate"
    VALIDATE = "validate"
    READ = "read"
    SEARCH = "search"
    TEST = "test"
    DONE = "done"


@dataclass
class Decision:
    """Uma decisão do agente."""
    type: DecisionType
    step: Step
    reason: str
    confidence: float = 1.0


DECIDE_SYSTEM = """You are an AI coding assistant deciding the next step.

Given the current context, decide what to do next.
Consider:
1. Have requirements been fully expanded?
2. Have requirements been decomposed into functions?
3. Have all functions been implemented?
4. Has the code been validated?
5. Are there errors to fix?

Output format:
ACTION: [expand|decompose|generate|validate|read|search|test|done]
TARGET: [what to act on]
REASON: [why this action]"""

DECIDE_PROMPT = """Current context:
{context}

Progress:
- Requirements: {num_requirements}
- Functions planned: {num_functions}
- Functions implemented: {num_implemented}
- Validation errors: {num_errors}

What should be the next step?"""


class Decider:
    """Decide próximo passo usando MDAP."""

    def __init__(
        self,
        client: ClaudeClient,
        config: Optional[MDAPConfig] = None,
    ):
        self.client = client
        self.config = config or MDAPConfig()
        self.voter = Voter(client, config)

    async def decide(
        self,
        context: ContextSnapshot,
        use_mdap: bool = True,
    ) -> Decision:
        """
        Decide próximo passo.

        Args:
            context: Estado atual
            use_mdap: Se True, usa votação

        Returns:
            Decision com tipo e target
        """
        # Calcula progresso
        num_requirements = len(context.requirements)
        num_functions = len(context.functions)
        num_implemented = len(context.generated_code)
        num_errors = sum(
            1 for _, r in context.execution_results
            if not r.success
        )

        prompt = DECIDE_PROMPT.format(
            context=context.to_prompt_context(),
            num_requirements=num_requirements,
            num_functions=num_functions,
            num_implemented=num_implemented,
            num_errors=num_errors,
        )

        if use_mdap:
            decision = await self._decide_with_mdap(context, prompt)
        else:
            decision = await self._decide_single(prompt)

        return decision

    async def _decide_single(self, prompt: str) -> Decision:
        """Decisão sem MDAP."""
        response = await self.client.generate(
            prompt=prompt,
            system=DECIDE_SYSTEM,
            temperature=0.0,
            max_tokens=200,
        )

        return self._parse_decision(response.content)

    async def _decide_with_mdap(
        self,
        context: ContextSnapshot,
        prompt: str,
    ) -> Decision:
        """Decisão com votação MDAP."""
        step = Step(
            type=StepType.DECIDE,
            description="Decide next step",
        )

        async def generator(s: Step, ctx: str) -> LLMResponse:
            return await self.client.generate(
                prompt=prompt,
                system=DECIDE_SYSTEM,
                temperature=self.config.temperature,
                max_tokens=200,
            )

        result = await self.voter.vote(
            step=step,
            context=prompt,
            generator=generator,
            k=self.config.k,
        )

        return self._parse_decision(result.winner.code)

    def _parse_decision(self, text: str) -> Decision:
        """Parse resposta em Decision."""
        lines = text.strip().split('\n')

        action = DecisionType.DONE
        target = ""
        reason = ""

        for line in lines:
            line = line.strip()

            if line.upper().startswith('ACTION:'):
                action_str = line.split(':', 1)[1].strip().lower()
                try:
                    action = DecisionType(action_str)
                except ValueError:
                    # Mapeia variações
                    action_map = {
                        'implement': DecisionType.GENERATE,
                        'code': DecisionType.GENERATE,
                        'write': DecisionType.GENERATE,
                        'check': DecisionType.VALIDATE,
                        'review': DecisionType.VALIDATE,
                        'find': DecisionType.SEARCH,
                        'finish': DecisionType.DONE,
                        'complete': DecisionType.DONE,
                    }
                    action = action_map.get(action_str, DecisionType.DONE)

            elif line.upper().startswith('TARGET:'):
                target = line.split(':', 1)[1].strip()

            elif line.upper().startswith('REASON:'):
                reason = line.split(':', 1)[1].strip()

        # Cria Step baseado na action
        step_type_map = {
            DecisionType.EXPAND: StepType.EXPAND,
            DecisionType.DECOMPOSE: StepType.DECOMPOSE,
            DecisionType.GENERATE: StepType.GENERATE,
            DecisionType.VALIDATE: StepType.VALIDATE,
            DecisionType.READ: StepType.READ,
            DecisionType.SEARCH: StepType.SEARCH,
            DecisionType.TEST: StepType.TEST,
            DecisionType.DONE: StepType.DONE,
        }

        step = Step(
            type=step_type_map.get(action, StepType.DONE),
            description=target or f"Execute {action.value}",
            action=target if action in (
                DecisionType.READ,
                DecisionType.SEARCH,
                DecisionType.TEST,
            ) else None,
        )

        return Decision(
            type=action,
            step=step,
            reason=reason,
        )

    async def decide_from_options(
        self,
        context: ContextSnapshot,
        options: list[Step],
    ) -> Step:
        """
        Escolhe entre opções predefinidas.

        Args:
            context: Contexto
            options: Lista de steps possíveis

        Returns:
            Step escolhido
        """
        options_text = "\n".join(
            f"{i}. {opt.description}"
            for i, opt in enumerate(options)
        )

        prompt = f"""Context:
{context.to_prompt_context()}

Options:
{options_text}

Which option should be next? Answer with just the number."""

        response = await self.client.generate(
            prompt=prompt,
            system="Choose the best next step. Output only the number.",
            temperature=0.0,
            max_tokens=10,
        )

        try:
            idx = int(response.content.strip())
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            pass

        return options[0] if options else Step(type=StepType.DONE)
