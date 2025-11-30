"""
Agent Loop - Loop principal do MDAP Agent

Combina:
- Votação MDAP em cada decisão
- Expansão de requisitos (não apenas decomposição)
- Separação Execução/Decisão
"""
import asyncio
import logging
from typing import Optional, Callable, Awaitable

from ..types import Step, StepType, Language, MDAPConfig
from ..llm.client import ClaudeClient, get_client, cleanup
from ..execution import init_all_tools
from .context import AgentContext
from .step import StepExecutor


logger = logging.getLogger(__name__)


class AgentLoop:
    """Loop principal do MDAP Agent."""

    def __init__(
        self,
        client: Optional[ClaudeClient] = None,
        config: Optional[MDAPConfig] = None,
    ):
        self.client = client or get_client(config)
        self.config = config or MDAPConfig()
        self.executor = StepExecutor(self.client, config)

        # Callbacks
        self._on_step_start: Optional[Callable[[Step], Awaitable[None]]] = None
        self._on_step_end: Optional[Callable[[Step, bool], Awaitable[None]]] = None
        self._on_decision: Optional[Callable[[Step], Awaitable[bool]]] = None

        # Inicializa ferramentas
        init_all_tools()

    async def run(
        self,
        task: str,
        language: Language = Language.PYTHON,
        max_steps: int = 50,
    ) -> AgentContext:
        """
        Executa tarefa completa.

        Args:
            task: Descrição da tarefa
            language: Linguagem alvo
            max_steps: Limite de passos

        Returns:
            AgentContext com resultado
        """
        context = AgentContext(
            task=task,
            language=language,
            config=self.config,
        )

        logger.info(f"Starting agent loop for: {task}")
        step_count = 0

        while not context.is_complete and step_count < max_steps:
            step_count += 1

            # 1. Decide próximo passo
            next_step = await self.executor.decide_next(context)
            logger.info(f"Step {step_count}: {next_step.type.value}")

            # Callback de decisão (pode cancelar)
            if self._on_decision:
                should_continue = await self._on_decision(next_step)
                if not should_continue:
                    logger.info("Stopped by decision callback")
                    break

            # 2. Callback de início
            if self._on_step_start:
                await self._on_step_start(next_step)

            # 3. Executa
            result = await self.executor.execute(next_step, context)

            # 4. Callback de fim
            if self._on_step_end:
                await self._on_step_end(next_step, result.success)

            # 5. Verifica erros
            if not result.success:
                logger.warning(f"Step failed: {result.error}")
                # Continua tentando (pode recuperar)

        if step_count >= max_steps:
            logger.warning(f"Max steps ({max_steps}) reached")

        logger.info(f"Agent loop complete. Steps: {step_count}")
        return context

    async def run_interactive(
        self,
        task: str,
        language: Language = Language.PYTHON,
    ) -> AgentContext:
        """
        Executa com confirmação a cada passo.

        Args:
            task: Descrição da tarefa
            language: Linguagem

        Returns:
            AgentContext com resultado
        """
        async def confirm_step(step: Step) -> bool:
            print(f"\nNext step: {step.type.value}")
            print(f"Description: {step.description}")
            response = input("Continue? [Y/n] ").strip().lower()
            return response != 'n'

        self._on_decision = confirm_step
        return await self.run(task, language)

    def on_step_start(
        self,
        callback: Callable[[Step], Awaitable[None]],
    ) -> None:
        """Registra callback para início de step."""
        self._on_step_start = callback

    def on_step_end(
        self,
        callback: Callable[[Step, bool], Awaitable[None]],
    ) -> None:
        """Registra callback para fim de step."""
        self._on_step_end = callback

    def on_decision(
        self,
        callback: Callable[[Step], Awaitable[bool]],
    ) -> None:
        """Registra callback para decisões."""
        self._on_decision = callback

    async def close(self) -> None:
        """Libera recursos."""
        await cleanup()


async def agent_loop(
    task: str,
    language: Language = Language.PYTHON,
    config: Optional[MDAPConfig] = None,
    max_steps: int = 50,
) -> dict:
    """
    Função helper para rodar agent loop.

    Args:
        task: Descrição da tarefa
        language: Linguagem
        config: Configuração MDAP
        max_steps: Limite de passos

    Returns:
        Dict com resultado
    """
    agent = AgentLoop(config=config)

    try:
        context = await agent.run(task, language, max_steps)
        return context.final_result()
    finally:
        await agent.close()


def run_sync(
    task: str,
    language: Language = Language.PYTHON,
    config: Optional[MDAPConfig] = None,
) -> dict:
    """
    Versão síncrona do agent loop.

    Args:
        task: Descrição da tarefa
        language: Linguagem
        config: Configuração

    Returns:
        Dict com resultado
    """
    return asyncio.run(agent_loop(task, language, config))


# --- CLI ---

def main():
    """CLI para o agent."""
    import argparse

    parser = argparse.ArgumentParser(description="MDAP Agent")
    parser.add_argument("task", help="Task description")
    parser.add_argument("--language", "-l", default="python", choices=["python", "typescript"])
    parser.add_argument("--k", type=int, default=3, help="MDAP k parameter")
    parser.add_argument("--max-steps", type=int, default=50, help="Max steps")
    parser.add_argument("--output", "-o", help="Output file")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)

    config = MDAPConfig(k=args.k)
    language = Language(args.language)

    result = run_sync(args.task, language, config)

    if args.output:
        import json
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"Result saved to {args.output}")
    else:
        # Print code
        print("\n=== Generated Code ===\n")
        for step_id, code in result.get("code", {}).items():
            print(f"# {step_id}")
            print(code)
            print()

        print("\n=== Metrics ===")
        metrics = result.get("metrics", {})
        print(f"Steps: {metrics.get('steps_total', 0)}")
        print(f"Tokens: {metrics.get('tokens', {}).get('total', 0)}")
        print(f"Duration: {metrics.get('duration_seconds', 0):.1f}s")


if __name__ == "__main__":
    main()
