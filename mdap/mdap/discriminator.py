"""
LLM Discriminator - Compara candidatos semanticamente

Usa Claude para determinar se dois códigos são equivalentes.
Agrupa candidatos por equivalência semântica para votação.
"""
import asyncio
from typing import Optional
from dataclasses import dataclass, field

from ..types import Candidate, MDAPConfig
from ..llm.client import ClaudeClient


@dataclass
class SemanticGroup:
    """Grupo de candidatos semanticamente equivalentes."""
    id: str
    representative: Candidate  # primeiro candidato do grupo
    members: list[Candidate] = field(default_factory=list)

    @property
    def votes(self) -> int:
        """Número de votos (membros) no grupo."""
        return len(self.members)

    def add(self, candidate: Candidate) -> None:
        """Adiciona candidato ao grupo."""
        candidate.group_id = self.id
        self.members.append(candidate)


class Discriminator:
    """Compara candidatos e agrupa por equivalência semântica."""

    def __init__(
        self,
        client: ClaudeClient,
        config: Optional[MDAPConfig] = None,
    ):
        self.client = client
        self.config = config or MDAPConfig()
        self.groups: dict[str, SemanticGroup] = {}
        self._comparison_cache: dict[tuple[str, str], bool] = {}

    async def compare(
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
        # Normaliza para cache
        key = self._cache_key(code_a, code_b)
        if key in self._comparison_cache:
            return self._comparison_cache[key]

        # Chama LLM
        result = await self.client.compare_semantic(code_a, code_b, context)

        # Cacheia resultado (bidirecional)
        self._comparison_cache[key] = result
        self._comparison_cache[self._cache_key(code_b, code_a)] = result

        return result

    async def find_group(
        self,
        candidate: Candidate,
        context: str = "",
    ) -> Optional[SemanticGroup]:
        """
        Encontra grupo existente para candidato.

        Args:
            candidate: Candidato a classificar
            context: Contexto da tarefa

        Returns:
            SemanticGroup se encontrou equivalente, None se novo
        """
        for group in self.groups.values():
            if await self.compare(
                candidate.code,
                group.representative.code,
                context,
            ):
                return group
        return None

    async def classify(
        self,
        candidate: Candidate,
        context: str = "",
    ) -> SemanticGroup:
        """
        Classifica candidato em grupo existente ou cria novo.

        Args:
            candidate: Candidato a classificar
            context: Contexto da tarefa

        Returns:
            SemanticGroup onde o candidato foi adicionado
        """
        # Procura grupo existente
        group = await self.find_group(candidate, context)

        if group:
            group.add(candidate)
        else:
            # Cria novo grupo
            group_id = f"group_{len(self.groups)}"
            group = SemanticGroup(
                id=group_id,
                representative=candidate,
                members=[candidate],
            )
            candidate.group_id = group_id
            self.groups[group_id] = group

        return group

    async def classify_batch(
        self,
        candidates: list[Candidate],
        context: str = "",
    ) -> dict[str, SemanticGroup]:
        """
        Classifica múltiplos candidatos.

        Args:
            candidates: Lista de candidatos
            context: Contexto da tarefa

        Returns:
            Dict de grupos resultantes
        """
        for candidate in candidates:
            await self.classify(candidate, context)
        return dict(self.groups)

    def get_winner(self, k: int = 3) -> Optional[SemanticGroup]:
        """
        Retorna grupo vencedor se tiver k votos de vantagem.

        Args:
            k: Margem de vitória necessária

        Returns:
            SemanticGroup vencedor ou None se não há vencedor ainda
        """
        if not self.groups:
            return None

        sorted_groups = sorted(
            self.groups.values(),
            key=lambda g: g.votes,
            reverse=True,
        )

        leader = sorted_groups[0]
        runner_up_votes = sorted_groups[1].votes if len(sorted_groups) > 1 else 0

        if leader.votes - runner_up_votes >= k:
            return leader

        return None

    def reset(self) -> None:
        """Limpa grupos e cache para nova votação."""
        self.groups.clear()
        self._comparison_cache.clear()

    def _cache_key(self, code_a: str, code_b: str) -> tuple[str, str]:
        """Gera chave de cache normalizada."""
        return (code_a.strip(), code_b.strip())

    def stats(self) -> dict:
        """Retorna estatísticas da sessão."""
        return {
            "groups": len(self.groups),
            "total_candidates": sum(g.votes for g in self.groups.values()),
            "cache_hits": len(self._comparison_cache),
            "group_sizes": {g.id: g.votes for g in self.groups.values()},
        }


async def are_semantically_equivalent(
    code_a: str,
    code_b: str,
    context: str = "",
    client: Optional[ClaudeClient] = None,
) -> bool:
    """
    Função helper para comparar dois códigos.

    Args:
        code_a: Primeiro código
        code_b: Segundo código
        context: Contexto opcional
        client: Cliente Claude (cria novo se não fornecido)

    Returns:
        True se semanticamente equivalentes
    """
    from ..llm.client import get_client

    client = client or get_client()
    return await client.compare_semantic(code_a, code_b, context)
