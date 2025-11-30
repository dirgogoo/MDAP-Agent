# Arquitetura do MDAP Agent

## Visão Geral

O MDAP Agent implementa um agent loop dinâmico com separação clara entre **Decisão** (usa MDAP) e **Execução** (determinístico).

```
┌─────────────────────────────────────────────────────────────┐
│                      MDAP AGENT LOOP                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  DECISÃO (não-determinística) → USA MDAP            │   │
│   │                                                      │   │
│   │  - "Quais requisitos?" (EXPAND)                     │   │
│   │  - "Como organizar?" (DECOMPOSE)                    │   │
│   │  - "Como implementar?" (GENERATE)                   │   │
│   │  - "Está correto?" (VALIDATE)                       │   │
│   │                                                      │   │
│   │  → N agentes veem MESMO contexto (snapshot)         │   │
│   │  → Votação first-to-ahead-by-k                      │   │
│   └─────────────────────────────────────────────────────┘   │
│                           │                                  │
│                           ▼                                  │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  EXECUÇÃO (determinística) → SEM MDAP               │   │
│   │                                                      │   │
│   │  - Ler arquivo                                       │   │
│   │  - Buscar código (grep)                             │   │
│   │  - Rodar testes                                      │   │
│   │  - Aplicar edição                                    │   │
│   │                                                      │   │
│   │  → Resultado único, atualiza contexto               │   │
│   └─────────────────────────────────────────────────────┘   │
│                           │                                  │
│                           ▼                                  │
│                    CONTEXTO ATUALIZADO                       │
│                           │                                  │
│                           ▼                                  │
│                   próxima DECISÃO...                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Componentes Principais

### 1. MDAPAgentLoop (`mdap_runner.py`)

Classe principal que implementa o agent loop.

```python
class MDAPAgentLoop:
    def __init__(self, config: MDAPConfig):
        self.config = config
        self.client = ClaudeCLIClient(config)
        self.voter = Voter(self.client, config)

    async def run(self, task: str) -> dict:
        """Loop principal - decide próximo passo até completar"""

    async def expand(self, target: str, context: AgentContext) -> list[str]:
        """EXPAND: Descobre requisitos atômicos"""

    async def decompose(self, requisitos: list[str], context: AgentContext) -> list[str]:
        """DECOMPOSE: Organiza em funções"""

    async def generate_with_mdap(self, funcao: str, context: AgentContext) -> str:
        """GENERATE: Implementa com votação MDAP"""
```

### 2. AgentContext

Mantém o estado acumulado durante a execução.

```python
@dataclass
class AgentContext:
    task: str
    requisitos: list = field(default_factory=list)
    funcoes: list = field(default_factory=list)
    codigos: dict = field(default_factory=dict)
    steps_history: list = field(default_factory=list)
    depth: int = 0
    max_depth: int = 3

    def snapshot(self) -> str:
        """Retorna snapshot do contexto para votação"""
```

### 3. EventBus (`mdap_cli/events.py`)

Sistema pub/sub para desacoplar lógica de UI.

```python
class EventBus:
    def subscribe(self, event_type: EventType, handler: Callable)
    def emit(self, event: Event)
    def emit_simple(self, event_type: EventType, **data)
```

Tipos de eventos:
- `PHASE_START`, `PHASE_END` - Início/fim de fases
- `STEP_START`, `STEP_END` - Início/fim de passos
- `VOTE_START`, `CANDIDATE_GENERATED`, `VOTE_COMPLETE` - Votação
- `LOG`, `LOG_ERROR` - Logs

### 4. InteractivePrompt (`mdap_cli/prompts.py`)

Gerencia checkpoints interativos.

```python
class InteractivePrompt:
    def ask_expand_approval(self, requisitos: list[str]) -> tuple[str, Optional[list[str]]]
    def ask_decompose_approval(self, funcoes: list[str]) -> tuple[str, Optional[any]]
    def ask_generate_approval(self, funcao: str, codigo: str, votacao_info: dict) -> tuple[str, Optional[str]]
```

### 5. MDAPDisplay (`mdap_cli/display.py`)

Display em tempo real usando Rich.

```python
class MDAPDisplay:
    def __init__(self, event_bus: EventBus)
    def render(self) -> Layout
    async def run(self)  # Loop de atualização
```

## Fluxo de Execução

### Modo Automático (`mdap_runner.py`)

```
1. Inicializa MDAPAgentLoop
2. Loop:
   a. decide_next_step() → determina ação
   b. Executa ação (expand/decompose/generate)
   c. Atualiza contexto
   d. Repete até DONE
3. Salva resultado em JSON
```

### Modo Interativo (`mdap_interactive.py`)

```
1. Inicializa MDAPInteractive
2. EXPAND:
   a. Gera requisitos
   b. CHECKPOINT: Usuário aprova/modifica
3. DECOMPOSE:
   a. Gera funções
   b. CHECKPOINT: Usuário aprova/modifica
4. GENERATE (para cada função):
   a. Gera código com MDAP
   b. CHECKPOINT: Usuário aprova/regenera/edita
5. CHECKPOINT FINAL: Salvar?
6. Exporta código se solicitado
```

## Chamadas Aninhadas

Quando o código gerado chama funções que não existem:

```python
def _detectar_sub_funcoes(self, codigo: str, context: AgentContext) -> list[str]:
    """Detecta chamadas a funções que não existem"""
    # Usa regex para encontrar chamadas
    # Filtra built-ins e funções já existentes
    # Retorna lista de funções a gerar
```

Se detectadas, gera recursivamente com controle de profundidade:

```python
if sub_funcoes and context.depth < context.max_depth:
    context.depth += 1
    sub_codigo = await self.generate_with_mdap(sub_func, context)
    context.codigos[sub_func] = sub_codigo
    context.depth -= 1
```

## Estrutura de Arquivos

```
mdap-agent/
├── mdap_runner.py           # Agent loop automático
├── mdap_interactive.py      # Agent loop interativo
├── mdap_cli/
│   ├── __init__.py
│   ├── events.py            # EventBus pub/sub
│   ├── display.py           # Rich Live display
│   ├── prompts.py           # Checkpoints interativos
│   └── code_view.py         # Syntax highlight
└── docs/
    └── *.md                 # Documentação
```

## Estrutura do Framework MDAP

O framework MDAP está incluído no repositório:
```
mdap/
├── types.py            # Step, StepType, Language, MDAPConfig
├── llm/
│   ├── client.py       # ClaudeClient (API)
│   └── client_cli.py   # ClaudeCLIClient (CLI local)
├── mdap/
│   ├── voter.py        # Voter (votação MDAP)
│   ├── discriminator.py # Comparador semântico
│   └── red_flag.py     # Filtros de qualidade
├── decision/
│   ├── expander.py     # EXPAND
│   ├── decomposer.py   # DECOMPOSE
│   ├── generator.py    # GENERATE
│   └── validator.py    # VALIDATE
└── agent/
    ├── loop.py         # Agent loop principal
    └── context.py      # Contexto acumulado
```
