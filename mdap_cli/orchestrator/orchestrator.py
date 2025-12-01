"""
MDAP Orchestrator - Coordenador Principal

Integra REPL com pipeline MDAP, gerencia estado,
interrupções e meta-inteligência.
"""
from typing import TYPE_CHECKING, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

from .state import PipelineState, OrchestratorState, EXECUTION_PHASES
from ..events import EventType, get_global_bus

if TYPE_CHECKING:
    from ..repl.session import REPLSession


@dataclass
class OrchestratorResult:
    """Resultado da execução do pipeline."""
    task: str = ""
    requirements: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    code: dict[str, str] = field(default_factory=dict)
    validation_passed: bool = False
    error: Optional[str] = None
    elapsed_seconds: float = 0.0
    decisions_made: int = 0


@dataclass
class OrchestratorStatus:
    """Status atual do orquestrador para display."""
    state: str
    state_name: str
    task: str
    phase_detail: str
    progress_percent: float
    elapsed_seconds: float
    requirements_count: int
    functions_count: int
    code_count: int
    is_running: bool
    is_paused: bool
    can_resume: bool


class MDAPOrchestrator:
    """
    Coordenador central do MDAP.

    Integra o REPL com o pipeline de geração de código,
    gerenciando estados, interrupções e explicações.

    Modo híbrido:
    - Executa automaticamente por padrão
    - Aceita interrupções (Ctrl+C, /pause)
    - Pode explicar o que está fazendo (/explain)
    """

    def __init__(self, session: "REPLSession"):
        """
        Args:
            session: Sessão REPL para acesso ao cliente LLM e console
        """
        self.session = session
        self.state = OrchestratorState()
        self.result = OrchestratorResult()
        self._event_bus = get_global_bus()

        # Componentes (serão inicializados depois)
        self._executor = None  # PipelineExecutor
        self._tracker = None   # DecisionTracker
        self._resources = None # ResourceManager
        self._meta = None      # MetaIntelligence
        self._interrupts = None # InterruptHandler

    # === API Principal ===

    async def start_task(self, task: str) -> OrchestratorResult:
        """
        Inicia execução do pipeline para uma tarefa.

        Args:
            task: Descrição da tarefa

        Returns:
            Resultado da execução
        """
        if self.state.is_running():
            raise RuntimeError("Pipeline já está em execução. Use /pause ou /cancel primeiro.")

        # Inicializa estado
        self.state.reset()
        self.state.task = task
        self.result = OrchestratorResult(task=task)

        # Emite evento de início
        self._emit_state_change("Iniciando pipeline")

        try:
            # Fase 1: EXPAND
            if not await self._execute_expand():
                return self.result

            # Fase 2: DECOMPOSE
            if not await self._execute_decompose():
                return self.result

            # Fase 3: GENERATE
            if not await self._execute_generate():
                return self.result

            # Fase 4: VALIDATE (opcional)
            await self._execute_validate()

            # Sucesso
            self.state.transition(PipelineState.COMPLETED, "Pipeline concluído")
            self._emit_state_change("Pipeline concluído com sucesso")

        except Exception as e:
            self.state.error_message = str(e)
            self.state.transition(PipelineState.ERROR, f"Erro: {e}")
            self.result.error = str(e)
            self._emit_state_change(f"Erro: {e}")

        self.result.elapsed_seconds = self.state.get_elapsed_seconds()
        return self.result

    async def pause(self) -> bool:
        """
        Pausa a execução no próximo ponto seguro.

        Returns:
            True se pausou, False se não era possível
        """
        if not self.state.is_pausable():
            return False

        self.state.transition(PipelineState.PAUSED, "Pausado pelo usuário")
        self._emit_state_change("Pipeline pausado")
        self._emit_event(EventType.ORCHESTRATOR_INTERRUPT, action="pause")
        return True

    async def resume(self) -> bool:
        """
        Retoma execução após pause.

        Returns:
            True se retomou, False se não estava pausado
        """
        resume_state = self.state.get_resume_state()
        if resume_state is None:
            return False

        self.state.transition(resume_state, "Retomando execução")
        self._emit_state_change(f"Retomando para {resume_state.value}")
        return True

    async def cancel(self) -> bool:
        """
        Cancela execução e volta ao IDLE.

        Returns:
            True se cancelou, False se já estava idle
        """
        if self.state.current == PipelineState.IDLE:
            return False

        self.state.transition(PipelineState.IDLE, "Cancelado pelo usuário")
        self._emit_state_change("Pipeline cancelado")
        return True

    # === API de Consulta ===

    def get_status(self) -> OrchestratorStatus:
        """Retorna status atual para display."""
        total_steps = 4  # expand, decompose, generate, validate
        completed_steps = 0

        if self.result.requirements:
            completed_steps += 1
        if self.result.functions:
            completed_steps += 1
        if self.result.code:
            completed_steps += 1
        if self.result.validation_passed:
            completed_steps += 1

        progress = (completed_steps / total_steps) * 100 if total_steps > 0 else 0

        return OrchestratorStatus(
            state=self.state.current.value,
            state_name=self.state.get_phase_name(),
            task=self.state.task,
            phase_detail=self.state.current_phase_detail,
            progress_percent=progress,
            elapsed_seconds=self.state.get_elapsed_seconds(),
            requirements_count=len(self.result.requirements),
            functions_count=len(self.result.functions),
            code_count=len(self.result.code),
            is_running=self.state.is_running(),
            is_paused=self.state.current == PipelineState.PAUSED,
            can_resume=self.state.get_resume_state() is not None,
        )

    def explain_current(self) -> str:
        """Explica o que o orquestrador está fazendo agora."""
        state = self.state.current

        explanations = {
            PipelineState.IDLE: "Aguardando uma tarefa. Use /run <descrição> para iniciar.",
            PipelineState.EXPANDING: self._explain_expanding(),
            PipelineState.DECOMPOSING: self._explain_decomposing(),
            PipelineState.GENERATING: self._explain_generating(),
            PipelineState.VALIDATING: self._explain_validating(),
            PipelineState.PAUSED: self._explain_paused(),
            PipelineState.AWAITING_DECISION: "Aguardando sua decisão em um checkpoint.",
            PipelineState.COMPLETED: f"Pipeline concluído! Gerados {len(self.result.requirements)} requisitos, {len(self.result.functions)} funções, {len(self.result.code)} implementações.",
            PipelineState.ERROR: f"Erro durante execução: {self.state.error_message}",
        }

        return explanations.get(state, f"Estado: {state.value}")

    # === Execução de Fases ===

    async def _execute_expand(self) -> bool:
        """Executa fase EXPAND."""
        self.state.transition(PipelineState.EXPANDING, "Iniciando expansão de requisitos")
        self._emit_state_change("Expandindo requisitos")

        try:
            # Se já tem requisitos coletados (de handle_expand anterior), usa eles
            if self.session.last_requirements:
                requirements = self.session.last_requirements
                self.session.last_requirements = []  # Limpa para próxima execução
            else:
                # Se não tem, faz perguntas
                questions = await self.session.questioner.generate_questions(self.state.task)

                if questions:
                    self.state.current_phase_detail = f"Geradas {len(questions)} perguntas"
                    result = await self.session._ask_questions(self.state.task, questions)
                    requirements = await self.session._expand_with_context(self.state.task, result)
                else:
                    # Fallback: expansão direta
                    prompt = f"Liste requisitos atômicos para: {self.state.task}"
                    response = await self.session.client.generate(prompt)
                    requirements = self.session._parse_requirements(response)

            self.result.requirements = requirements
            self.state.current_phase_detail = f"{len(requirements)} requisitos"
            self._emit_progress(25, f"Requisitos: {len(requirements)}")

            return not self._should_stop()

        except Exception as e:
            self.result.error = f"Erro em EXPAND: {e}"
            return False

    async def _execute_decompose(self) -> bool:
        """Executa fase DECOMPOSE."""
        if self._should_stop():
            return False

        self.state.transition(PipelineState.DECOMPOSING, "Decompondo em funções")
        self._emit_state_change("Decompondo funções")

        try:
            import re

            # PRIMEIRO: Extrai funções diretamente dos requisitos que já têm assinaturas
            functions = []
            for req in self.result.requirements:
                # Detecta padrões como "Criar função nome(args)" ou "função nome()"
                match = re.search(r'função\s+([a-z_][a-z0-9_]*\s*\([^)]*\))', req, re.IGNORECASE)
                if match:
                    func_sig = match.group(1).strip()
                    # Converte para assinatura Python
                    functions.append(f"def {func_sig}:")

            # Se encontrou funções nos requisitos, usa elas
            if functions:
                self.result.functions = functions[:15]
                self.state.current_phase_detail = f"{len(self.result.functions)} funções"
                self._emit_progress(50, f"Funções: {len(self.result.functions)}")
                return not self._should_stop()

            # SEGUNDO: Se não encontrou, pede ao LLM
            reqs_text = "\n".join([f"- {r}" for r in self.result.requirements[:10]])
            prompt = f"""TAREFA: Crie assinaturas de funções Python para estes requisitos.

REQUISITOS:
{reqs_text}

RESPONDA APENAS com assinaturas Python (uma por linha):
def nome_funcao(param1, param2):
def outra_funcao(param):"""

            response = await self.session.client.generate(prompt)

            # Parse funções da resposta
            for line in response.split('\n'):
                match = re.search(r'(def\s+[a-z_][a-z0-9_]*\s*\([^)]*\):?)', line, re.IGNORECASE)
                if match:
                    func = match.group(1).strip()
                    if not func.endswith(':'):
                        func += ':'
                    functions.append(func)

            # Se ainda não tem funções, gera fallback básico
            if not functions:
                functions = [
                    "def criar(dados: dict):",
                    "def listar():",
                    "def buscar(id: int):",
                    "def atualizar(id: int, dados: dict):",
                    "def remover(id: int):",
                ]

            self.result.functions = functions[:15]
            self.state.current_phase_detail = f"{len(self.result.functions)} funções"
            self._emit_progress(50, f"Funções: {len(self.result.functions)}")

            return not self._should_stop()

        except Exception as e:
            self.result.error = f"Erro em DECOMPOSE: {e}"
            return False

    async def _execute_generate(self) -> bool:
        """Executa fase GENERATE."""
        if self._should_stop():
            return False

        self.state.transition(PipelineState.GENERATING, "Gerando código")
        self._emit_state_change("Gerando implementações")

        try:
            code = {}
            total = len(self.result.functions)

            for i, func in enumerate(self.result.functions, 1):
                if self._should_stop():
                    break

                self.state.current_phase_detail = f"Função {i}/{total}: {func[:30]}..."
                self._emit_progress(50 + (i / total) * 40, f"Gerando {i}/{total}")

                prompt = f"""Implemente esta função Python:
{func}

Contexto: {self.state.task}

Retorne APENAS o código Python, sem explicações."""

                response = await self.session.client.generate(prompt)
                code[func] = response

            self.result.code = code
            self.state.current_phase_detail = f"{len(code)} implementações"

            return not self._should_stop()

        except Exception as e:
            self.result.error = f"Erro em GENERATE: {e}"
            return False

    async def _execute_validate(self) -> bool:
        """Executa fase VALIDATE."""
        if self._should_stop():
            return False

        self.state.transition(PipelineState.VALIDATING, "Validando código")
        self._emit_state_change("Validando implementações")

        try:
            # Validação básica: verifica sintaxe
            all_valid = True
            for func, code in self.result.code.items():
                try:
                    compile(code, '<string>', 'exec')
                except SyntaxError:
                    all_valid = False
                    self.state.current_phase_detail = f"Erro de sintaxe em {func[:30]}"
                    break

            self.result.validation_passed = all_valid
            self._emit_progress(100, "Validação concluída")

            return True

        except Exception as e:
            self.result.error = f"Erro em VALIDATE: {e}"
            return False

    # === Helpers ===

    def _should_stop(self) -> bool:
        """Verifica se deve parar execução."""
        return self.state.current in {
            PipelineState.PAUSED,
            PipelineState.IDLE,
            PipelineState.ERROR,
        }

    def _emit_state_change(self, reason: str) -> None:
        """Emite evento de mudança de estado."""
        self._emit_event(
            EventType.ORCHESTRATOR_STATE_CHANGE,
            state=self.state.current.value,
            state_name=self.state.get_phase_name(),
            reason=reason,
            task=self.state.task,
        )

    def _emit_progress(self, percent: float, detail: str) -> None:
        """Emite evento de progresso."""
        self._emit_event(
            EventType.ORCHESTRATOR_PROGRESS,
            percent=percent,
            detail=detail,
            phase=self.state.current.value,
        )

    def _emit_event(self, event_type: EventType, **data) -> None:
        """Emite evento no bus global."""
        self._event_bus.emit_simple(event_type, **data)

    # === Explicações ===

    def _explain_expanding(self) -> str:
        return f"""Estou na fase EXPAND, gerando requisitos atômicos.

Tarefa: {self.state.task}
Detalhe: {self.state.current_phase_detail}

Nesta fase, analiso a tarefa e extraio cada requisito individual
que precisa ser implementado. Cada requisito deve ser testável
e independente."""

    def _explain_decomposing(self) -> str:
        return f"""Estou na fase DECOMPOSE, planejando as funções.

Requisitos encontrados: {len(self.result.requirements)}
Detalhe: {self.state.current_phase_detail}

Nesta fase, organizo os requisitos em funções Python
que serão implementadas. Cada função tem uma responsabilidade clara."""

    def _explain_generating(self) -> str:
        return f"""Estou na fase GENERATE, implementando código.

Funções planejadas: {len(self.result.functions)}
Já implementadas: {len(self.result.code)}
Detalhe: {self.state.current_phase_detail}

Nesta fase, implemento cada função uma por uma."""

    def _explain_validating(self) -> str:
        return f"""Estou na fase VALIDATE, verificando o código.

Implementações: {len(self.result.code)}
Detalhe: {self.state.current_phase_detail}

Nesta fase, verifico sintaxe e correção do código gerado."""

    def _explain_paused(self) -> str:
        resume_state = self.state.get_resume_state()
        return f"""Pipeline PAUSADO.

Estava em: {resume_state.value if resume_state else 'desconhecido'}
Tarefa: {self.state.task}
Progresso: {len(self.result.requirements)} requisitos, {len(self.result.functions)} funções, {len(self.result.code)} implementações

Opções:
  /resume  - Continuar de onde parou
  /cancel  - Cancelar e começar de novo
  /status  - Ver detalhes do progresso
  /explain - Ver mais detalhes sobre o estado atual"""
