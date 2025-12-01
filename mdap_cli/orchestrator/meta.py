"""
Meta Intelligence - Explicações e introspecção do pipeline

Fornece explicações detalhadas sobre o que o orquestrador
está fazendo, por que tomou decisões, e análises de recursos.
"""
from typing import TYPE_CHECKING, Optional
from dataclasses import dataclass

from .state import PipelineState
from .tracker import DecisionTracker, DecisionPhase
from .resources import ResourceManager, BudgetStatus

if TYPE_CHECKING:
    from .orchestrator import MDAPOrchestrator


@dataclass
class StatusExplanation:
    """Explicação de status."""
    short: str      # Uma linha
    detailed: str   # Múltiplas linhas
    suggestions: list[str]  # Sugestões de ação


@dataclass
class PhaseExplanation:
    """Explicação de uma fase."""
    phase: str
    purpose: str
    current_progress: str
    what_happens_next: str


@dataclass
class WorkPrediction:
    """Predição de trabalho restante."""
    steps_remaining: int
    estimated_time_seconds: float
    estimated_tokens: int
    estimated_cost_usd: float
    confidence: str  # "alta", "média", "baixa"


class MetaIntelligence:
    """
    Fornece introspecção e explicações sobre o pipeline.

    Pode explicar:
    - Status atual (o que está fazendo)
    - Fases do pipeline (para que serve cada uma)
    - Decisões tomadas (por que escolheu X)
    - Votação MDAP (detalhes de candidatos e grupos)
    - Recursos (tokens, custo, tempo)
    - Predições (quanto falta)
    """

    def __init__(
        self,
        orchestrator: "MDAPOrchestrator",
        tracker: DecisionTracker,
        resources: ResourceManager,
    ):
        self.orchestrator = orchestrator
        self.tracker = tracker
        self.resources = resources

    # === Status ===

    def explain_status(self) -> StatusExplanation:
        """Explica status atual do pipeline."""
        state = self.orchestrator.state
        status = self.orchestrator.get_status()

        short = self._get_short_status(state.current, status)
        detailed = self._get_detailed_status(state.current, status)
        suggestions = self._get_suggestions(state.current)

        return StatusExplanation(
            short=short,
            detailed=detailed,
            suggestions=suggestions,
        )

    def _get_short_status(self, state: PipelineState, status) -> str:
        """Gera status curto de uma linha."""
        if state == PipelineState.IDLE:
            return "Aguardando tarefa"
        elif state == PipelineState.PAUSED:
            return f"Pausado ({status.progress_percent:.0f}% completo)"
        elif state == PipelineState.COMPLETED:
            return f"Concluído em {status.elapsed_seconds:.1f}s"
        elif state == PipelineState.ERROR:
            return f"Erro: {self.orchestrator.state.error_message}"
        else:
            return f"{status.state_name} - {status.phase_detail}"

    def _get_detailed_status(self, state: PipelineState, status) -> str:
        """Gera status detalhado."""
        lines = [
            f"Estado: {status.state_name}",
            f"Tarefa: {status.task or '(nenhuma)'}",
            f"Progresso: {status.progress_percent:.0f}%",
            "",
            "Resultados parciais:",
            f"  - Requisitos: {status.requirements_count}",
            f"  - Funções: {status.functions_count}",
            f"  - Código gerado: {status.code_count}",
            "",
            f"Tempo decorrido: {status.elapsed_seconds:.1f}s",
        ]

        if state == PipelineState.PAUSED:
            lines.extend([
                "",
                "Pipeline PAUSADO. Use /resume para continuar.",
            ])

        return "\n".join(lines)

    def _get_suggestions(self, state: PipelineState) -> list[str]:
        """Gera sugestões baseadas no estado."""
        suggestions = {
            PipelineState.IDLE: [
                "Use /run <tarefa> para iniciar",
                "Use /help para ver comandos disponíveis",
            ],
            PipelineState.PAUSED: [
                "Use /resume para continuar",
                "Use /cancel para cancelar",
                "Use /status para ver progresso",
            ],
            PipelineState.COMPLETED: [
                "Use /history para ver decisões tomadas",
                "Use /resources para ver consumo",
                "Use /run para nova tarefa",
            ],
            PipelineState.ERROR: [
                "Use /run para tentar novamente",
                "Use /explain para entender o erro",
            ],
        }
        return suggestions.get(state, ["Use /explain para mais detalhes"])

    # === Fases ===

    def explain_phase(self, phase: str) -> PhaseExplanation:
        """Explica uma fase do pipeline."""
        phase_info = {
            "expand": PhaseExplanation(
                phase="EXPAND",
                purpose="Analisar a tarefa e extrair requisitos atômicos individuais",
                current_progress=self._get_phase_progress("expand"),
                what_happens_next="Os requisitos serão organizados em funções (DECOMPOSE)",
            ),
            "decompose": PhaseExplanation(
                phase="DECOMPOSE",
                purpose="Organizar requisitos em funções com responsabilidades claras",
                current_progress=self._get_phase_progress("decompose"),
                what_happens_next="Cada função será implementada (GENERATE)",
            ),
            "generate": PhaseExplanation(
                phase="GENERATE",
                purpose="Implementar o código de cada função",
                current_progress=self._get_phase_progress("generate"),
                what_happens_next="O código será validado (VALIDATE)",
            ),
            "validate": PhaseExplanation(
                phase="VALIDATE",
                purpose="Verificar sintaxe e correção do código gerado",
                current_progress=self._get_phase_progress("validate"),
                what_happens_next="Pipeline concluído!",
            ),
        }

        return phase_info.get(phase.lower(), PhaseExplanation(
            phase=phase,
            purpose="Fase desconhecida",
            current_progress="N/A",
            what_happens_next="N/A",
        ))

    def _get_phase_progress(self, phase: str) -> str:
        """Retorna progresso de uma fase."""
        result = self.orchestrator.result
        state = self.orchestrator.state

        if phase == "expand":
            if result.requirements:
                return f"{len(result.requirements)} requisitos gerados"
            return "Gerando requisitos..."
        elif phase == "decompose":
            if result.functions:
                return f"{len(result.functions)} funções planejadas"
            return "Planejando funções..."
        elif phase == "generate":
            total = len(result.functions)
            done = len(result.code)
            if total > 0:
                return f"{done}/{total} funções implementadas"
            return "Aguardando funções..."
        elif phase == "validate":
            if result.validation_passed:
                return "Validação passou"
            return "Validando código..."

        return state.current_phase_detail

    # === Decisões ===

    def explain_decision(self, decision_id: str) -> str:
        """Explica uma decisão específica."""
        return self.tracker.explain_decision(decision_id)

    def explain_decisions_summary(self) -> str:
        """Resumo de todas as decisões."""
        return self.tracker.summarize()

    def explain_last_decision(self) -> str:
        """Explica a última decisão tomada."""
        history = self.tracker.get_history(limit=1)
        if not history:
            return "Nenhuma decisão registrada ainda."
        return history[0].to_explanation()

    # === Votação ===

    def explain_voting(self, decision_id: str) -> str:
        """Explica detalhes de votação de uma decisão."""
        decision = self.tracker.get_by_id(decision_id)
        if not decision:
            return f"Decisão {decision_id} não encontrada."

        if not decision.voting:
            return "Esta decisão não envolveu votação MDAP."

        return decision.voting.to_explanation()

    def explain_confidence(self) -> str:
        """Explica nível de confiança geral das decisões."""
        voting_decisions = [
            d for d in self.tracker.get_all()
            if d.voting
        ]

        if not voting_decisions:
            return "Nenhuma decisão com votação registrada."

        total = len(voting_decisions)
        high = sum(1 for d in voting_decisions if d.voting.confidence_level() == "alta")
        medium = sum(1 for d in voting_decisions if d.voting.confidence_level() == "média")
        low = total - high - medium

        avg_margin = sum(d.voting.winning_margin for d in voting_decisions) / total

        lines = [
            f"Análise de confiança ({total} decisões com votação):",
            "",
            f"  Alta confiança: {high} ({high/total*100:.0f}%)",
            f"  Média confiança: {medium} ({medium/total*100:.0f}%)",
            f"  Baixa confiança: {low} ({low/total*100:.0f}%)",
            "",
            f"Margem média de vitória: {avg_margin:.1f}",
            "",
        ]

        if low > total * 0.3:
            lines.append("AVISO: Muitas decisões com baixa confiança. Considere revisar.")
        elif high > total * 0.7:
            lines.append("BOM: Maioria das decisões com alta confiança.")
        else:
            lines.append("OK: Confiança geral moderada.")

        return "\n".join(lines)

    # === Recursos ===

    def explain_resources(self) -> str:
        """Explica uso de recursos."""
        return self.resources.to_summary()

    def explain_budget_status(self) -> str:
        """Explica status do budget."""
        check = self.resources.check_budget()

        lines = [f"Status: {check.status.value.upper()}"]

        if check.status == BudgetStatus.EXCEEDED:
            lines.append("ALERTA: Limite de recursos excedido!")
        elif check.status == BudgetStatus.WARNING:
            lines.append("AVISO: Aproximando do limite de recursos.")
        else:
            lines.append("Recursos dentro do esperado.")

        lines.extend([
            "",
            f"Tokens: {check.tokens_percent:.0f}%",
            f"Chamadas: {check.calls_percent:.0f}%",
            f"Tempo: {check.time_percent:.0f}%",
            f"Custo: {check.cost_percent:.0f}%",
        ])

        return "\n".join(lines)

    # === Predições ===

    def predict_remaining(self) -> WorkPrediction:
        """Prediz trabalho restante."""
        result = self.orchestrator.result

        # Estima passos restantes
        steps = 0
        if not result.requirements:
            steps += 1  # EXPAND
        if not result.functions:
            steps += 1  # DECOMPOSE
        steps += max(0, len(result.functions) - len(result.code))  # GENERATE
        if not result.validation_passed and result.code:
            steps += 1  # VALIDATE

        estimate = self.resources.estimate_remaining(steps)

        # Determina confiança baseado no histórico
        history_size = len(self.resources._history)
        if history_size >= 5:
            confidence = "alta"
        elif history_size >= 2:
            confidence = "média"
        else:
            confidence = "baixa"

        return WorkPrediction(
            steps_remaining=steps,
            estimated_time_seconds=estimate.elapsed_seconds,
            estimated_tokens=estimate.tokens_total,
            estimated_cost_usd=estimate.estimated_cost_usd,
            confidence=confidence,
        )

    def explain_prediction(self) -> str:
        """Explica predição de trabalho restante."""
        pred = self.predict_remaining()

        lines = [
            "Predição de trabalho restante:",
            "",
            f"  Passos restantes: {pred.steps_remaining}",
            f"  Tempo estimado: {pred.estimated_time_seconds:.0f}s",
            f"  Tokens estimados: {pred.estimated_tokens:,}",
            f"  Custo estimado: ${pred.estimated_cost_usd:.4f}",
            "",
            f"Confiança da predição: {pred.confidence}",
        ]

        if pred.confidence == "baixa":
            lines.append("(Poucos dados para predição precisa)")

        return "\n".join(lines)

    # === Explicação completa ===

    def explain_everything(self) -> str:
        """Gera explicação completa do estado atual."""
        sections = [
            "=" * 50,
            "MDAP ORCHESTRATOR - EXPLICAÇÃO COMPLETA",
            "=" * 50,
            "",
            "### STATUS ###",
            self.explain_status().detailed,
            "",
            "### FASE ATUAL ###",
            self.explain_phase(self.orchestrator.state.current.value).purpose,
            "",
            "### DECISÕES ###",
            self.explain_decisions_summary(),
            "",
            "### RECURSOS ###",
            self.explain_resources(),
            "",
            "### PREDIÇÃO ###",
            self.explain_prediction(),
            "",
            "=" * 50,
        ]

        return "\n".join(sections)
