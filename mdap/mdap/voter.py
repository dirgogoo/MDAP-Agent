"""
MDAP Voter - Implementa votação first-to-ahead-by-k

Baseado no paper MAKER:
1. Gera candidatos um por vez
2. Classifica em grupos semânticos
3. Primeiro grupo com k votos de vantagem vence
"""
import asyncio
from typing import AsyncIterator, Callable, Awaitable, Optional
from dataclasses import dataclass, field
import logging

from ..types import Candidate, VoteResult, Step, MDAPConfig, Language
from .discriminator import Discriminator, SemanticGroup
from .red_flag import RedFlagFilter
from ..llm.client import ClaudeClient, LLMResponse


logger = logging.getLogger(__name__)


@dataclass
class VotingSession:
    """Estado de uma sessão de votação."""
    step: Step
    context: str
    samples: list[Candidate] = field(default_factory=list)
    valid_samples: list[Candidate] = field(default_factory=list)
    invalid_samples: list[Candidate] = field(default_factory=list)
    is_complete: bool = False
    winner: Optional[SemanticGroup] = None


class Voter:
    """Implementa votação MDAP first-to-ahead-by-k."""

    def __init__(
        self,
        client: ClaudeClient,
        config: Optional[MDAPConfig] = None,
    ):
        self.client = client
        self.config = config or MDAPConfig()
        self.discriminator = Discriminator(client, config)
        self.red_flag_filter = RedFlagFilter(config)

    async def vote(
        self,
        step: Step,
        context: str,
        generator: Callable[[Step, str], Awaitable[LLMResponse]],
        language: Language = Language.PYTHON,
        k: Optional[int] = None,
        max_samples: Optional[int] = None,
    ) -> VoteResult:
        """
        Executa votação para um step.

        Args:
            step: Step a ser votado
            context: Contexto da tarefa
            generator: Função que gera candidatos
            language: Linguagem do código
            k: Margem de vitória (default: config.k)
            max_samples: Máximo de amostras (default: config.max_samples)

        Returns:
            VoteResult com vencedor e estatísticas
        """
        k = k or self.config.k
        max_samples = max_samples or self.config.max_samples

        self.discriminator.reset()
        session = VotingSession(step=step, context=context)

        logger.info(f"Starting vote for step {step.id}: {step.description}")

        while len(session.samples) < max_samples and not session.is_complete:
            # 1. Gera candidato
            try:
                response = await generator(step, context)
                candidate = Candidate(
                    code=response.content,
                    tokens_used=response.tokens_output,
                )
                session.samples.append(candidate)
            except Exception as e:
                logger.warning(f"Generation failed: {e}")
                continue

            # 2. Aplica red-flags
            flag_result = self.red_flag_filter.check(candidate, language)
            if not flag_result.passed:
                candidate.is_valid = False
                candidate.red_flag_reason = flag_result.reason
                session.invalid_samples.append(candidate)
                logger.debug(f"Red-flagged: {flag_result.reason}")
                continue

            session.valid_samples.append(candidate)

            # 3. Classifica em grupo semântico
            await self.discriminator.classify(candidate, context)

            # 4. Verifica se há vencedor
            winner = self.discriminator.get_winner(k)
            if winner:
                session.is_complete = True
                session.winner = winner
                logger.info(
                    f"Winner found after {len(session.samples)} samples: "
                    f"{winner.id} with {winner.votes} votes"
                )

        # Monta resultado
        if session.winner:
            winner_candidate = session.winner.representative
        elif self.discriminator.groups:
            # Sem vencedor claro, pega grupo com mais votos
            sorted_groups = sorted(
                self.discriminator.groups.values(),
                key=lambda g: g.votes,
                reverse=True,
            )
            winner_candidate = sorted_groups[0].representative
            session.winner = sorted_groups[0]
        else:
            # Nenhum candidato válido
            raise ValueError(f"No valid candidates for step {step.id}")

        votes_per_group = {
            g.id: g.votes for g in self.discriminator.groups.values()
        }
        winning_margin = 0
        if len(votes_per_group) > 1:
            sorted_votes = sorted(votes_per_group.values(), reverse=True)
            winning_margin = sorted_votes[0] - sorted_votes[1]

        return VoteResult(
            winner=winner_candidate,
            groups={
                g.id: g.members for g in self.discriminator.groups.values()
            },
            votes_per_group=votes_per_group,
            total_samples=len(session.samples),
            winning_margin=winning_margin,
        )

    async def vote_parallel(
        self,
        step: Step,
        context: str,
        generator: Callable[[Step, str], Awaitable[LLMResponse]],
        language: Language = Language.PYTHON,
        k: Optional[int] = None,
        batch_size: int = 3,
    ) -> VoteResult:
        """
        Votação com geração paralela em batches.

        Gera batch_size candidatos em paralelo, depois classifica.
        Mais rápido mas usa mais tokens.
        """
        k = k or self.config.k
        max_samples = self.config.max_samples

        self.discriminator.reset()
        session = VotingSession(step=step, context=context)

        logger.info(f"Starting parallel vote (batch={batch_size}) for {step.id}")

        while len(session.samples) < max_samples and not session.is_complete:
            # Gera batch em paralelo
            tasks = [
                generator(step, context)
                for _ in range(min(batch_size, max_samples - len(session.samples)))
            ]
            responses = await asyncio.gather(*tasks, return_exceptions=True)

            for response in responses:
                if isinstance(response, Exception):
                    logger.warning(f"Batch generation failed: {response}")
                    continue

                candidate = Candidate(
                    code=response.content,
                    tokens_used=response.tokens_output,
                )
                session.samples.append(candidate)

                # Red-flag check
                flag_result = self.red_flag_filter.check(candidate, language)
                if not flag_result.passed:
                    candidate.is_valid = False
                    candidate.red_flag_reason = flag_result.reason
                    session.invalid_samples.append(candidate)
                    continue

                session.valid_samples.append(candidate)
                await self.discriminator.classify(candidate, context)

            # Verifica vencedor após batch
            winner = self.discriminator.get_winner(k)
            if winner:
                session.is_complete = True
                session.winner = winner

        # Mesmo resultado que vote()
        return self._build_result(session)

    def _build_result(self, session: VotingSession) -> VoteResult:
        """Constrói VoteResult a partir de sessão."""
        if session.winner:
            winner_candidate = session.winner.representative
        elif self.discriminator.groups:
            sorted_groups = sorted(
                self.discriminator.groups.values(),
                key=lambda g: g.votes,
                reverse=True,
            )
            winner_candidate = sorted_groups[0].representative
        else:
            raise ValueError(f"No valid candidates for step {session.step.id}")

        votes_per_group = {
            g.id: g.votes for g in self.discriminator.groups.values()
        }
        winning_margin = 0
        if len(votes_per_group) > 1:
            sorted_votes = sorted(votes_per_group.values(), reverse=True)
            winning_margin = sorted_votes[0] - sorted_votes[1]

        return VoteResult(
            winner=winner_candidate,
            groups={
                g.id: g.members for g in self.discriminator.groups.values()
            },
            votes_per_group=votes_per_group,
            total_samples=len(session.samples),
            winning_margin=winning_margin,
        )


async def first_to_ahead_by_k(
    step: Step,
    context: str,
    client: ClaudeClient,
    k: int = 3,
    max_samples: int = 20,
    language: Language = Language.PYTHON,
) -> VoteResult:
    """
    Helper function para votação simples.

    Args:
        step: Step a votar
        context: Contexto
        client: Cliente Claude
        k: Margem de vitória
        max_samples: Máximo de amostras
        language: Linguagem

    Returns:
        VoteResult
    """
    async def default_generator(s: Step, ctx: str) -> LLMResponse:
        return await client.generate_code(
            specification=s.description,
            context=ctx,
            language=language.value,
        )

    config = MDAPConfig(k=k, max_samples=max_samples)
    voter = Voter(client, config)

    return await voter.vote(
        step=step,
        context=context,
        generator=default_generator,
        language=language,
        k=k,
        max_samples=max_samples,
    )
