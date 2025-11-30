"""
Agent Context - Gerencia estado durante execução

O Context é MUTÁVEL e cresce durante a execução.
Cada decisão MDAP recebe um SNAPSHOT imutável.
"""
from typing import Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import json

from ..types import (
    Context,
    ContextSnapshot,
    Step,
    StepType,
    ExecutionResult,
    Language,
    MDAPConfig,
)


@dataclass
class AgentMetrics:
    """Métricas de execução do agente."""
    steps_total: int = 0
    steps_expand: int = 0
    steps_decompose: int = 0
    steps_generate: int = 0
    steps_validate: int = 0
    steps_execute: int = 0

    tokens_input: int = 0
    tokens_output: int = 0

    mdap_votes_total: int = 0
    mdap_samples_total: int = 0

    errors_count: int = 0
    red_flags_count: int = 0

    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    @property
    def duration_seconds(self) -> float:
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()

    @property
    def tokens_total(self) -> int:
        return self.tokens_input + self.tokens_output

    def to_dict(self) -> dict:
        return {
            "steps_total": self.steps_total,
            "steps_by_type": {
                "expand": self.steps_expand,
                "decompose": self.steps_decompose,
                "generate": self.steps_generate,
                "validate": self.steps_validate,
                "execute": self.steps_execute,
            },
            "tokens": {
                "input": self.tokens_input,
                "output": self.tokens_output,
                "total": self.tokens_total,
            },
            "mdap": {
                "votes_total": self.mdap_votes_total,
                "samples_total": self.mdap_samples_total,
            },
            "errors": self.errors_count,
            "red_flags": self.red_flags_count,
            "duration_seconds": self.duration_seconds,
        }


class AgentContext:
    """Gerencia estado do agente durante execução."""

    def __init__(
        self,
        task: str,
        language: Language = Language.PYTHON,
        config: Optional[MDAPConfig] = None,
    ):
        self.task = task
        self.language = language
        self.config = config or MDAPConfig()

        # Estado interno
        self._context = Context(task=task, language=language)
        self._metrics = AgentMetrics()
        self._log: list[dict] = []

    @property
    def context(self) -> Context:
        """Contexto mutável."""
        return self._context

    @property
    def metrics(self) -> AgentMetrics:
        """Métricas de execução."""
        return self._metrics

    @property
    def is_complete(self) -> bool:
        """Se tarefa está completa."""
        return self._context.is_complete

    def snapshot(self) -> ContextSnapshot:
        """Cria snapshot imutável para MDAP."""
        return self._context.snapshot()

    # --- Ações ---

    def add_requirements(self, requirements: list[str]) -> None:
        """Adiciona requisitos expandidos."""
        for req in requirements:
            self._context.add_requirement(req)
        self._log_event("requirements_added", {"count": len(requirements)})

    def add_functions(self, functions: list[Step]) -> None:
        """Adiciona funções decompostas."""
        for func in functions:
            self._context.add_function(func)
        self._log_event("functions_added", {"count": len(functions)})

    def add_generated_code(self, step: Step, code: str) -> None:
        """Adiciona código gerado."""
        self._context.add_code(step, code)
        self._log_event("code_generated", {
            "step_id": step.id,
            "signature": step.signature,
            "code_length": len(code),
        })

    def add_execution_result(self, step: Step, result: ExecutionResult) -> None:
        """Adiciona resultado de execução."""
        self._context.add_result(step, result)
        self._log_event("execution_result", {
            "step_id": step.id,
            "success": result.success,
            "error": result.error,
        })
        if not result.success:
            self._metrics.errors_count += 1

    def mark_complete(self) -> None:
        """Marca tarefa como completa."""
        self._context.mark_complete()
        self._metrics.end_time = datetime.now()
        self._log_event("task_complete", {})

    # --- Métricas ---

    def record_step(self, step: Step) -> None:
        """Registra execução de step."""
        self._metrics.steps_total += 1

        if step.type == StepType.EXPAND:
            self._metrics.steps_expand += 1
        elif step.type == StepType.DECOMPOSE:
            self._metrics.steps_decompose += 1
        elif step.type == StepType.GENERATE:
            self._metrics.steps_generate += 1
        elif step.type == StepType.VALIDATE:
            self._metrics.steps_validate += 1
        elif step.type in (StepType.READ, StepType.SEARCH, StepType.TEST, StepType.APPLY):
            self._metrics.steps_execute += 1

    def record_tokens(self, input_tokens: int, output_tokens: int) -> None:
        """Registra uso de tokens."""
        self._metrics.tokens_input += input_tokens
        self._metrics.tokens_output += output_tokens

    def record_mdap_vote(self, samples: int) -> None:
        """Registra votação MDAP."""
        self._metrics.mdap_votes_total += 1
        self._metrics.mdap_samples_total += samples

    def record_red_flag(self) -> None:
        """Registra red flag."""
        self._metrics.red_flags_count += 1

    # --- Log ---

    def _log_event(self, event: str, data: dict) -> None:
        """Log interno de eventos."""
        self._log.append({
            "timestamp": datetime.now().isoformat(),
            "event": event,
            "data": data,
        })

    def get_log(self) -> list[dict]:
        """Retorna log de eventos."""
        return list(self._log)

    # --- Resultado ---

    def final_result(self) -> dict:
        """Retorna resultado final."""
        return {
            "task": self.task,
            "language": self.language.value,
            "requirements": list(self._context.requirements),
            "functions": [
                {"id": f.id, "signature": f.signature, "description": f.description}
                for f in self._context.functions
            ],
            "code": self._context.final_result(),
            "metrics": self._metrics.to_dict(),
            "log": self._log,
        }

    def to_json(self) -> str:
        """Serializa para JSON."""
        return json.dumps(self.final_result(), indent=2)

    def save(self, path: str) -> None:
        """Salva resultado em arquivo."""
        with open(path, "w") as f:
            f.write(self.to_json())
