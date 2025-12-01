"""
Decision Tracker - Rastreia decisões para explicabilidade

Registra todas as decisões tomadas durante a execução do pipeline
para permitir explicações detalhadas e análise posterior.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
from enum import Enum
import uuid


class DecisionPhase(Enum):
    """Fase em que a decisão foi tomada."""
    EXPAND = "expand"
    DECOMPOSE = "decompose"
    GENERATE = "generate"
    VALIDATE = "validate"


@dataclass
class VotingDetails:
    """Detalhes de uma votação MDAP."""
    candidates_total: int = 0
    candidates_valid: int = 0  # Após red-flag
    groups_formed: int = 0
    votes_per_group: dict[str, int] = field(default_factory=dict)
    winning_group: str = ""
    winning_margin: int = 0
    k_threshold: int = 3
    max_samples: int = 20
    samples_used: int = 0

    def confidence_level(self) -> str:
        """Retorna nível de confiança baseado na margem."""
        if self.winning_margin >= 5:
            return "alta"
        elif self.winning_margin >= 3:
            return "média"
        else:
            return "baixa"

    def to_explanation(self) -> str:
        """Gera explicação textual da votação."""
        lines = [
            f"Candidatos gerados: {self.candidates_total}",
            f"Candidatos válidos (pós red-flag): {self.candidates_valid}",
            f"Grupos semânticos formados: {self.groups_formed}",
        ]

        if self.votes_per_group:
            lines.append("Votos por grupo:")
            for group, votes in sorted(self.votes_per_group.items(), key=lambda x: -x[1]):
                marker = " <-- VENCEDOR" if group == self.winning_group else ""
                lines.append(f"  {group}: {votes} votos{marker}")

        lines.extend([
            f"Margem de vitória: {self.winning_margin} (threshold k={self.k_threshold})",
            f"Confiança: {self.confidence_level()}",
            f"Amostras utilizadas: {self.samples_used}/{self.max_samples}",
        ])

        return "\n".join(lines)


@dataclass
class DecisionRecord:
    """Registro de uma decisão tomada."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.now)
    phase: DecisionPhase = DecisionPhase.EXPAND
    description: str = ""  # O que foi decidido
    input_context: str = ""  # Contexto de entrada
    output_result: str = ""  # Resultado da decisão
    rationale: str = ""  # Por que essa decisão foi tomada
    voting: Optional[VotingDetails] = None
    alternatives_considered: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_summary(self) -> str:
        """Resumo curto da decisão."""
        return f"[{self.id}] {self.phase.value}: {self.description[:50]}..."

    def to_explanation(self) -> str:
        """Explicação completa da decisão."""
        lines = [
            f"Decisão: {self.id}",
            f"Timestamp: {self.timestamp.strftime('%H:%M:%S')}",
            f"Fase: {self.phase.value.upper()}",
            f"",
            f"Descrição: {self.description}",
            f"",
            f"Contexto de entrada:",
            f"  {self.input_context[:200]}{'...' if len(self.input_context) > 200 else ''}",
            f"",
            f"Resultado:",
            f"  {self.output_result[:200]}{'...' if len(self.output_result) > 200 else ''}",
            f"",
            f"Rationale: {self.rationale}",
        ]

        if self.voting:
            lines.extend([
                f"",
                f"Detalhes da Votação MDAP:",
                self.voting.to_explanation(),
            ])

        if self.alternatives_considered:
            lines.extend([
                f"",
                f"Alternativas consideradas:",
            ])
            for alt in self.alternatives_considered[:5]:
                lines.append(f"  - {alt[:80]}...")

        return "\n".join(lines)


class DecisionTracker:
    """
    Rastreia todas as decisões do pipeline.

    Permite:
    - Registrar decisões com contexto
    - Consultar histórico
    - Gerar explicações
    - Analisar padrões
    """

    def __init__(self):
        self._decisions: list[DecisionRecord] = []
        self._by_phase: dict[DecisionPhase, list[DecisionRecord]] = {
            phase: [] for phase in DecisionPhase
        }

    def record(self, decision: DecisionRecord) -> str:
        """
        Registra uma decisão.

        Args:
            decision: Registro da decisão

        Returns:
            ID da decisão registrada
        """
        self._decisions.append(decision)
        self._by_phase[decision.phase].append(decision)
        return decision.id

    def record_simple(
        self,
        phase: DecisionPhase,
        description: str,
        input_context: str,
        output_result: str,
        rationale: str = "",
    ) -> str:
        """
        Registra decisão de forma simplificada.

        Returns:
            ID da decisão registrada
        """
        decision = DecisionRecord(
            phase=phase,
            description=description,
            input_context=input_context,
            output_result=output_result,
            rationale=rationale,
        )
        return self.record(decision)

    def record_with_voting(
        self,
        phase: DecisionPhase,
        description: str,
        input_context: str,
        output_result: str,
        voting: VotingDetails,
        rationale: str = "",
    ) -> str:
        """
        Registra decisão com detalhes de votação MDAP.

        Returns:
            ID da decisão registrada
        """
        decision = DecisionRecord(
            phase=phase,
            description=description,
            input_context=input_context,
            output_result=output_result,
            voting=voting,
            rationale=rationale or f"Venceu por margem de {voting.winning_margin}",
        )
        return self.record(decision)

    def get_by_id(self, decision_id: str) -> Optional[DecisionRecord]:
        """Busca decisão por ID."""
        for d in self._decisions:
            if d.id == decision_id:
                return d
        return None

    def get_history(self, limit: int = 10) -> list[DecisionRecord]:
        """Retorna últimas N decisões."""
        return self._decisions[-limit:]

    def get_by_phase(self, phase: DecisionPhase) -> list[DecisionRecord]:
        """Retorna decisões de uma fase específica."""
        return self._by_phase[phase].copy()

    def get_all(self) -> list[DecisionRecord]:
        """Retorna todas as decisões."""
        return self._decisions.copy()

    def count(self) -> int:
        """Retorna número total de decisões."""
        return len(self._decisions)

    def count_by_phase(self) -> dict[str, int]:
        """Retorna contagem por fase."""
        return {
            phase.value: len(decisions)
            for phase, decisions in self._by_phase.items()
        }

    def clear(self) -> None:
        """Limpa todas as decisões."""
        self._decisions.clear()
        for phase in DecisionPhase:
            self._by_phase[phase].clear()

    def summarize(self) -> str:
        """Gera resumo das decisões."""
        if not self._decisions:
            return "Nenhuma decisão registrada ainda."

        lines = [
            f"Total de decisões: {len(self._decisions)}",
            "",
            "Por fase:",
        ]

        for phase, decisions in self._by_phase.items():
            if decisions:
                lines.append(f"  {phase.value.upper()}: {len(decisions)}")

        # Últimas 3 decisões
        lines.extend(["", "Últimas decisões:"])
        for d in self._decisions[-3:]:
            lines.append(f"  - {d.to_summary()}")

        # Confiança média
        voting_decisions = [d for d in self._decisions if d.voting]
        if voting_decisions:
            avg_margin = sum(d.voting.winning_margin for d in voting_decisions) / len(voting_decisions)
            lines.extend([
                "",
                f"Margem média de votação: {avg_margin:.1f}",
            ])

        return "\n".join(lines)

    def explain_decision(self, decision_id: str) -> str:
        """Gera explicação para uma decisão específica."""
        decision = self.get_by_id(decision_id)
        if decision is None:
            return f"Decisão {decision_id} não encontrada."
        return decision.to_explanation()

    def explain_phase(self, phase: DecisionPhase) -> str:
        """Gera explicação de todas as decisões de uma fase."""
        decisions = self._by_phase[phase]
        if not decisions:
            return f"Nenhuma decisão na fase {phase.value}."

        lines = [
            f"Fase {phase.value.upper()}: {len(decisions)} decisões",
            "",
        ]

        for i, d in enumerate(decisions, 1):
            lines.append(f"{i}. {d.to_summary()}")
            if d.voting:
                lines.append(f"   Confiança: {d.voting.confidence_level()} (margem {d.voting.winning_margin})")

        return "\n".join(lines)
