"""
REPL Session - Gerencia sessao interativa

Loop principal e estado da conversa.
"""
import asyncio
import subprocess
import platform
import tempfile
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime

from rich.console import Console
from rich.prompt import Prompt

from .commands import CommandRouter
from .questioner import TaskQuestioner, Question, QuestionnaireResult
from .requirement_collector import RequirementCollector
from ..orchestrator import OrchestratorAdapter
from ..orchestrator.intent import IntentDetector, UserIntent
from .ui import (
    show_welcome,
    show_user_message,
    show_assistant_message,
    show_error,
    show_info,
    show_question_header,
    show_question,
    show_question_skipped,
    show_questionnaire_summary,
    show_requirements,
    show_expanding,
)


@dataclass
class Message:
    """Uma mensagem na conversa."""
    role: str  # "user" ou "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)


class ClaudeCLI:
    """Cliente simples para Claude CLI."""

    def __init__(self):
        self._call_count = 0
        self._claude_cmd = self._find_claude_cmd()

    def _find_claude_cmd(self) -> str:
        """Encontra o caminho do claude CLI."""
        if platform.system() == "Windows":
            # Tenta locais comuns no Windows
            npm_path = Path.home() / "AppData" / "Roaming" / "npm" / "claude.cmd"
            if npm_path.exists():
                return str(npm_path)
        return "claude"

    async def generate(self, prompt: str) -> str:
        """Gera resposta usando claude --print via stdin."""
        self._call_count += 1

        # Comando para Windows ou Unix - usa stdin para passar o prompt
        if platform.system() == "Windows":
            cmd = [self._claude_cmd, "--print", "-"]
        else:
            cmd = ["claude", "--print", "-"]

        # Usa diretorio temp para evitar ler CLAUDE.md do projeto
        temp_dir = tempfile.gettempdir()

        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=temp_dir,
            )

            # Envia prompt via stdin
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=prompt.encode("utf-8")),
                timeout=120,  # 2 minutos
            )

            if process.returncode == 0:
                # Try UTF-8 first, fallback to cp1252 (Windows) with replace for errors
                try:
                    return stdout.decode("utf-8").strip()
                except UnicodeDecodeError:
                    return stdout.decode("cp1252", errors="replace").strip()
            else:
                try:
                    error = stderr.decode("utf-8").strip()
                except UnicodeDecodeError:
                    error = stderr.decode("cp1252", errors="replace").strip()
                raise RuntimeError(f"Claude CLI error: {error}")

        except asyncio.TimeoutError:
            if process:
                process.kill()
            raise RuntimeError("Claude CLI timeout (2 minutes)")

    @property
    def call_count(self) -> int:
        return self._call_count


class REPLSession:
    """
    Sessao interativa do MDAP Agent.

    Gerencia:
    - Loop de input/output
    - Historico de conversa
    - Comunicacao com Claude CLI
    - Comandos slash
    """

    def __init__(self, working_dir: str = "."):
        self.working_dir = Path(working_dir).resolve()
        self.console = Console()
        self.client = ClaudeCLI()
        self.commands = CommandRouter(self)
        self.questioner = TaskQuestioner(self.client)
        self.collector = RequirementCollector(self.client, self.console)  # Coleta completa
        self.history: list[Message] = []
        self.running = True
        self.start_time = datetime.now()
        self.last_requirements: list[str] = []  # Últimos requisitos gerados
        self.last_collection = None  # Última coleta completa
        self.orch = OrchestratorAdapter(self)  # Orchestrator
        self.intent_detector = IntentDetector(self)  # Detecção de intenção
        self.smart_mode = True  # Modo inteligente (detecta intenção)
        self.deep_collect = True  # Modo de coleta profunda (múltiplas rodadas)

    async def run(self) -> None:
        """Loop principal do REPL."""
        show_welcome(self.console, self.working_dir)

        while self.running:
            try:
                # Prompt de input
                user_input = Prompt.ask("[bold cyan]>[/bold cyan]")

                if not user_input.strip():
                    continue

                # Tenta processar como comando
                if user_input.startswith("/"):
                    await self.commands.route(user_input)
                else:
                    # Chat normal
                    await self._handle_chat(user_input)

            except KeyboardInterrupt:
                self.console.print("\n[dim]Use /exit to quit, or Ctrl+C again to force exit[/dim]")
                try:
                    await asyncio.sleep(0.5)
                except KeyboardInterrupt:
                    self.console.print("\n[dim]Goodbye![/dim]")
                    break

            except EOFError:
                self.console.print("\n[dim]Goodbye![/dim]")
                break

            except Exception as e:
                show_error(self.console, str(e))

    async def _handle_chat(self, message: str) -> None:
        """Processa mensagem de chat com detecção inteligente de intenção."""
        # Não mostra mensagem do usuario - já foi mostrada pelo Prompt.ask()
        show_user_message(self.console, message)

        # Adiciona ao historico
        self.history.append(Message(role="user", content=message))

        # Se modo inteligente está ativo, detecta intenção
        if self.smart_mode:
            show_info(self.console, "Analisando intenção...")
            intent_result = await self.intent_detector.detect(message)

            # Mostra a intenção detectada
            self.console.print(f"[dim]→ Intenção: {intent_result.intent.value} ({intent_result.confidence:.0%})[/dim]")

            handled = await self._handle_intent(intent_result, message)
            if handled:
                return

        # Fallback para chat normal
        show_info(self.console, "Pensando...")

        try:
            # Constroi prompt com contexto
            prompt = self._build_prompt(message)

            # Chama Claude CLI
            response = await self.client.generate(prompt)

            # Adiciona resposta ao historico
            self.history.append(Message(role="assistant", content=response))

            # Mostra resposta
            show_assistant_message(self.console, response)

        except Exception as e:
            show_error(self.console, f"Failed to get response: {e}")

    async def _handle_intent(self, intent_result, original_message: str) -> bool:
        """
        Trata intenção detectada.

        Returns:
            True se a intenção foi tratada, False para continuar com chat normal
        """
        intent = intent_result.intent
        task = intent_result.task or original_message

        # Tarefas
        if intent == UserIntent.TASK_COMPLEX:
            show_info(self.console, f"Detectei uma tarefa complexa. Vou fazer algumas perguntas primeiro...")
            await self.handle_expand(task)
            # Após expandir, oferece executar
            confirm = Prompt.ask("[cyan]Deseja executar o pipeline completo?[/cyan] [dim](s/n)[/dim]")
            if confirm.lower() in ["s", "sim", "yes", "y"]:
                await self.orch.run(task)
            return True

        elif intent == UserIntent.TASK_SIMPLE:
            show_info(self.console, f"Detectei uma tarefa. Iniciando pipeline...")
            await self.orch.run(task)
            return True

        elif intent == UserIntent.TASK_EXPLORE:
            show_info(self.console, f"Vou explorar os requisitos dessa tarefa...")
            await self.handle_expand(task)
            return True

        # Meta
        elif intent == UserIntent.META_STATUS:
            self.orch.status()
            return True

        elif intent == UserIntent.META_EXPLAIN:
            self.orch.explain()
            return True

        elif intent == UserIntent.META_HELP:
            self._show_greeting_response()  # Mostra capacidades
            return True

        # Controle
        elif intent == UserIntent.CONTROL_PAUSE:
            await self.orch.pause()
            return True

        elif intent == UserIntent.CONTROL_RESUME:
            await self.orch.resume()
            return True

        elif intent == UserIntent.CONTROL_CANCEL:
            await self.orch.cancel()
            return True

        # Chat
        elif intent == UserIntent.CHAT_GREETING:
            self._show_greeting_response()
            return True

        # Chat geral e perguntas técnicas - continua para o LLM responder
        return False

    def _show_greeting_response(self) -> None:
        """Mostra resposta de saudação com capacidades."""
        from rich.panel import Panel
        from rich import box

        content = """Olá! Sou o MDAP Orchestrator.

Posso ajudar você a:
  • Criar código - Diga o que quer criar e eu implemento
  • Explorar requisitos - Analisar e detalhar o que precisa ser feito
  • Responder perguntas - Sobre programação ou sobre meu funcionamento

Exemplos:
  "crie um validador de CPF"
  "quero um sistema de autenticação completo"
  "quais requisitos preciso para uma API de pagamentos?"
  "como funciona async/await em Python?"

Basta conversar comigo normalmente!"""

        self.console.print(Panel(
            content,
            title="MDAP Orchestrator",
            border_style="cyan",
            box=box.ROUNDED,
        ))

    def _build_prompt(self, message: str) -> str:
        """Constroi prompt com contexto da conversa."""
        lines = []

        # System context - MDAP Orchestrator identity
        lines.append("""Você é o MDAP Orchestrator, um sistema inteligente de geração de código baseado no paper "Solving a Million-Step LLM Task with Zero Errors".

Suas capacidades:
- Criar código: Você implementa código usando votação MDAP (múltiplos candidatos votados)
- Explorar requisitos: Você analisa tarefas e extrai requisitos atômicos
- Responder perguntas: Sobre programação ou sobre seu funcionamento

Comandos disponíveis:
- O usuário pode usar comandos como /run, /expand, /status, /pause, /resume, /cancel
- Ou simplesmente conversar naturalmente que você entende a intenção

Se o usuário pedir para CRIAR algo (código, função, sistema, etc), responda que você vai iniciar o pipeline de geração.
Se o usuário perguntar O QUE VOCÊ FAZ ou suas CAPACIDADES, explique que você é o MDAP Orchestrator e liste suas capacidades.

Responda em português de forma concisa e direta.""")
        lines.append(f"Diretório de trabalho: {self.working_dir}")
        lines.append("")

        # Historico recente (ultimas 10 mensagens)
        recent_history = self.history[-10:]
        if recent_history:
            lines.append("Conversa recente:")
            for msg in recent_history:
                role = "Usuário" if msg.role == "user" else "MDAP"
                content = msg.content[:500]
                if len(msg.content) > 500:
                    content += "..."
                lines.append(f"{role}: {content}")
            lines.append("")

        # Mensagem atual
        lines.append(f"Usuário: {message}")
        lines.append("")
        lines.append("Responda de forma útil. Se mostrar código, use blocos markdown com a linguagem especificada.")

        return "\n".join(lines)

    def get_stats(self) -> dict:
        """Retorna estatisticas da sessao."""
        elapsed = datetime.now() - self.start_time
        return {
            "messages": len(self.history),
            "user_messages": sum(1 for m in self.history if m.role == "user"),
            "assistant_messages": sum(1 for m in self.history if m.role == "assistant"),
            "elapsed_seconds": elapsed.total_seconds(),
            "cli_calls": self.client.call_count,
        }

    async def handle_expand(self, task: str) -> None:
        """
        Expande tarefa em requisitos com questionário.

        Args:
            task: Descrição da tarefa
        """
        try:
            # Modo de coleta profunda - múltiplas rodadas de perguntas
            if self.deep_collect:
                show_info(self.console, "Iniciando coleta completa de requisitos...")
                self.console.print("[dim]Vou fazer perguntas sobre: Negócio → Tecnologia → UI/UX → Arquitetura → Segurança[/dim]\n")

                # Usa o collector para coleta em múltiplas rodadas
                collection = await self.collector.collect(task)
                self.last_collection = collection

                # Gera requisitos baseados na coleta completa
                show_info(self.console, "Gerando requisitos baseados nas respostas...")
                requirements = await self._expand_from_collection(task, collection)

            else:
                # Modo simples - uma rodada de perguntas
                show_info(self.console, "Gerando perguntas...")
                questions = await self.questioner.generate_questions(task)

                if not questions:
                    show_error(self.console, "Não consegui gerar perguntas para esta tarefa.")
                    return

                show_question_header(self.console, task, len(questions))
                result = await self._ask_questions(task, questions)

                # Mostra resumo
                show_questionnaire_summary(
                    self.console,
                    answered=len(result.answered_questions),
                    skipped=len(result.skipped_questions),
                    total=len(result.questions)
                )

                # Expande requisitos com contexto
                show_expanding(self.console)
                requirements = await self._expand_with_context(task, result)

            # Mostra requisitos
            show_requirements(self.console, requirements)

            # Salva para uso posterior
            self.last_requirements = requirements

        except Exception as e:
            show_error(self.console, f"Erro na expansão: {e}")

    async def _ask_questions(
        self,
        task: str,
        questions: list[Question]
    ) -> QuestionnaireResult:
        """
        Faz perguntas ao usuário com opções.

        Args:
            task: Tarefa
            questions: Lista de perguntas

        Returns:
            Resultado do questionário
        """
        result = self.questioner.create_result(task, questions)
        skip_all = False

        for i, question in enumerate(questions, 1):
            if skip_all:
                question.skipped = True
                continue

            show_question(self.console, question, i, len(questions))

            # Pega resposta
            answer = Prompt.ask("   [cyan]>[/cyan]")
            answer_lower = answer.lower().strip()

            # Comandos especiais
            if answer_lower in ["/skip", "/s", ""]:
                question.skipped = True
                show_question_skipped(self.console)
            elif answer_lower in ["/skipall", "/sa"]:
                question.skipped = True
                skip_all = True
                show_question_skipped(self.console)
                self.console.print("   [dim]Pulando todas as perguntas restantes...[/dim]")
            elif question.options:
                # Tenta encontrar opção selecionada
                option = question.get_option_by_key(answer_lower)
                if option:
                    if option.key == "custom":
                        # Pede input customizado
                        custom = Prompt.ask("   [yellow]Digite sua resposta[/yellow]")
                        if custom.strip():
                            question.answer = custom.strip()
                            question.selected_option = "custom"
                            self.console.print(f"   [green]Resposta: {custom.strip()}[/green]")
                        else:
                            question.skipped = True
                            show_question_skipped(self.console)
                    else:
                        question.answer = option.value
                        question.selected_option = option.key
                        self.console.print(f"   [green]Selecionado: {option.label}[/green]")
                else:
                    # Se não é uma opção válida, usa como resposta customizada
                    question.answer = answer.strip()
                    question.selected_option = "custom"
                    self.console.print(f"   [green]Resposta: {answer.strip()}[/green]")
            elif answer.strip():
                question.answer = answer.strip()
                self.console.print(f"   [green]Resposta: {answer.strip()}[/green]")

        return result

    async def _expand_with_context(
        self,
        task: str,
        questionnaire: QuestionnaireResult
    ) -> list[str]:
        """
        Expande requisitos usando contexto do questionário.

        Args:
            task: Tarefa
            questionnaire: Resultado do questionário

        Returns:
            Lista de requisitos
        """
        # Constrói contexto
        context = questionnaire.to_context()

        prompt = f"""Preciso que você liste os requisitos funcionais para este projeto de software:

"{task}"

{context}

Liste cada requisito como uma funcionalidade específica (modelos de dados, funções, regras de negócio).

Retorne os requisitos neste formato JSON:
```json
["Criar modelo Jogo com campos id, titulo, preco_diaria", "Criar função cadastrar_jogo(dados)", "Criar função listar_jogos_disponiveis()", "Criar função realizar_locacao(cliente_id, jogo_id, dias)"]
```

Gere apenas o JSON array com os requisitos."""

        response = await self.client.generate(prompt)

        # Debug
        print(f"[DEBUG] Resposta LLM requisitos: {response[:150]}...")

        requirements = self._parse_requirements(response)

        if not requirements:
            print(f"[DEBUG] Falha ao parsear requisitos. Resposta: {response}")

        return requirements

    async def _expand_from_collection(self, task: str, collection) -> list[str]:
        """
        Gera requisitos baseados na coleta completa de múltiplas rodadas.

        Args:
            task: Tarefa
            collection: CollectionState com todas as respostas

        Returns:
            Lista de requisitos
        """
        context = collection.to_context()

        prompt = f"""Com base nas informações coletadas, liste TODOS os requisitos funcionais para este projeto.

Projeto: {task}

{context}

Inclua requisitos para:
1. Modelos de dados (com campos específicos)
2. Funções CRUD (criar, ler, atualizar, deletar)
3. Regras de negócio específicas mencionadas
4. Interface do usuário (telas, componentes)
5. Integrações e APIs
6. Autenticação/segurança se mencionado

Retorne os requisitos neste formato JSON:
```json
["Criar modelo X com campos a, b, c", "Criar função y(params)", "Criar tela de Z", ...]
```

Gere o máximo de requisitos específicos possível baseado nas respostas."""

        response = await self.client.generate(prompt)

        print(f"[DEBUG] Resposta LLM requisitos (coleta completa): {response[:150]}...")

        requirements = self._parse_requirements(response)

        if not requirements:
            print(f"[DEBUG] Falha ao parsear requisitos. Resposta: {response}")

        return requirements

    def _parse_requirements(self, text: str) -> list[str]:
        """Parse resposta em lista de requisitos."""
        import json
        import re

        text = text.strip()

        # Tenta parse JSON
        try:
            json_match = re.search(r'\[[\s\S]*\]', text)
            if json_match:
                data = json.loads(json_match.group())
                if isinstance(data, list):
                    return [str(r).strip() for r in data if r]
        except json.JSONDecodeError:
            pass

        # Fallback: parse linha por linha
        requirements = []
        for line in text.split('\n'):
            line = line.strip()
            line = re.sub(r'^[-*•]\s*', '', line)
            line = re.sub(r'^\d+\.\s*', '', line)
            line = re.sub(r'^"(.+)"[,]?$', r'\1', line)

            if line and len(line) > 5:
                requirements.append(line)

        return requirements

    def _generate_fallback_requirements(self, task: str, questionnaire) -> list[str]:
        """Gera requisitos baseados no contexto quando LLM falha."""
        task_lower = task.lower()

        # Detecta domínio e gera requisitos específicos
        if "locação" in task_lower or "aluguel" in task_lower:
            if "jogo" in task_lower or "game" in task_lower:
                return self._requirements_locacao_jogos(questionnaire)

        # Requisitos genéricos para sistema completo
        return [
            "Definir modelo de dados principal",
            "Criar CRUD (Create, Read, Update, Delete) para entidades principais",
            "Implementar autenticação de usuários",
            "Criar interface de listagem",
            "Criar interface de cadastro/edição",
            "Implementar validação de dados",
            "Criar relatórios básicos",
            "Implementar busca/filtros",
        ]

    def _requirements_locacao_jogos(self, questionnaire) -> list[str]:
        """Requisitos específicos para sistema de locação de jogos."""
        reqs = [
            # Modelos de dados
            "Criar modelo Jogo (id, titulo, plataforma, genero, quantidade_estoque, preco_diaria, capa_url)",
            "Criar modelo Cliente (id, nome, cpf, telefone, email, endereco, data_cadastro)",
            "Criar modelo Locacao (id, cliente_id, jogo_id, data_inicio, data_prevista_devolucao, data_devolucao, valor_total, status)",

            # CRUD Jogos
            "Criar função cadastrar_jogo(dados) -> Jogo",
            "Criar função listar_jogos(filtros?) -> Lista[Jogo]",
            "Criar função buscar_jogo(id) -> Jogo",
            "Criar função atualizar_jogo(id, dados) -> Jogo",
            "Criar função remover_jogo(id) -> bool",

            # CRUD Clientes
            "Criar função cadastrar_cliente(dados) -> Cliente",
            "Criar função listar_clientes(filtros?) -> Lista[Cliente]",
            "Criar função buscar_cliente(id_ou_cpf) -> Cliente",
            "Criar função atualizar_cliente(id, dados) -> Cliente",

            # Locação
            "Criar função realizar_locacao(cliente_id, jogo_id, dias) -> Locacao",
            "Criar função devolver_jogo(locacao_id) -> Locacao",
            "Criar função listar_locacoes_ativas() -> Lista[Locacao]",
            "Criar função verificar_disponibilidade(jogo_id) -> bool",
            "Criar função calcular_valor_locacao(jogo_id, dias) -> float",

            # Relatórios
            "Criar função relatorio_faturamento(periodo) -> dict",
            "Criar função relatorio_jogos_mais_alugados() -> Lista",
            "Criar função relatorio_clientes_inadimplentes() -> Lista",
        ]

        # Adiciona requisitos baseados nas respostas do questionário
        for q in questionnaire.answered_questions:
            if "multa" in q.question.lower() and q.answer and "não" not in q.answer.lower():
                reqs.append("Criar função calcular_multa_atraso(locacao_id) -> float")
                reqs.append("Criar modelo Multa (id, locacao_id, valor, data_geracao, pago)")

            if "reserva" in q.question.lower() and q.answer and "não" not in q.answer.lower():
                reqs.append("Criar função reservar_jogo(cliente_id, jogo_id, data_retirada) -> Reserva")
                reqs.append("Criar modelo Reserva (id, cliente_id, jogo_id, data_reserva, data_retirada, status)")

        return reqs
