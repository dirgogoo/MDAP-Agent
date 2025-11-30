"""
MDAP Agent Types - Dataclasses compartilhadas

Define os tipos fundamentais usados em todo o framework:
- Step: passo atômico (uma função/método)
- Context: estado do agente durante execução
- Candidate: candidato de código para votação
- VoteResult: resultado da votação MDAP
"""
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum
from datetime import datetime
import uuid


class Language(Enum):
    """Linguagens suportadas pelo framework."""
    PYTHON = "python"
    TYPESCRIPT = "typescript"


class StepType(Enum):
    """Tipo de passo no agent loop."""
    # Decisão (usa MDAP)
    EXPAND = "expand"          # Gerar requisitos atômicos
    DECOMPOSE = "decompose"    # Organizar em funções
    GENERATE = "generate"      # Implementar código
    VALIDATE = "validate"      # Verificar correção
    DECIDE = "decide"          # Escolher próximo passo

    # Execução (sem MDAP)
    READ = "read"              # Ler arquivo
    SEARCH = "search"          # Buscar código
    TEST = "test"              # Rodar testes
    APPLY = "apply"            # Aplicar edição

    # Controle
    DONE = "done"              # Tarefa completa


@dataclass
class Step:
    """Um passo atômico (uma função/método ou ação)."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: StepType = StepType.DECIDE
    description: str = ""
    signature: str = ""          # ex: "def validate_token(token: str) -> dict"
    context: str = ""            # dependências, imports necessários
    action: Optional[str] = None # para execução: comando/path
    specification: Optional[str] = None  # para geração: spec detalhada

    def __post_init__(self):
        if isinstance(self.type, str):
            self.type = StepType(self.type)


@dataclass
class Candidate:
    """Um candidato de código para um Step."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    code: str = ""
    tokens_used: int = 0
    is_valid: bool = True          # passou red-flags?
    red_flag_reason: Optional[str] = None
    group_id: Optional[str] = None # grupo semântico após votação

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if isinstance(other, Candidate):
            return self.id == other.id
        return False


@dataclass
class VoteResult:
    """Resultado da votação MDAP para um Step."""
    winner: Candidate
    groups: dict[str, list[Candidate]] = field(default_factory=dict)
    votes_per_group: dict[str, int] = field(default_factory=dict)
    total_samples: int = 0
    winning_margin: int = 0

    @property
    def winner_votes(self) -> int:
        """Número de votos do vencedor."""
        if self.winner.group_id and self.winner.group_id in self.votes_per_group:
            return self.votes_per_group[self.winner.group_id]
        return 0


@dataclass
class ExecutionResult:
    """Resultado de uma operação de execução (sem MDAP)."""
    success: bool
    output: str = ""
    error: Optional[str] = None
    data: Any = None  # dados estruturados (ex: conteúdo de arquivo)


@dataclass
class ContextSnapshot:
    """Snapshot imutável do contexto para MDAP."""
    task: str
    requirements: list[str] = field(default_factory=list)
    functions: list[Step] = field(default_factory=list)
    generated_code: dict[str, str] = field(default_factory=dict)  # step_id -> code
    execution_results: list[tuple[Step, ExecutionResult]] = field(default_factory=list)
    current_step: Optional[Step] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_prompt_context(self) -> str:
        """Converte para texto que pode ser incluído em prompts."""
        lines = [f"# Task: {self.task}", ""]

        if self.requirements:
            lines.append("## Requirements:")
            for i, req in enumerate(self.requirements, 1):
                lines.append(f"{i}. {req}")
            lines.append("")

        if self.functions:
            lines.append("## Functions to implement:")
            for func in self.functions:
                lines.append(f"- {func.signature}: {func.description}")
            lines.append("")

        if self.generated_code:
            lines.append("## Generated code so far:")
            for step_id, code in self.generated_code.items():
                lines.append(f"### {step_id}")
                lines.append(f"```python\n{code}\n```")
            lines.append("")

        if self.execution_results:
            lines.append("## Execution results:")
            for step, result in self.execution_results[-5:]:  # últimos 5
                status = "OK" if result.success else "FAIL"
                lines.append(f"- [{status}] {step.description}")
                if result.output:
                    lines.append(f"  Output: {result.output[:200]}...")
            lines.append("")

        return "\n".join(lines)


@dataclass
class Context:
    """Estado mutável do agente durante execução."""
    task: str
    language: Language = Language.PYTHON
    requirements: list[str] = field(default_factory=list)
    functions: list[Step] = field(default_factory=list)
    generated_code: dict[str, str] = field(default_factory=dict)
    execution_results: list[tuple[Step, ExecutionResult]] = field(default_factory=list)
    current_step: Optional[Step] = None
    history: list[Step] = field(default_factory=list)
    is_complete: bool = False

    def snapshot(self) -> ContextSnapshot:
        """Cria snapshot imutável do contexto atual."""
        return ContextSnapshot(
            task=self.task,
            requirements=list(self.requirements),
            functions=list(self.functions),
            generated_code=dict(self.generated_code),
            execution_results=list(self.execution_results),
            current_step=self.current_step,
        )

    def add_requirement(self, requirement: str) -> None:
        """Adiciona requisito expandido."""
        if requirement not in self.requirements:
            self.requirements.append(requirement)

    def add_function(self, step: Step) -> None:
        """Adiciona função a ser implementada."""
        self.functions.append(step)

    def add_code(self, step: Step, code: str) -> None:
        """Adiciona código gerado para um step."""
        self.generated_code[step.id] = code
        self.history.append(step)

    def add_result(self, step: Step, result: ExecutionResult) -> None:
        """Adiciona resultado de execução."""
        self.execution_results.append((step, result))
        self.history.append(step)

    def mark_complete(self) -> None:
        """Marca tarefa como completa."""
        self.is_complete = True

    def final_result(self) -> dict[str, str]:
        """Retorna código final gerado."""
        return dict(self.generated_code)


@dataclass
class MDAPConfig:
    """Configuração do MDAP Agent."""
    k: int = 3                      # votos de vantagem para vencer
    max_samples: int = 20           # máximo de candidatos por step
    max_tokens_response: int = 500  # red-flag para respostas longas
    temperature: float = 0.1        # temperatura do LLM
    model: str = "claude-3-haiku-20240307"  # modelo padrão

    # Timeouts
    vote_timeout_seconds: int = 60
    execution_timeout_seconds: int = 30

    # Red-flags
    enable_syntax_check: bool = True
    enable_length_check: bool = True
    enable_format_check: bool = True
