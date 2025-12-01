"""
Resource Manager - Rastreia e gerencia consumo de recursos

Monitora tokens, chamadas API, tempo e custo estimado.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class BudgetStatus(Enum):
    """Status do budget."""
    OK = "ok"               # Dentro do limite
    WARNING = "warning"     # Acima de 80%
    EXCEEDED = "exceeded"   # Acima de 100%


# Preços estimados (Claude API)
PRICE_PER_1K_INPUT_TOKENS = 0.003   # $3 per million
PRICE_PER_1K_OUTPUT_TOKENS = 0.015  # $15 per million


@dataclass
class ResourceUsage:
    """Uso de recursos acumulado."""
    tokens_input: int = 0
    tokens_output: int = 0
    api_calls: int = 0
    elapsed_seconds: float = 0.0

    @property
    def tokens_total(self) -> int:
        """Total de tokens."""
        return self.tokens_input + self.tokens_output

    @property
    def estimated_cost_usd(self) -> float:
        """Custo estimado em USD."""
        input_cost = (self.tokens_input / 1000) * PRICE_PER_1K_INPUT_TOKENS
        output_cost = (self.tokens_output / 1000) * PRICE_PER_1K_OUTPUT_TOKENS
        return input_cost + output_cost

    def __add__(self, other: "ResourceUsage") -> "ResourceUsage":
        """Soma dois usos de recursos."""
        return ResourceUsage(
            tokens_input=self.tokens_input + other.tokens_input,
            tokens_output=self.tokens_output + other.tokens_output,
            api_calls=self.api_calls + other.api_calls,
            elapsed_seconds=self.elapsed_seconds + other.elapsed_seconds,
        )

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "tokens_total": self.tokens_total,
            "api_calls": self.api_calls,
            "elapsed_seconds": self.elapsed_seconds,
            "estimated_cost_usd": self.estimated_cost_usd,
        }


@dataclass
class ResourceBudget:
    """Limites de recursos."""
    max_tokens: Optional[int] = None
    max_api_calls: Optional[int] = None
    max_time_seconds: Optional[float] = None
    max_cost_usd: Optional[float] = None

    def is_empty(self) -> bool:
        """Verifica se nenhum limite foi definido."""
        return all([
            self.max_tokens is None,
            self.max_api_calls is None,
            self.max_time_seconds is None,
            self.max_cost_usd is None,
        ])


@dataclass
class ResourceCheck:
    """Resultado de verificação de budget."""
    status: BudgetStatus
    message: str
    tokens_percent: float = 0.0
    calls_percent: float = 0.0
    time_percent: float = 0.0
    cost_percent: float = 0.0


class ResourceManager:
    """
    Gerencia e monitora recursos do pipeline.

    Funcionalidades:
    - Rastreia tokens, chamadas, tempo, custo
    - Verifica budget e emite warnings
    - Estima recursos restantes
    """

    def __init__(self, budget: Optional[ResourceBudget] = None):
        """
        Args:
            budget: Limites de recursos (opcional)
        """
        self.budget = budget or ResourceBudget()
        self._usage = ResourceUsage()
        self._started_at: Optional[datetime] = None
        self._history: list[ResourceUsage] = []

    def start_tracking(self) -> None:
        """Inicia rastreamento de tempo."""
        self._started_at = datetime.now()

    def stop_tracking(self) -> None:
        """Para rastreamento e salva tempo decorrido."""
        if self._started_at:
            elapsed = (datetime.now() - self._started_at).total_seconds()
            self._usage.elapsed_seconds = elapsed

    def track(
        self,
        tokens_input: int = 0,
        tokens_output: int = 0,
        api_calls: int = 1,
    ) -> None:
        """
        Registra uso de recursos.

        Args:
            tokens_input: Tokens de entrada
            tokens_output: Tokens de saída
            api_calls: Número de chamadas API
        """
        increment = ResourceUsage(
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            api_calls=api_calls,
        )
        self._usage = self._usage + increment
        self._history.append(increment)

    def track_simple(self, response_length: int) -> None:
        """
        Rastreamento simplificado baseado no tamanho da resposta.

        Estima tokens baseado em caracteres (~4 chars/token).
        """
        estimated_output = response_length // 4
        estimated_input = estimated_output // 3  # Assume prompt é ~1/3 da resposta
        self.track(
            tokens_input=estimated_input,
            tokens_output=estimated_output,
            api_calls=1,
        )

    def get_usage(self) -> ResourceUsage:
        """Retorna uso atual de recursos."""
        # Atualiza tempo se estiver rastreando
        if self._started_at:
            self._usage.elapsed_seconds = (datetime.now() - self._started_at).total_seconds()
        return self._usage

    def check_budget(self) -> ResourceCheck:
        """
        Verifica se está dentro do budget.

        Returns:
            ResourceCheck com status e percentuais
        """
        usage = self.get_usage()

        if self.budget.is_empty():
            return ResourceCheck(
                status=BudgetStatus.OK,
                message="Sem limite definido",
            )

        # Calcula percentuais
        tokens_pct = 0.0
        calls_pct = 0.0
        time_pct = 0.0
        cost_pct = 0.0

        if self.budget.max_tokens:
            tokens_pct = (usage.tokens_total / self.budget.max_tokens) * 100

        if self.budget.max_api_calls:
            calls_pct = (usage.api_calls / self.budget.max_api_calls) * 100

        if self.budget.max_time_seconds:
            time_pct = (usage.elapsed_seconds / self.budget.max_time_seconds) * 100

        if self.budget.max_cost_usd:
            cost_pct = (usage.estimated_cost_usd / self.budget.max_cost_usd) * 100

        # Determina status
        max_pct = max(tokens_pct, calls_pct, time_pct, cost_pct)

        if max_pct >= 100:
            status = BudgetStatus.EXCEEDED
            message = self._get_exceeded_message(tokens_pct, calls_pct, time_pct, cost_pct)
        elif max_pct >= 80:
            status = BudgetStatus.WARNING
            message = self._get_warning_message(tokens_pct, calls_pct, time_pct, cost_pct)
        else:
            status = BudgetStatus.OK
            message = f"Recursos OK ({max_pct:.0f}% do limite)"

        return ResourceCheck(
            status=status,
            message=message,
            tokens_percent=tokens_pct,
            calls_percent=calls_pct,
            time_percent=time_pct,
            cost_percent=cost_pct,
        )

    def _get_exceeded_message(self, tokens: float, calls: float, time: float, cost: float) -> str:
        """Gera mensagem de budget excedido."""
        exceeded = []
        if tokens >= 100:
            exceeded.append(f"tokens ({tokens:.0f}%)")
        if calls >= 100:
            exceeded.append(f"chamadas ({calls:.0f}%)")
        if time >= 100:
            exceeded.append(f"tempo ({time:.0f}%)")
        if cost >= 100:
            exceeded.append(f"custo ({cost:.0f}%)")
        return f"LIMITE EXCEDIDO: {', '.join(exceeded)}"

    def _get_warning_message(self, tokens: float, calls: float, time: float, cost: float) -> str:
        """Gera mensagem de warning."""
        warnings = []
        if tokens >= 80:
            warnings.append(f"tokens ({tokens:.0f}%)")
        if calls >= 80:
            warnings.append(f"chamadas ({calls:.0f}%)")
        if time >= 80:
            warnings.append(f"tempo ({time:.0f}%)")
        if cost >= 80:
            warnings.append(f"custo ({cost:.0f}%)")
        return f"WARNING: Aproximando do limite - {', '.join(warnings)}"

    def estimate_remaining(self, steps_left: int) -> ResourceUsage:
        """
        Estima recursos necessários para passos restantes.

        Args:
            steps_left: Número de passos restantes

        Returns:
            Estimativa de recursos
        """
        if not self._history or steps_left <= 0:
            return ResourceUsage()

        # Média por chamada
        total_calls = sum(h.api_calls for h in self._history)
        total_input = sum(h.tokens_input for h in self._history)
        total_output = sum(h.tokens_output for h in self._history)

        if total_calls == 0:
            return ResourceUsage()

        avg_input = total_input / total_calls
        avg_output = total_output / total_calls
        avg_time = self._usage.elapsed_seconds / total_calls if total_calls > 0 else 5.0

        return ResourceUsage(
            tokens_input=int(avg_input * steps_left),
            tokens_output=int(avg_output * steps_left),
            api_calls=steps_left,
            elapsed_seconds=avg_time * steps_left,
        )

    def predict_total(self, steps_left: int) -> ResourceUsage:
        """
        Prediz uso total (atual + restante).

        Args:
            steps_left: Número de passos restantes

        Returns:
            Predição de uso total
        """
        return self.get_usage() + self.estimate_remaining(steps_left)

    def reset(self) -> None:
        """Reseta contadores."""
        self._usage = ResourceUsage()
        self._history.clear()
        self._started_at = None

    def set_budget(
        self,
        max_tokens: Optional[int] = None,
        max_api_calls: Optional[int] = None,
        max_time_seconds: Optional[float] = None,
        max_cost_usd: Optional[float] = None,
    ) -> None:
        """Define limites de budget."""
        self.budget = ResourceBudget(
            max_tokens=max_tokens,
            max_api_calls=max_api_calls,
            max_time_seconds=max_time_seconds,
            max_cost_usd=max_cost_usd,
        )

    def to_summary(self) -> str:
        """Gera resumo textual do uso de recursos."""
        usage = self.get_usage()
        check = self.check_budget()

        lines = [
            "Uso de Recursos:",
            f"  Tokens: {usage.tokens_total:,} ({usage.tokens_input:,} in / {usage.tokens_output:,} out)",
            f"  Chamadas API: {usage.api_calls}",
            f"  Tempo: {usage.elapsed_seconds:.1f}s",
            f"  Custo estimado: ${usage.estimated_cost_usd:.4f}",
            "",
            f"Status: {check.status.value.upper()}",
            f"  {check.message}",
        ]

        if not self.budget.is_empty():
            lines.extend([
                "",
                "Limites:",
            ])
            if self.budget.max_tokens:
                lines.append(f"  Tokens: {usage.tokens_total:,} / {self.budget.max_tokens:,} ({check.tokens_percent:.0f}%)")
            if self.budget.max_api_calls:
                lines.append(f"  Chamadas: {usage.api_calls} / {self.budget.max_api_calls} ({check.calls_percent:.0f}%)")
            if self.budget.max_time_seconds:
                lines.append(f"  Tempo: {usage.elapsed_seconds:.1f}s / {self.budget.max_time_seconds:.1f}s ({check.time_percent:.0f}%)")
            if self.budget.max_cost_usd:
                lines.append(f"  Custo: ${usage.estimated_cost_usd:.4f} / ${self.budget.max_cost_usd:.4f} ({check.cost_percent:.0f}%)")

        return "\n".join(lines)
