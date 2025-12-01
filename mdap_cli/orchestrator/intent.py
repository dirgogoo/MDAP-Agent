"""
Intent Detector - Detecta intenção do usuário via IA

Usa LLM para classificar a intenção de forma inteligente.
"""
from enum import Enum
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING
import json
import re

if TYPE_CHECKING:
    from ..repl.session import REPLSession


class UserIntent(Enum):
    """Intenções possíveis do usuário."""
    # Tarefas
    TASK_SIMPLE = "task_simple"       # Tarefa simples → executa direto
    TASK_COMPLEX = "task_complex"     # Tarefa complexa → perguntas primeiro
    TASK_EXPLORE = "task_explore"     # Quer explorar/entender requisitos

    # Meta
    META_STATUS = "meta_status"       # Quer saber status do pipeline
    META_EXPLAIN = "meta_explain"     # Quer explicação do que está acontecendo
    META_HELP = "meta_help"           # Quer ajuda/saber capacidades

    # Controle
    CONTROL_PAUSE = "control_pause"
    CONTROL_RESUME = "control_resume"
    CONTROL_CANCEL = "control_cancel"

    # Chat
    CHAT_GREETING = "chat_greeting"   # Saudação
    CHAT_GENERAL = "chat_general"     # Conversa geral
    CHAT_QUESTION = "chat_question"   # Pergunta sobre programação


@dataclass
class IntentResult:
    """Resultado da detecção de intenção."""
    intent: UserIntent
    confidence: float  # 0.0 a 1.0
    task: str = ""  # Tarefa extraída (se aplicável)
    reasoning: str = ""  # Explicação da classificação

    def __post_init__(self):
        if not self.reasoning:
            self.reasoning = ""


INTENT_CLASSIFICATION_PROMPT = """Classifique a intenção do usuário nesta mensagem:

"{message}"

Categorias possíveis:
- META_HELP: pergunta sobre capacidades ("o que você faz", "me ajuda")
- TASK_COMPLEX: quer criar sistema/projeto completo
- TASK_SIMPLE: quer criar algo simples (função, script)
- TASK_EXPLORE: quer analisar/explorar requisitos
- META_STATUS: pergunta sobre progresso
- CHAT_GREETING: apenas saudação (oi, olá)
- CHAT_QUESTION: pergunta técnica
- CHAT_GENERAL: conversa geral

Retorne sua classificação neste formato JSON:
```json
{{"intent": "CATEGORIA", "confidence": 0.9, "task": "descrição da tarefa se aplicável", "reasoning": "motivo da classificação"}}
```"""


class IntentDetector:
    """
    Detecta intenção do usuário usando IA.

    Usa LLM para classificar de forma inteligente.
    """

    def __init__(self, session: "REPLSession"):
        self.session = session

    async def detect(self, message: str) -> IntentResult:
        """
        Detecta intenção da mensagem usando IA.

        Args:
            message: Mensagem do usuário

        Returns:
            IntentResult com intenção, confiança e tarefa extraída
        """
        prompt = INTENT_CLASSIFICATION_PROMPT.format(message=message)

        try:
            response = await self.session.client.generate(prompt)
            result = self._parse_response(response, message)

            # Se LLM falhou, tenta detecção local como backup
            if result.confidence == 0.5 and result.intent == UserIntent.CHAT_GENERAL:
                local_result = self._detect_local(message)
                if local_result:
                    return local_result

            return result
        except Exception as e:
            # Fallback para detecção local
            local_result = self._detect_local(message)
            if local_result:
                return local_result

            return IntentResult(
                intent=UserIntent.CHAT_GENERAL,
                confidence=0.5,
                reasoning=f"Erro: {e}",
            )

    def _detect_local(self, message: str) -> Optional[IntentResult]:
        """Detecção local por palavras-chave como fallback."""
        msg = message.lower().strip()

        # META_HELP - perguntas sobre capacidades
        help_patterns = [
            "o que você faz", "o que vc faz", "o que você pode",
            "o que vc pode", "capaz de fazer", "suas capacidades",
            "me ajuda", "ajuda", "help", "comandos"
        ]
        if any(p in msg for p in help_patterns):
            return IntentResult(
                intent=UserIntent.META_HELP,
                confidence=0.85,
                reasoning="Detectado localmente: pergunta sobre capacidades",
            )

        # TASK_COMPLEX - sistemas/projetos
        complex_patterns = [
            "sistema", "projeto", "aplicação", "aplicativo", "app",
            "completo", "backend", "frontend", "banco de dados"
        ]
        task_verbs = ["quero", "preciso", "criar", "fazer", "desenvolver", "construir"]
        if any(p in msg for p in complex_patterns) and any(v in msg for v in task_verbs):
            return IntentResult(
                intent=UserIntent.TASK_COMPLEX,
                confidence=0.85,
                task=message,
                reasoning="Detectado localmente: tarefa complexa",
            )

        # TASK_SIMPLE - funções simples
        simple_patterns = ["função", "validador", "script", "hello world"]
        if any(p in msg for p in simple_patterns) and any(v in msg for v in task_verbs):
            return IntentResult(
                intent=UserIntent.TASK_SIMPLE,
                confidence=0.85,
                task=message,
                reasoning="Detectado localmente: tarefa simples",
            )

        # CHAT_GREETING - saudações simples (sem pergunta)
        greetings = ["oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "e aí", "eai"]
        if msg in greetings or (len(msg) < 15 and any(g in msg for g in greetings) and "?" not in msg):
            return IntentResult(
                intent=UserIntent.CHAT_GREETING,
                confidence=0.9,
                reasoning="Detectado localmente: saudação",
            )

        return None

    def _parse_response(self, response: str, original_message: str) -> IntentResult:
        """Parse resposta JSON do LLM."""
        try:
            # Remove markdown code blocks se houver
            clean_response = response.strip()
            clean_response = re.sub(r'^```(?:json)?\s*', '', clean_response)
            clean_response = re.sub(r'\s*```$', '', clean_response)

            # Tenta extrair JSON da resposta
            json_match = re.search(r'\{[\s\S]*\}', clean_response)
            if json_match:
                data = json.loads(json_match.group())

                intent_str = data.get("intent", "CHAT_GENERAL").upper()
                confidence = float(data.get("confidence", 0.7))
                task = data.get("task", "")
                reasoning = data.get("reasoning", "")

                # Mapeia string para enum
                intent_map = {
                    "TASK_SIMPLE": UserIntent.TASK_SIMPLE,
                    "TASK_COMPLEX": UserIntent.TASK_COMPLEX,
                    "TASK_EXPLORE": UserIntent.TASK_EXPLORE,
                    "META_STATUS": UserIntent.META_STATUS,
                    "META_EXPLAIN": UserIntent.META_EXPLAIN,
                    "META_HELP": UserIntent.META_HELP,
                    "CONTROL_PAUSE": UserIntent.CONTROL_PAUSE,
                    "CONTROL_RESUME": UserIntent.CONTROL_RESUME,
                    "CONTROL_CANCEL": UserIntent.CONTROL_CANCEL,
                    "CHAT_GREETING": UserIntent.CHAT_GREETING,
                    "CHAT_GENERAL": UserIntent.CHAT_GENERAL,
                    "CHAT_QUESTION": UserIntent.CHAT_QUESTION,
                }

                intent = intent_map.get(intent_str, UserIntent.CHAT_GENERAL)

                return IntentResult(
                    intent=intent,
                    confidence=confidence,
                    task=task if task else original_message,
                    reasoning=reasoning,
                )

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            pass

        # Fallback
        return IntentResult(
            intent=UserIntent.CHAT_GENERAL,
            confidence=0.5,
            reasoning="Não foi possível classificar com precisão",
        )
