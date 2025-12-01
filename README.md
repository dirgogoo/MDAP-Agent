# MDAP Agent

Framework de geração de código com **votação MDAP** baseado no paper MAKER ("Solving a Million-Step LLM Task with Zero Errors").

## O Que É

MDAP (Massively Decomposed Agentic Processes) é uma técnica que:
- Gera múltiplos candidatos de código
- Compara semanticamente usando um LLM discriminador
- Vota para escolher o melhor (first-to-ahead-by-k)
- Garante alta confiabilidade no código gerado

## Features

| Feature | Descrição |
|---------|-----------|
| **REPL Inteligente** | Orquestrador com detecção de intenção por IA |
| **Perguntas com Opções** | Coleta contexto com múltipla escolha |
| **Agent Loop Dinâmico** | Decide próximo passo automaticamente |
| **Votação MDAP** | Múltiplos candidatos votados por equivalência |
| **Meta-Inteligência** | Explica decisões e rastreia recursos |
| **Controle Híbrido** | Automático com interrupções (pause/resume) |

## Quick Start

### REPL Inteligente (Recomendado)

```bash
pip install -e .
mdap-repl
```

```
> olá, o que você faz?
# Mostra capacidades

> crie um validador de CPF
# Detecta tarefa → Executa pipeline

> quero um sistema de autenticação completo
# Detecta tarefa complexa → Faz perguntas → Executa

> como está o progresso?
# Mostra status do pipeline
```

### Modo Automático (Legacy)

```bash
python mdap_runner.py "Criar validador de CPF brasileiro"
```

### Modo Interativo com Checkpoints (Legacy)

```bash
python mdap_interactive.py "Criar validador de CPF brasileiro"
```

## Comandos do REPL

| Comando | Descrição |
|---------|-----------|
| `/run <task>` | Executa pipeline MDAP |
| `/expand <task>` | Expande requisitos com perguntas |
| `/pause` | Pausa execução |
| `/resume` | Retoma execução |
| `/cancel` | Cancela pipeline |
| `/status` | Mostra estado atual |
| `/explain` | Explica o que está fazendo |
| `/history` | Histórico de decisões |
| `/resources` | Uso de recursos (tokens/custo) |
| `/help` | Lista de comandos |

## Detecção de Intenção por IA

O orquestrador classifica automaticamente sua mensagem:

| Intenção | Exemplo | Ação |
|----------|---------|------|
| Tarefa Simples | "crie um validador de email" | Executa pipeline |
| Tarefa Complexa | "sistema de autenticação completo" | Perguntas → Pipeline |
| Explorar | "quais requisitos preciso?" | Expande requisitos |
| Status | "como está?" | Mostra progresso |
| Ajuda | "o que você faz?" | Mostra capacidades |
| Chat | "como funciona X?" | Responde via LLM |

## Pipeline

```
TAREFA
   │
   ▼
[1] INTENT DETECTION (IA)
   │ "Qual a intenção do usuário?"
   │ → Classifica em 12 categorias
   ▼
[2] QUESTIONS (se TASK_COMPLEX)
   │ "Preciso de mais contexto"
   │ → Perguntas com opções
   ▼
[3] EXPAND
   │ "Quais requisitos atômicos?"
   │ → Lista de requisitos
   ▼
[4] DECOMPOSE
   │ "Como organizar em funções?"
   │ → Lista de assinaturas
   ▼
[5] GENERATE (com MDAP)
   │ → Votação para cada função
   │ → Código validado
   ▼
RESULTADO
```

## Estrutura

```
mdap-agent/
├── mdap_repl.py          # Entry point do REPL
├── mdap_runner.py        # Modo automático (legacy)
├── mdap_interactive.py   # Modo interativo (legacy)
├── mdap/                 # Core MDAP
│   ├── agent/            # Agent loop e contexto
│   ├── decision/         # Expander, Decomposer, Generator
│   ├── execution/        # Tools (Read, Write, Grep, etc)
│   ├── llm/              # Clientes LLM
│   └── mdap/             # Voter, Discriminator, RedFlag
├── mdap_cli/
│   ├── repl/             # REPL interativo
│   │   ├── session.py    # Loop principal com smart mode
│   │   ├── commands.py   # Comandos slash
│   │   ├── questioner.py # Perguntas com opções
│   │   └── ui.py         # Componentes visuais
│   ├── orchestrator/     # Orquestrador inteligente
│   │   ├── orchestrator.py  # Coordenador principal
│   │   ├── state.py      # State machine (9 estados)
│   │   ├── intent.py     # Detecção de intenção por IA
│   │   ├── tracker.py    # Histórico de decisões
│   │   ├── resources.py  # Tokens/custo/tempo
│   │   ├── meta.py       # Explicações
│   │   └── interrupts.py # Pause/resume/cancel
│   ├── events.py         # Sistema pub/sub
│   └── display.py        # Display Rich
└── docs/                 # Documentação
```

## Requisitos

- Python 3.10+
- Rich (para CLI interativa)
- Claude CLI instalado (`claude --print`)

```bash
pip install -e ".[dev]"
```

## Documentação

- [CLAUDE.md](CLAUDE.md) - Guia completo para Claude Code
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - Arquitetura detalhada
- [docs/USAGE.md](docs/USAGE.md) - Guia de uso
- [docs/MDAP_VOTING.md](docs/MDAP_VOTING.md) - Votação MDAP explicada

## Baseado Em

Paper: **"Solving a Million-Step LLM Task with Zero Errors"** (arXiv:2511.09030)

Conceitos implementados:
- MDAP: Massively Decomposed Agentic Processes
- First-to-ahead-by-k: Votação por margem de vantagem
- Red-flagging: Descarte de respostas inválidas
- LLM Discriminator: Comparação semântica de código

## Licença

MIT
