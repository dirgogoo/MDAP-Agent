"""
Step Executor - Executa um step do agent loop

Separa:
- DECISÃO (não-determinística, usa MDAP)
- EXECUÇÃO (determinística, sem MDAP)
"""
from typing import Optional
import logging

from ..types import Step, StepType, ExecutionResult, Language, MDAPConfig
from ..llm.client import ClaudeClient
from ..decision.expander import Expander
from ..decision.decomposer import Decomposer
from ..decision.generator import Generator
from ..decision.validator import Validator, ValidationResult
from ..decision.decider import Decider, Decision
from ..execution.tools import execute_tool
from .context import AgentContext


logger = logging.getLogger(__name__)


class StepExecutor:
    """Executa steps do agent loop."""

    def __init__(
        self,
        client: ClaudeClient,
        config: Optional[MDAPConfig] = None,
    ):
        self.client = client
        self.config = config or MDAPConfig()

        # Componentes de decisão
        self.expander = Expander(client, config)
        self.decomposer = Decomposer(client, config)
        self.generator = Generator(client, config)
        self.validator = Validator(client, config)
        self.decider = Decider(client, config)

    async def execute(
        self,
        step: Step,
        context: AgentContext,
    ) -> ExecutionResult:
        """
        Executa um step.

        Args:
            step: Step a executar
            context: Contexto do agente

        Returns:
            ExecutionResult
        """
        context.record_step(step)
        logger.info(f"Executing step {step.id}: {step.type.value} - {step.description}")

        try:
            if step.type == StepType.EXPAND:
                return await self._execute_expand(step, context)

            elif step.type == StepType.DECOMPOSE:
                return await self._execute_decompose(step, context)

            elif step.type == StepType.GENERATE:
                return await self._execute_generate(step, context)

            elif step.type == StepType.VALIDATE:
                return await self._execute_validate(step, context)

            elif step.type in (StepType.READ, StepType.SEARCH, StepType.TEST, StepType.APPLY):
                return await self._execute_tool(step, context)

            elif step.type == StepType.DECIDE:
                return await self._execute_decide(step, context)

            elif step.type == StepType.DONE:
                context.mark_complete()
                return ExecutionResult(success=True, output="Task complete")

            else:
                return ExecutionResult(
                    success=False,
                    error=f"Unknown step type: {step.type}",
                )

        except Exception as e:
            logger.error(f"Step {step.id} failed: {e}")
            return ExecutionResult(
                success=False,
                error=str(e),
            )

    async def _execute_expand(
        self,
        step: Step,
        context: AgentContext,
    ) -> ExecutionResult:
        """Executa EXPAND - gera requisitos."""
        requirements = await self.expander.expand(
            task=context.task,
            context=context.snapshot(),
            use_mdap=True,
        )

        context.add_requirements(requirements)

        return ExecutionResult(
            success=True,
            output=f"Expanded {len(requirements)} requirements",
            data=requirements,
        )

    async def _execute_decompose(
        self,
        step: Step,
        context: AgentContext,
    ) -> ExecutionResult:
        """Executa DECOMPOSE - organiza em funções."""
        functions = await self.decomposer.decompose(
            requirements=context.context.requirements,
            language=context.language,
            context=context.snapshot(),
            use_mdap=True,
        )

        context.add_functions(functions)

        return ExecutionResult(
            success=True,
            output=f"Decomposed into {len(functions)} functions",
            data=[f.signature for f in functions],
        )

    async def _execute_generate(
        self,
        step: Step,
        context: AgentContext,
    ) -> ExecutionResult:
        """Executa GENERATE - implementa código."""
        code = await self.generator.generate(
            step=step,
            context=context.snapshot(),
            language=context.language,
            use_mdap=True,
        )

        context.add_generated_code(step, code)

        return ExecutionResult(
            success=True,
            output=f"Generated code for {step.signature}",
            data=code,
        )

    async def _execute_validate(
        self,
        step: Step,
        context: AgentContext,
    ) -> ExecutionResult:
        """Executa VALIDATE - verifica código."""
        # Encontra código a validar
        code = context.context.generated_code.get(step.id, "")
        if not code and step.specification:
            code = step.specification

        if not code:
            return ExecutionResult(
                success=False,
                error="No code to validate",
            )

        result = await self.validator.validate(
            code=code,
            step=step,
            context=context.snapshot(),
            language=context.language,
        )

        if result.passed:
            return ExecutionResult(
                success=True,
                output="Validation passed",
                data=result,
            )
        else:
            return ExecutionResult(
                success=False,
                output=f"Validation failed: {result.errors}",
                error="; ".join(result.errors),
                data=result,
            )

    async def _execute_tool(
        self,
        step: Step,
        context: AgentContext,
    ) -> ExecutionResult:
        """Executa ferramenta (determinística)."""
        result = await execute_tool(step)
        context.add_execution_result(step, result)
        return result

    async def _execute_decide(
        self,
        step: Step,
        context: AgentContext,
    ) -> ExecutionResult:
        """Executa DECIDE - escolhe próximo passo."""
        decision = await self.decider.decide(
            context=context.snapshot(),
            use_mdap=True,
        )

        return ExecutionResult(
            success=True,
            output=f"Next: {decision.type.value} - {decision.reason}",
            data=decision,
        )

    async def decide_next(self, context: AgentContext) -> Step:
        """
        Decide próximo step.

        Args:
            context: Contexto atual

        Returns:
            Próximo Step a executar
        """
        # Lógica de progresso automático
        snapshot = context.snapshot()

        # 1. Se não tem requisitos, expandir
        if not snapshot.requirements:
            return Step(
                type=StepType.EXPAND,
                description=f"Expand requirements for: {context.task}",
            )

        # 2. Se não tem funções, decompor
        if not snapshot.functions:
            return Step(
                type=StepType.DECOMPOSE,
                description="Decompose requirements into functions",
            )

        # 3. Se tem funções não implementadas, gerar
        for func in snapshot.functions:
            if func.id not in snapshot.generated_code:
                return Step(
                    type=StepType.GENERATE,
                    id=func.id,
                    description=func.description,
                    signature=func.signature,
                    context=func.context,
                )

        # 4. Tudo implementado - done
        return Step(type=StepType.DONE, description="All functions implemented")
