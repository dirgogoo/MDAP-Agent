# Plano Original do Projeto

Este documento contém o plano original que guiou o desenvolvimento do MDAP Agent.

## Objetivo

Criar um **agent loop com MDAP** que combina:
- Votação em cada decisão (do paper MAKER)
- Expansão de requisitos (não apenas decomposição)
- Chain dinâmica com contexto
- Separação entre Execução e Decisão

## Comparação com Sistemas Existentes

| Sistema | Votação | Expansão | Chain Dinâmica | Ferramentas |
|---------|---------|----------|----------------|-------------|
| ReAct | ❌ | ❌ | ✅ | ✅ |
| Tree of Thoughts | ✅ | ❌ | ❌ | ❌ |
| AutoGPT | ❌ | ✅ | ✅ | ✅ |
| MAKER (paper) | ✅ | ❌ | ❌ | ❌ |
| **MDAP Agent (nós)** | ✅ | ✅ | ✅ | ✅ |

## Conceito Chave: Expansão vs Decomposição

**Decomposição (top-down):** divide algo grande em partes
```
"Sistema auth" → [JWT, Password, Session]
```

**Expansão (bottom-up):** descobre requisitos atômicos
```
"Sistema auth" →
  - "precisa login com email"
  - "senha mínimo 8 chars"
  - "token expira em 24h"
  - "suporta refresh token"
  - ...
```

**Nosso fluxo:** EXPANSÃO → DECOMPOSIÇÃO → GERAÇÃO
```
TAREFA
   │
   ▼
EXPANSÃO (MDAP): "O que precisa existir?"
   │              → lista de requisitos atômicos
   ▼
DECOMPOSIÇÃO (MDAP): "Como organizar em módulos/funções?"
   │                  → estrutura de código
   ▼
GERAÇÃO (MDAP): "Implementar cada função"
   │             → código final
   ▼
VALIDAÇÃO (MDAP): "Está correto? Testes passam?"
```

## O Loop Principal

```python
async def agent_loop(task: str):
    context = Context(task=task)

    while not context.is_complete:
        # 1. DECISÃO: Qual próximo passo? (com MDAP)
        next_step = await mdap_decide(
            prompt="Dado o contexto, qual o próximo passo?",
            context=context.snapshot(),  # todos veem o mesmo
            k=3
        )

        if next_step.type == "EXECUTE":
            # 2a. EXECUÇÃO: determinística, sem MDAP
            result = await execute_tool(next_step.action)
            context.add_result(next_step, result)

        elif next_step.type == "GENERATE":
            # 2b. GERAÇÃO: com MDAP
            code = await mdap_generate(
                prompt=next_step.specification,
                context=context.snapshot(),
                k=3
            )
            context.add_code(code)

        elif next_step.type == "DONE":
            break

    return context.final_result()
```

## Tipos de Passos

| Tipo | MDAP? | Exemplo |
|------|-------|---------|
| `EXPAND` | ✅ | "Quais requisitos para auth?" |
| `DECOMPOSE` | ✅ | "Como organizar em funções?" |
| `GENERATE` | ✅ | "Implementar validate_token()" |
| `VALIDATE` | ✅ | "Este código está correto?" |
| `READ` | ❌ | Ler arquivo (determinístico) |
| `SEARCH` | ❌ | Buscar código (determinístico) |
| `TEST` | ❌ | Rodar testes (determinístico) |
| `APPLY` | ❌ | Aplicar edição (determinístico) |

## Conceitos do Paper Aplicados

### 1. Decomposição Máxima (MAD)
- **No paper**: 1 passo = 1 movimento de disco
- **No coding**: 1 passo = 1 decisão sobre função/método
  - Assinatura (params, retorno, tipos)
  - Estrutura lógica (if/else, loops)
  - Implementação do corpo
  - Validação/erro handling

### 2. Votação First-to-ahead-by-k
- Múltiplos agentes Claude geram respostas independentes
- Resposta vence quando tem `k` votos a mais que qualquer outra
- k=3 foi suficiente no paper para p > 0.99

### 3. Red-Flagging
- Descartar respostas muito longas (confusão)
- Descartar respostas mal formatadas
- Descartar código que não compila/parseia

## Arquitetura Proposta

```
┌──────────────────────────────────────────────────────────────────┐
│                    MDAP Coding Framework                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐   │
│  │ Decomposer  │───▶│  Generator  │───▶│       Voter         │   │
│  │             │    │             │    │                     │   │
│  │ Task → Steps│    │ Step → N    │    │ LLM Discriminator   │   │
│  │             │    │ candidates  │    │ (compara semântica) │   │
│  └─────────────┘    └─────────────┘    └─────────────────────┘   │
│         │                 │                      │               │
│         │                 ▼                      ▼               │
│         │     ┌─────────────────────────────────────────┐       │
│         │     │           Red-Flag Filter                │       │
│         │     │  - Max tokens exceeded?                  │       │
│         │     │  - Format invalid?                       │       │
│         │     │  - Code doesn't parse? (AST)             │       │
│         │     └─────────────────────────────────────────┘       │
│         │                                                        │
│         ▼                                                        │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                   Language Adapters                      │    │
│  │  ┌──────────────┐              ┌──────────────┐         │    │
│  │  │   Python     │              │  TypeScript  │         │    │
│  │  │  - ast.parse │              │  - ts-morph  │         │    │
│  │  │  - black fmt │              │  - prettier  │         │    │
│  │  └──────────────┘              └──────────────┘         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

## Estrutura de Arquivos Planejada

```
mdap-agent/
├── mdap/
│   ├── __init__.py
│   │
│   ├── agent/                     # Agent Loop
│   │   ├── __init__.py
│   │   ├── loop.py                # agent_loop() principal
│   │   ├── context.py             # Gerencia estado/contexto
│   │   └── step.py                # Dataclass Step e tipos
│   │
│   ├── decision/                  # Camada de DECISÃO (usa MDAP)
│   │   ├── __init__.py
│   │   ├── expander.py            # EXPAND: gera requisitos
│   │   ├── decomposer.py          # DECOMPOSE: organiza em funções
│   │   ├── generator.py           # GENERATE: implementa código
│   │   ├── validator.py           # VALIDATE: verifica correção
│   │   └── decider.py             # DECIDE: próximo passo
│   │
│   ├── execution/                 # Camada de EXECUÇÃO (sem MDAP)
│   │   ├── __init__.py
│   │   ├── tools.py               # Interface de ferramentas
│   │   ├── file_ops.py            # READ, WRITE
│   │   ├── search.py              # SEARCH (grep)
│   │   └── test_runner.py         # TEST
│   │
│   ├── mdap/                      # Core MDAP (votação)
│   │   ├── __init__.py
│   │   ├── voter.py               # First-to-ahead-by-k
│   │   ├── discriminator.py       # LLM compara candidatos
│   │   └── red_flag.py            # Filtros
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   └── client.py              # Claude API async
│   │
│   └── types.py                   # Dataclasses compartilhadas
│
├── prompts/
│   ├── expand.md                  # "Quais requisitos para X?"
│   ├── decompose.md               # "Como organizar em funções?"
│   ├── generate.md                # "Implemente esta função"
│   ├── validate.md                # "Este código está correto?"
│   ├── decide_next.md             # "Qual o próximo passo?"
│   └── discriminate.md            # "Qual resposta é melhor?"
│
├── examples/
│   ├── refactor_module.py         # Exemplo: refatorar módulo
│   ├── implement_feature.py       # Exemplo: nova feature
│   └── fix_bug.py                 # Exemplo: corrigir bug
│
├── results/                       # Logs e métricas
├── pyproject.toml
└── README.md
```

## Ordem de Implementação

### Fase 1: Core MDAP (fundação)
1. `mdap/types.py` - Dataclasses (Step, Context, Candidate, VoteResult)
2. `mdap/llm/client.py` - Wrapper Claude API async
3. `mdap/mdap/red_flag.py` - Filtros de qualidade
4. `mdap/mdap/discriminator.py` - LLM compara candidatos
5. `mdap/mdap/voter.py` - First-to-ahead-by-k

### Fase 2: Camada de Execução (ferramentas)
6. `mdap/execution/tools.py` - Interface base
7. `mdap/execution/file_ops.py` - READ, WRITE
8. `mdap/execution/search.py` - SEARCH (grep/glob)
9. `mdap/execution/test_runner.py` - Rodar testes

### Fase 3: Camada de Decisão (usa MDAP)
10. `mdap/decision/expander.py` - EXPAND requisitos
11. `mdap/decision/decomposer.py` - DECOMPOSE em funções
12. `mdap/decision/generator.py` - GENERATE código
13. `mdap/decision/validator.py` - VALIDATE correção
14. `mdap/decision/decider.py` - DECIDE próximo passo

### Fase 4: Agent Loop
15. `mdap/agent/context.py` - Gerencia estado
16. `mdap/agent/step.py` - Step e tipos
17. `mdap/agent/loop.py` - Loop principal

### Fase 5: Prompts e Exemplos
18. `prompts/*.md` - 6 prompts
19. `examples/implement_feature.py` - Primeiro exemplo
20. Testar e iterar

## Parâmetros do Experimento

| Parâmetro | Valor | Justificativa |
|-----------|-------|---------------|
| k (votação) | 3 | Suficiente para p > 0.99 segundo paper |
| max_tokens_response | 500 | Red-flag para respostas longas |
| temperature | 0.1 | Baixa para consistência, como no paper |
| model | claude-3-haiku | Custo baixo para experimento |
| max_samples_per_step | 20 | Limite de segurança |

## Métricas a Coletar

| Métrica | Descrição |
|---------|-----------|
| `steps_total` | Número de funções geradas |
| `samples_per_step` | Média de candidatos por função |
| `discriminator_calls` | Chamadas ao LLM comparador |
| `red_flag_rate` | % de candidatos descartados |
| `tokens_total` | Tokens totais consumidos |
| `cost_usd` | Custo total em dólares |
| `time_seconds` | Tempo total de execução |
| `success_rate` | % de funções que compilam/funcionam |

## Referência

Paper: **"Solving a Million-Step LLM Task with Zero Errors"** (arXiv:2511.09030)
