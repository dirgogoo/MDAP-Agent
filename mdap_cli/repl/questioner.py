"""
Task Questioner - Gera perguntas inteligentes para expandir requisitos

Analisa a tarefa e gera perguntas relevantes por categoria
para coletar contexto do usuário antes da expansão.

Perguntas possuem opções pré-definidas + opção customizada.
"""
import json
import re
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum


class QuestionCategory(Enum):
    """Categorias de perguntas."""
    ESCOPO = "ESCOPO"
    USUARIOS = "USUARIOS"
    TECNOLOGIA = "TECNOLOGIA"
    SEGURANCA = "SEGURANCA"
    PERFORMANCE = "PERFORMANCE"
    INTEGRACOES = "INTEGRACOES"
    UX = "UX"
    DADOS = "DADOS"
    EDGE_CASES = "EDGE_CASES"
    NEGOCIO = "NEGOCIO"


@dataclass
class QuestionOption:
    """Uma opção de resposta."""
    key: str      # "a", "b", "c", etc ou "custom"
    label: str    # Texto curto da opção
    value: str    # Valor a ser usado como resposta


@dataclass
class Question:
    """Uma pergunta sobre a tarefa com opções."""
    category: str
    question: str
    why: str  # Por que essa pergunta é importante
    options: List[QuestionOption] = field(default_factory=list)
    answer: Optional[str] = None
    selected_option: Optional[str] = None  # Key da opção selecionada
    skipped: bool = False

    def __post_init__(self):
        # Sempre adiciona opção customizada se não existir
        if self.options and not any(o.key == "custom" for o in self.options):
            self.options.append(QuestionOption(
                key="custom",
                label="Outro (digite)",
                value=""
            ))

    def get_option_by_key(self, key: str) -> Optional[QuestionOption]:
        """Retorna opção pela key."""
        for opt in self.options:
            if opt.key.lower() == key.lower():
                return opt
        return None


@dataclass
class QuestionnaireResult:
    """Resultado do questionário."""
    task: str
    questions: list[Question] = field(default_factory=list)

    @property
    def answered_questions(self) -> list[Question]:
        return [q for q in self.questions if q.answer and not q.skipped]

    @property
    def skipped_questions(self) -> list[Question]:
        return [q for q in self.questions if q.skipped]

    def to_context(self) -> str:
        """Converte respostas em contexto para expansão."""
        if not self.answered_questions:
            return ""

        lines = ["Informações coletadas do usuário:"]
        for q in self.answered_questions:
            lines.append(f"- {q.category}: {q.question}")
            lines.append(f"  Resposta: {q.answer}")

        return "\n".join(lines)


QUESTION_GENERATION_PROMPT = """Preciso que você gere perguntas para entender melhor este projeto de software:

"{task}"

Por favor, crie 5 perguntas sobre as REGRAS DE NEGÓCIO (não sobre tecnologia). Cada pergunta deve ter opções de resposta.

Retorne as perguntas neste formato JSON:
```json
[
  {{"category": "NEGOCIO", "question": "Sua pergunta aqui?", "why": "Por que essa pergunta importa", "options": [{{"key": "a", "label": "Opção 1", "value": "opcao1"}}, {{"key": "b", "label": "Opção 2", "value": "opcao2"}}, {{"key": "c", "label": "Opção 3", "value": "opcao3"}}]}}
]
```

Gere apenas o JSON, sem explicações adicionais."""


class TaskQuestioner:
    """Gera e gerencia perguntas sobre a tarefa."""

    def __init__(self, client):
        """
        Args:
            client: Cliente Claude CLI para gerar perguntas
        """
        self.client = client

    async def generate_questions(self, task: str) -> list[Question]:
        """
        Gera perguntas relevantes para a tarefa usando IA.

        Args:
            task: Descrição da tarefa

        Returns:
            Lista de perguntas com opções
        """
        prompt = QUESTION_GENERATION_PROMPT.format(task=task)
        response = await self.client.generate(prompt)

        # Debug para ver resposta
        print(f"[DEBUG] Resposta LLM perguntas: {response[:150]}...")

        questions = self._parse_questions(response)

        # Se não conseguiu parsear, retorna lista vazia (não usa fallback)
        if not questions:
            print(f"[DEBUG] Falha ao parsear perguntas. Resposta completa: {response}")

        return questions

    def _parse_questions(self, response: str) -> list[Question]:
        """Parse resposta JSON em lista de Questions."""
        try:
            # Tenta extrair JSON da resposta
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                data = json.loads(json_match.group())

                questions = []
                for item in data:
                    if isinstance(item, dict):
                        # Parse opções
                        options = []
                        for opt in item.get("options", []):
                            if isinstance(opt, dict):
                                options.append(QuestionOption(
                                    key=opt.get("key", ""),
                                    label=opt.get("label", ""),
                                    value=opt.get("value", opt.get("label", "")),
                                ))

                        questions.append(Question(
                            category=item.get("category", "GERAL"),
                            question=item.get("question", ""),
                            why=item.get("why", ""),
                            options=options,
                        ))

                return questions
        except json.JSONDecodeError:
            pass

        # Fallback: perguntas genéricas com opções
        return self._get_fallback_questions()

    def _get_fallback_questions(self) -> list[Question]:
        """Perguntas genéricas com opções caso a IA falhe."""
        return [
            Question(
                category="ESCOPO",
                question="Qual o tamanho/complexidade do projeto?",
                why="Define o escopo da implementação",
                options=[
                    QuestionOption("a", "MVP simples", "MVP com funcionalidades básicas"),
                    QuestionOption("b", "Projeto médio", "Projeto médio com várias features"),
                    QuestionOption("c", "Sistema completo", "Sistema robusto para produção"),
                ]
            ),
            Question(
                category="TECNOLOGIA",
                question="Qual linguagem de programação?",
                why="Define a stack técnica",
                options=[
                    QuestionOption("a", "Python", "Python"),
                    QuestionOption("b", "JavaScript/TS", "JavaScript ou TypeScript"),
                    QuestionOption("c", "Java", "Java"),
                    QuestionOption("d", "Go", "Go"),
                ]
            ),
            Question(
                category="USUARIOS",
                question="Quantos usuários simultâneos esperados?",
                why="Define requisitos de performance",
                options=[
                    QuestionOption("a", "Poucos (<100)", "Menos de 100 usuários"),
                    QuestionOption("b", "Médio (100-1000)", "Entre 100 e 1000 usuários"),
                    QuestionOption("c", "Muitos (1000+)", "Mais de 1000 usuários"),
                ]
            ),
            Question(
                category="DADOS",
                question="Precisa persistir dados?",
                why="Define necessidade de banco de dados",
                options=[
                    QuestionOption("a", "Não", "Sem persistência"),
                    QuestionOption("b", "Arquivo local", "Salvar em arquivos"),
                    QuestionOption("c", "Banco SQL", "PostgreSQL, MySQL, etc"),
                    QuestionOption("d", "Banco NoSQL", "MongoDB, Redis, etc"),
                ]
            ),
            Question(
                category="SEGURANCA",
                question="Precisa de autenticação?",
                why="Define requisitos de segurança",
                options=[
                    QuestionOption("a", "Não", "Sem autenticação"),
                    QuestionOption("b", "Simples", "Login básico com senha"),
                    QuestionOption("c", "OAuth", "Login social (Google, GitHub)"),
                    QuestionOption("d", "Completo", "Auth completa com 2FA"),
                ]
            ),
        ]

    def create_result(self, task: str, questions: list[Question]) -> QuestionnaireResult:
        """Cria resultado do questionário."""
        return QuestionnaireResult(task=task, questions=questions)

    def _generate_contextual_questions(self, task: str) -> list[Question]:
        """Gera perguntas baseadas em palavras-chave do projeto."""
        task_lower = task.lower()
        questions = []

        # Detecta domínio e gera perguntas específicas
        if "locação" in task_lower or "aluguel" in task_lower:
            if "jogo" in task_lower or "game" in task_lower:
                questions = self._questions_locacao_jogos()
            else:
                questions = self._questions_locacao_geral()

        elif "e-commerce" in task_lower or "loja" in task_lower or "venda" in task_lower:
            questions = self._questions_ecommerce()

        elif "autenticação" in task_lower or "login" in task_lower or "auth" in task_lower:
            questions = self._questions_auth()

        elif "financeiro" in task_lower or "pagamento" in task_lower:
            questions = self._questions_financeiro()

        elif "estoque" in task_lower or "inventário" in task_lower:
            questions = self._questions_estoque()

        return questions

    def _questions_locacao_jogos(self) -> list[Question]:
        """Perguntas específicas para sistema de locação de jogos."""
        return [
            Question(
                category="PRODUTOS",
                question="Que tipo de jogos serão alugados?",
                why="Define o catálogo e regras de negócio",
                options=[
                    QuestionOption("a", "Jogos físicos (CDs/DVDs)", "Jogos em mídia física"),
                    QuestionOption("b", "Jogos digitais (códigos)", "Códigos de ativação"),
                    QuestionOption("c", "Ambos", "Físicos e digitais"),
                    QuestionOption("d", "Consoles também", "Jogos + consoles para alugar"),
                ]
            ),
            Question(
                category="LOCACAO",
                question="Como funciona o período de locação?",
                why="Define regras de tempo e cobrança",
                options=[
                    QuestionOption("a", "Por dia", "Cobrança diária"),
                    QuestionOption("b", "Por hora", "Cobrança por hora"),
                    QuestionOption("c", "Pacotes (3/7/15 dias)", "Pacotes de dias"),
                    QuestionOption("d", "Assinatura mensal", "Plano mensal ilimitado"),
                ]
            ),
            Question(
                category="MULTAS",
                question="Precisa de sistema de multas por atraso?",
                why="Define regras de penalidade",
                options=[
                    QuestionOption("a", "Não", "Sem multas"),
                    QuestionOption("b", "Multa fixa", "Valor fixo por dia de atraso"),
                    QuestionOption("c", "Multa percentual", "% do valor por dia"),
                    QuestionOption("d", "Bloqueio de conta", "Bloqueia até regularizar"),
                ]
            ),
            Question(
                category="RESERVA",
                question="Precisa de sistema de reserva antecipada?",
                why="Define fluxo de reservas",
                options=[
                    QuestionOption("a", "Não", "Apenas disponibilidade imediata"),
                    QuestionOption("b", "Reserva simples", "Reservar para data futura"),
                    QuestionOption("c", "Fila de espera", "Entrar na fila se indisponível"),
                ]
            ),
            Question(
                category="CLIENTES",
                question="Precisa de cadastro de clientes com histórico?",
                why="Define gestão de clientes",
                options=[
                    QuestionOption("a", "Básico", "Nome, contato, documento"),
                    QuestionOption("b", "Com histórico", "Histórico de locações"),
                    QuestionOption("c", "Com score", "Pontuação de confiabilidade"),
                    QuestionOption("d", "Completo", "Histórico + score + preferências"),
                ]
            ),
            Question(
                category="FINANCEIRO",
                question="Quais relatórios financeiros precisa?",
                why="Define módulo de gestão financeira",
                options=[
                    QuestionOption("a", "Básico", "Faturamento diário/mensal"),
                    QuestionOption("b", "Detalhado", "Por jogo, cliente, período"),
                    QuestionOption("c", "Completo", "Inadimplência, projeções, lucro"),
                    QuestionOption("d", "Dashboard", "Gráficos e métricas em tempo real"),
                ]
            ),
            Question(
                category="ESTOQUE",
                question="Como controlar disponibilidade dos jogos?",
                why="Define gestão de estoque",
                options=[
                    QuestionOption("a", "Manual", "Baixa manual no sistema"),
                    QuestionOption("b", "Automático", "Atualiza ao confirmar locação"),
                    QuestionOption("c", "Com alertas", "Avisa quando estoque baixo"),
                ]
            ),
        ]

    def _questions_locacao_geral(self) -> list[Question]:
        """Perguntas para locação geral."""
        return [
            Question(
                category="PRODUTOS",
                question="O que será alugado?",
                why="Define o tipo de produto/serviço",
                options=[
                    QuestionOption("a", "Equipamentos", "Máquinas, ferramentas"),
                    QuestionOption("b", "Veículos", "Carros, motos, bicicletas"),
                    QuestionOption("c", "Imóveis", "Casas, apartamentos, salas"),
                    QuestionOption("d", "Outros", "Especificar"),
                ]
            ),
        ]

    def _questions_ecommerce(self) -> list[Question]:
        """Perguntas para e-commerce."""
        return [
            Question(
                category="VENDEDORES",
                question="Quem vende na plataforma?",
                why="Define modelo de negócio",
                options=[
                    QuestionOption("a", "Só eu", "Loja própria"),
                    QuestionOption("b", "Marketplace", "Múltiplos vendedores"),
                ]
            ),
        ]

    def _questions_auth(self) -> list[Question]:
        """Perguntas para sistema de autenticação."""
        return [
            Question(
                category="METODOS",
                question="Quais métodos de login?",
                why="Define integrações necessárias",
                options=[
                    QuestionOption("a", "Email/senha", "Login tradicional"),
                    QuestionOption("b", "Social", "Google, Facebook, etc"),
                    QuestionOption("c", "SSO", "Single Sign-On corporativo"),
                ]
            ),
        ]

    def _questions_financeiro(self) -> list[Question]:
        """Perguntas para sistema financeiro."""
        return [
            Question(
                category="PAGAMENTOS",
                question="Quais formas de pagamento?",
                why="Define integrações de pagamento",
                options=[
                    QuestionOption("a", "Dinheiro", "Apenas presencial"),
                    QuestionOption("b", "Cartão", "Crédito/débito"),
                    QuestionOption("c", "PIX", "Pagamento instantâneo"),
                    QuestionOption("d", "Todos", "Múltiplas formas"),
                ]
            ),
        ]

    def _questions_estoque(self) -> list[Question]:
        """Perguntas para sistema de estoque."""
        return [
            Question(
                category="CONTROLE",
                question="Tipo de controle de estoque?",
                why="Define complexidade do módulo",
                options=[
                    QuestionOption("a", "Simples", "Entrada/saída"),
                    QuestionOption("b", "Com lotes", "Controle por lote/validade"),
                    QuestionOption("c", "Multi-local", "Vários depósitos"),
                ]
            ),
        ]
