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
| **Agent Loop Dinâmico** | Decide próximo passo automaticamente |
| **Chamadas Aninhadas** | Função complexa gera sub-funções recursivamente |
| **Votação MDAP** | Múltiplos candidatos votados por equivalência |
| **CLI Interativa** | Checkpoints para aprovar/modificar decisões |
| **Syntax Highlight** | Código formatado com Rich |

## Quick Start

### Modo Automático
```bash
python mdap_runner.py "Criar validador de CPF brasileiro"
```

### Modo Interativo (Recomendado)
```bash
python mdap_interactive.py "Criar validador de CPF brasileiro"
```

## Pipeline

```
TAREFA
   │
   ▼
[1] EXPAND
   │ "Quais requisitos atômicos?"
   │ → Lista de requisitos
   ▼
[2] DECOMPOSE
   │ "Como organizar em funções?"
   │ → Lista de assinaturas
   ▼
[3] GENERATE (com MDAP)
   │ → Votação para cada função
   │ → Código validado
   ▼
RESULTADO
```

## Estrutura

```
mdap-agent/
├── mdap_runner.py        # Modo automático
├── mdap_interactive.py   # Modo interativo com checkpoints
├── mdap_cli/
│   ├── events.py         # Sistema de eventos pub/sub
│   ├── display.py        # Display em tempo real (Rich)
│   ├── prompts.py        # Checkpoints interativos
│   └── code_view.py      # Syntax highlight
└── docs/
    ├── ARCHITECTURE.md   # Arquitetura detalhada
    ├── ORIGINAL_PLAN.md  # Plano original do projeto
    ├── USAGE.md          # Guia de uso
    ├── CLI_INTERACTIVE.md # CLI interativa
    └── MDAP_VOTING.md    # Votação MDAP explicada
```

## Requisitos

- Python 3.10+
- Rich (para CLI interativa)
- Claude CLI instalado (`claude --print`)

```bash
pip install rich
```

## Documentação

- [Arquitetura](docs/ARCHITECTURE.md)
- [Plano Original](docs/ORIGINAL_PLAN.md)
- [Guia de Uso](docs/USAGE.md)
- [CLI Interativa](docs/CLI_INTERACTIVE.md)
- [Votação MDAP](docs/MDAP_VOTING.md)

## Baseado Em

Paper: **"Solving a Million-Step LLM Task with Zero Errors"** (arXiv:2511.09030)

Conceitos implementados:
- MDAP: Massively Decomposed Agentic Processes
- First-to-ahead-by-k: Votação por margem de vantagem
- Red-flagging: Descarte de respostas inválidas
- LLM Discriminator: Comparação semântica de código

## Licença

MIT
