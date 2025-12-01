"""
Requirement Collector - Sistema de coleta de requisitos em múltiplas rodadas

Faz perguntas em diferentes categorias até ter informações suficientes.
Usa um agente verificador para decidir se precisa de mais perguntas.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
import json
import re


class QuestionCategory(Enum):
    """Categorias de perguntas em ordem de prioridade."""
    NEGOCIO = "NEGOCIO"           # Regras de negócio, fluxos, entidades
    TECNOLOGIA = "TECNOLOGIA"     # Stack, linguagem, frameworks
    UI_UX = "UI_UX"               # Interface, experiência do usuário
    ARQUITETURA = "ARQUITETURA"   # Frontend, backend, banco de dados
    INFRAESTRUTURA = "INFRA"      # Deploy, hosting, escalabilidade
    INTEGRACAO = "INTEGRACAO"     # APIs externas, serviços terceiros
    SEGURANCA = "SEGURANCA"       # Autenticação, autorização, dados sensíveis


@dataclass
class CollectedAnswer:
    """Uma resposta coletada."""
    category: str
    question: str
    answer: str


@dataclass
class CollectionState:
    """Estado da coleta de requisitos."""
    task: str
    answers: List[CollectedAnswer] = field(default_factory=list)
    completed_categories: List[str] = field(default_factory=list)
    is_complete: bool = False

    def to_context(self) -> str:
        """Converte respostas em contexto para o LLM."""
        if not self.answers:
            return ""

        lines = ["Informações coletadas:"]
        current_cat = ""
        for a in self.answers:
            if a.category != current_cat:
                current_cat = a.category
                lines.append(f"\n## {a.category}")
            lines.append(f"- {a.question}: {a.answer}")

        return "\n".join(lines)


class RequirementCollector:
    """
    Coleta requisitos em múltiplas rodadas de perguntas.

    Fluxo:
    1. Faz perguntas de NEGÓCIO
    2. Verifica se precisa de mais perguntas
    3. Se sim, faz perguntas de TECNOLOGIA, UI/UX, etc.
    4. Repete até ter informações suficientes
    """

    def __init__(self, client, console):
        """
        Args:
            client: Cliente Claude CLI
            console: Console Rich para output
        """
        self.client = client
        self.console = console
        self.state = None

    async def collect(self, task: str) -> CollectionState:
        """
        Coleta requisitos para uma tarefa.

        Args:
            task: Descrição da tarefa

        Returns:
            Estado da coleta com todas as respostas
        """
        self.state = CollectionState(task=task)

        # Define ordem das categorias
        categories = [
            QuestionCategory.NEGOCIO,
            QuestionCategory.TECNOLOGIA,
            QuestionCategory.UI_UX,
            QuestionCategory.ARQUITETURA,
            QuestionCategory.SEGURANCA,
        ]

        for category in categories:
            # Verifica se já tem informações suficientes
            if await self._should_stop_collecting():
                break

            # Gera e faz perguntas desta categoria
            await self._collect_category(category)
            self.state.completed_categories.append(category.value)

        self.state.is_complete = True
        return self.state

    async def _collect_category(self, category: QuestionCategory) -> None:
        """Coleta respostas para uma categoria específica."""
        from .ui import show_info

        show_info(self.console, f"Analisando {category.value.lower()}...")

        # Gera perguntas para esta categoria
        questions = await self._generate_questions_for_category(category)

        if not questions:
            return

        # Mostra header da categoria
        self.console.print(f"\n[bold cyan]═══ {category.value} ═══[/bold cyan]")
        self.console.print(f"[dim]{len(questions)} perguntas sobre {category.value.lower()}[/dim]\n")

        # Faz cada pergunta
        from rich.prompt import Prompt

        for i, q in enumerate(questions, 1):
            self.console.print(f"[cyan][{i}/{len(questions)}][/cyan] [bold]{q['question']}[/bold]")
            if q.get('why'):
                self.console.print(f"   [dim]({q['why']})[/dim]")

            # Mostra opções
            if q.get('options'):
                self.console.print()
                for opt in q['options']:
                    self.console.print(f"   [cyan]{opt['key']})[/cyan] {opt['label']}")
                self.console.print(f"   [dim]/skip para pular[/dim]")

            # Coleta resposta
            answer = Prompt.ask("   [cyan]>[/cyan]")

            if answer.lower() in ["/skip", "/s", ""]:
                self.console.print("   [dim]Pulada[/dim]")
                continue

            # Processa resposta
            if q.get('options'):
                # Verifica se é uma opção
                for opt in q['options']:
                    if opt['key'].lower() == answer.lower():
                        answer = opt['value']
                        self.console.print(f"   [green]Selecionado: {opt['label']}[/green]")
                        break
                else:
                    self.console.print(f"   [green]Resposta: {answer}[/green]")
            else:
                self.console.print(f"   [green]Resposta: {answer}[/green]")

            # Salva resposta
            self.state.answers.append(CollectedAnswer(
                category=category.value,
                question=q['question'],
                answer=answer
            ))

            self.console.print()

    async def _generate_questions_for_category(self, category: QuestionCategory) -> List[Dict]:
        """Gera perguntas específicas para uma categoria."""

        prompts = {
            QuestionCategory.NEGOCIO: self._prompt_negocio(),
            QuestionCategory.TECNOLOGIA: self._prompt_tecnologia(),
            QuestionCategory.UI_UX: self._prompt_ui_ux(),
            QuestionCategory.ARQUITETURA: self._prompt_arquitetura(),
            QuestionCategory.SEGURANCA: self._prompt_seguranca(),
        }

        prompt = prompts.get(category, self._prompt_negocio())
        prompt = prompt.format(
            task=self.state.task,
            context=self.state.to_context()
        )

        response = await self.client.generate(prompt)
        return self._parse_questions(response)

    async def _should_stop_collecting(self) -> bool:
        """Verifica se já tem informações suficientes."""

        # Precisa de pelo menos uma rodada de negócio
        if not self.state.answers:
            return False

        # Verifica com o LLM se precisa de mais perguntas
        prompt = f"""Analise as informações coletadas e decida se precisa de mais perguntas.

Projeto: {self.state.task}

{self.state.to_context()}

Categorias já coletadas: {', '.join(self.state.completed_categories)}
Categorias pendentes: TECNOLOGIA, UI_UX, ARQUITETURA, SEGURANCA

Responda APENAS com JSON:
```json
{{"should_continue": true, "reason": "motivo para continuar ou parar"}}
```"""

        response = await self.client.generate(prompt)

        try:
            # Extrai JSON
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
                should_continue = data.get('should_continue', True)
                reason = data.get('reason', '')

                if not should_continue:
                    self.console.print(f"[dim]Verificador: {reason}[/dim]")
                    return True
        except:
            pass

        return False

    def _parse_questions(self, response: str) -> List[Dict]:
        """Parse resposta JSON em lista de perguntas."""
        try:
            # Remove markdown
            clean = re.sub(r'^```(?:json)?\s*', '', response.strip())
            clean = re.sub(r'\s*```$', '', clean)

            json_match = re.search(r'\[[\s\S]*\]', clean)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass
        return []

    # === Prompts por Categoria ===

    def _prompt_negocio(self) -> str:
        return """Gere perguntas sobre REGRAS DE NEGÓCIO para este projeto:

Projeto: {task}

{context}

Foque em: fluxos principais, entidades, regras específicas do domínio.

Retorne 5 perguntas neste formato JSON:
```json
[{{"question": "Pergunta?", "why": "Motivo", "options": [{{"key": "a", "label": "Opção 1", "value": "valor1"}}, {{"key": "b", "label": "Opção 2", "value": "valor2"}}]}}]
```"""

    def _prompt_tecnologia(self) -> str:
        return """Gere perguntas sobre TECNOLOGIA para este projeto:

Projeto: {task}

{context}

Foque em: linguagem, framework frontend, framework backend, banco de dados.

Retorne 4 perguntas neste formato JSON:
```json
[{{"question": "Pergunta?", "why": "Motivo", "options": [{{"key": "a", "label": "Opção 1", "value": "valor1"}}, {{"key": "b", "label": "Opção 2", "value": "valor2"}}]}}]
```"""

    def _prompt_ui_ux(self) -> str:
        return """Gere perguntas sobre UI/UX para este projeto:

Projeto: {task}

{context}

Foque em: tipo de interface (web/mobile/desktop), estilo visual, responsividade.

Retorne 3 perguntas neste formato JSON:
```json
[{{"question": "Pergunta?", "why": "Motivo", "options": [{{"key": "a", "label": "Opção 1", "value": "valor1"}}, {{"key": "b", "label": "Opção 2", "value": "valor2"}}]}}]
```"""

    def _prompt_arquitetura(self) -> str:
        return """Gere perguntas sobre ARQUITETURA para este projeto:

Projeto: {task}

{context}

Foque em: separação frontend/backend, API REST/GraphQL, estrutura de pastas.

Retorne 3 perguntas neste formato JSON:
```json
[{{"question": "Pergunta?", "why": "Motivo", "options": [{{"key": "a", "label": "Opção 1", "value": "valor1"}}, {{"key": "b", "label": "Opção 2", "value": "valor2"}}]}}]
```"""

    def _prompt_seguranca(self) -> str:
        return """Gere perguntas sobre SEGURANÇA para este projeto:

Projeto: {task}

{context}

Foque em: autenticação, autorização, dados sensíveis, LGPD.

Retorne 3 perguntas neste formato JSON:
```json
[{{"question": "Pergunta?", "why": "Motivo", "options": [{{"key": "a", "label": "Opção 1", "value": "valor1"}}, {{"key": "b", "label": "Opção 2", "value": "valor2"}}]}}]
```"""
