# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MDAP Agent is a code generation framework implementing **MDAP voting** based on the paper "Solving a Million-Step LLM Task with Zero Errors" (arXiv:2511.09030). It generates multiple code candidates, compares them semantically using an LLM discriminator, and votes to choose the best using first-to-ahead-by-k algorithm.

The project includes an **intelligent REPL** with an **AI-powered orchestrator** that understands natural language and automatically routes to the appropriate action.

## Commands

```bash
# Install dependencies
pip install -e ".[dev]"   # Full dev install with pytest, black, ruff, mypy
pip install rich          # CLI interface

# Run the intelligent REPL (recommended)
mdap-repl                 # Interactive mode with AI orchestrator

# Run automatic mode (legacy)
python mdap_runner.py "Criar validador de CPF brasileiro"

# Run interactive mode with checkpoints (legacy)
python mdap_interactive.py "Criar validador de CPF brasileiro"

# CLI via installed package
mdap-agent "Task description" --k 3 --max-steps 50 -v

# Run tests
pytest                    # All tests
pytest tests/test_voter.py -v  # Specific test file

# Linting & formatting
black mdap tests          # Format code
ruff check mdap tests     # Lint
mypy mdap                 # Type check
```

## REPL Mode (mdap-repl)

The intelligent REPL allows natural conversation with the orchestrator:

```bash
$ mdap-repl

> olá, o que você faz?
# AI detects: META_HELP → Shows capabilities

> crie um validador de CPF
# AI detects: TASK_SIMPLE → Runs pipeline directly

> quero um sistema de autenticação completo
# AI detects: TASK_COMPLEX → Asks questions first, then runs pipeline

> quais requisitos preciso para uma API de pagamentos?
# AI detects: TASK_EXPLORE → Expands requirements with questions

> como está o progresso?
# AI detects: META_STATUS → Shows pipeline status
```

### REPL Commands

| Command | Aliases | Description |
|---------|---------|-------------|
| `/run <task>` | `/go`, `/start` | Run MDAP pipeline |
| `/expand <task>` | `/e`, `/req` | Expand task into requirements |
| `/pause` | `/p` | Pause pipeline execution |
| `/resume` | `/r` | Resume paused pipeline |
| `/cancel` | `/stop` | Cancel and reset pipeline |
| `/status` | `/st` | Show orchestrator status |
| `/explain [id]` | `/why` | Explain current state or decision |
| `/history [n]` | `/hist` | Show decision history |
| `/resources` | `/res` | Show resource usage (tokens, cost) |
| `/budget type value` | - | Set budget (tokens/cost/time) |
| `/help` | `/h`, `/?` | Show available commands |
| `/clear` | `/cls` | Clear screen and history |
| `/exit` | `/quit`, `/q` | Exit the REPL |

### AI Intent Detection

The orchestrator uses AI to classify user intent into 12 categories:

| Intent | Examples | Action |
|--------|----------|--------|
| `TASK_SIMPLE` | "crie um validador de email" | Runs pipeline directly |
| `TASK_COMPLEX` | "sistema de autenticação completo" | Questions → Pipeline |
| `TASK_EXPLORE` | "quais requisitos preciso?" | Expands requirements |
| `META_STATUS` | "como está?", "progresso" | Shows status |
| `META_EXPLAIN` | "por que escolheu isso?" | Explains decisions |
| `META_HELP` | "o que você faz?" | Shows capabilities |
| `CONTROL_PAUSE` | "pausa", "espera" | Pauses pipeline |
| `CONTROL_RESUME` | "continua", "segue" | Resumes pipeline |
| `CONTROL_CANCEL` | "cancela", "aborta" | Cancels pipeline |
| `CHAT_GREETING` | "olá", "oi" | Shows welcome |
| `CHAT_GENERAL` | "tudo bem?" | Chat via LLM |
| `CHAT_QUESTION` | "como funciona X?" | Answers via LLM |

### Questions with Options

When expanding tasks, the AI generates questions with predefined options:

```
[1/5] TECNOLOGIA
   Qual linguagem de programação?
   (Define a stack técnica)

   a) Python
   b) JavaScript/TS
   c) Java
   d) Go
   custom) Outro (digite)
   /skip para pular

   > a
   Selecionado: Python
```

## Architecture

### High-Level Flow
```
User Input → [Intent Detection] → Route to Action
                    ↓
         ┌─────────┼─────────┐
         ↓         ↓         ↓
      TASK      META      CHAT
         ↓         ↓         ↓
    Pipeline   Status    LLM Response
```

### Pipeline Flow
```
TASK → [EXPAND] → [DECOMPOSE] → [GENERATE with MDAP] → [VALIDATE] → RESULT
          ↓            ↓              ↓                    ↓
       atomic      function      code with             syntax
     requirements  signatures    voting                check
```

### Core Separation: Decision vs Execution

| Layer | Uses MDAP | Components | Purpose |
|-------|-----------|------------|---------|
| **Decision** | Yes | Expander, Decomposer, Generator, Validator, Decider | Non-deterministic - multiple candidates voted |
| **Execution** | No | ReadTool, WriteTool, GrepTool, GlobTool, PytestTool | Deterministic - single result, updates context |

### Package Structure

```
mdap/
├── __init__.py          # Exports: Language, StepType, Step, Candidate, VoteResult, Context, MDAPConfig
├── types.py             # Core dataclasses: Step, Candidate, VoteResult, Context, ContextSnapshot
├── agent/
│   ├── loop.py          # AgentLoop - main entry point, run() and run_interactive()
│   ├── context.py       # AgentContext - state management
│   └── step.py          # StepExecutor - dispatches to decision/execution
├── decision/            # MDAP voting layer
│   ├── expander.py      # Expander - generates atomic requirements
│   ├── decomposer.py    # Decomposer - organizes into functions
│   ├── generator.py     # Generator - implements code with voting
│   ├── validator.py     # Validator - verifies correctness
│   └── decider.py       # Decider - chooses next step
├── execution/           # Deterministic tools
│   ├── tools.py         # Tool, ToolRegistry, register_tool()
│   ├── file_ops.py      # ReadTool, WriteTool
│   ├── search.py        # GrepTool, GlobTool, FindFunctionTool
│   └── test_runner.py   # PytestTool, PythonCheckTool
├── llm/
│   ├── client.py        # ClaudeClient - Anthropic API wrapper
│   └── client_cli.py    # ClaudeCLIClient - CLI wrapper (legacy)
└── mdap/                # Voting implementation
    ├── voter.py         # Voter - first-to-ahead-by-k algorithm
    ├── discriminator.py # Discriminator - semantic comparison
    └── red_flag.py      # RedFlagFilter - syntax/length/format checks

mdap_cli/
├── events.py            # EventBus pub/sub system for UI decoupling
├── display.py           # MDAPDisplay - Rich Live real-time display
├── prompts.py           # InteractivePrompt - checkpoint interactions
├── code_view.py         # CodeViewer - syntax highlighting utilities
├── repl/                # Interactive REPL
│   ├── __init__.py
│   ├── session.py       # REPLSession - main loop with smart mode
│   ├── commands.py      # CommandRouter - slash commands
│   ├── questioner.py    # TaskQuestioner - questions with options
│   └── ui.py            # UI components (Rich)
└── orchestrator/        # AI-powered orchestrator
    ├── __init__.py
    ├── orchestrator.py  # MDAPOrchestrator - main coordinator
    ├── state.py         # PipelineState - state machine (9 states)
    ├── executor.py      # PipelineExecutor - executes phases
    ├── tracker.py       # DecisionTracker - decision history
    ├── resources.py     # ResourceManager - tokens/cost/time
    ├── interrupts.py    # InterruptHandler - pause/resume/cancel
    ├── meta.py          # MetaIntelligence - explanations
    ├── intent.py        # IntentDetector - AI intent classification
    └── adapter.py       # OrchestratorAdapter - REPL integration
```

### Orchestrator State Machine

```python
class PipelineState(Enum):
    IDLE = "idle"                    # Waiting for task
    EXPANDING = "expanding"          # EXPAND phase
    DECOMPOSING = "decomposing"      # DECOMPOSE phase
    GENERATING = "generating"        # GENERATE phase
    VALIDATING = "validating"        # VALIDATE phase
    PAUSED = "paused"               # User interrupted
    AWAITING_DECISION = "awaiting"  # Checkpoint waiting
    COMPLETED = "completed"          # Done
    ERROR = "error"                  # Failed
```

State transitions:
```
IDLE ──/run──> EXPANDING ──> DECOMPOSING ──> GENERATING ──> VALIDATING ──> COMPLETED
                  │              │               │              │
                  └──────────────┴───────────────┴──────────────┘
                                      │
                              Ctrl+C ou /pause
                                      │
                                      v
                                   PAUSED ──/resume──> (resume previous state)
                                      │
                                   /cancel
                                      │
                                      v
                                    IDLE
```

### MDAP Voting Algorithm

1. Generate candidates one at a time via `generator(step, context)`
2. Apply red-flag checks (syntax, length, format) - invalid candidates discarded
3. Classify into semantic groups using LLM discriminator
4. When a group has **k votes advantage** over others, it wins
5. If max_samples reached without winner, highest-voted group wins

Key parameters in `MDAPConfig`:
- `k`: Votes advantage to win (default: 3)
- `max_samples`: Maximum candidates (default: 20)
- `max_tokens_response`: Red-flag threshold (default: 500)
- `temperature`: LLM temperature (default: 0.1)

### Context Management

`Context` maintains mutable state; `snapshot()` creates immutable `ContextSnapshot` for MDAP voting:
```python
context = Context(task="...", language=Language.PYTHON)
context.add_requirement("Validate input format")
context.add_function(step)
context.add_code(step, generated_code)
snapshot = context.snapshot()  # Immutable for voting
```

### Prompt Templates

Located in `prompts/` directory:
- `expand.md` - Generate atomic requirements
- `decompose.md` - Organize into function signatures
- `generate.md` - Implement code
- `validate.md` - Verify correctness
- `discriminate.md` - Compare semantic equivalence
- `decide_next.md` - Choose next step

## Testing

Tests use pytest-asyncio with fixtures in `tests/conftest.py`:
- `mock_client` - Mocked ClaudeClient for unit tests
- `sample_step`, `sample_candidate`, `sample_context` - Test fixtures
- `candidate_factory` - Helper to create candidate lists

Key test files:
- `test_voter.py` - Voting algorithm tests
- `test_discriminator.py` - Semantic comparison tests
- `test_red_flag.py` - Red-flag filter tests
- `test_agent.py` - Agent loop integration tests
- `test_decision.py` - Decision layer tests
- `test_execution.py` - Execution tools tests

## Output Files

- `mdap_resultado.json` - Complete result with task, requirements, functions, code, metrics
- `mdap_codigo_gerado.py` - Exported Python code (interactive mode only)

## Resource Tracking

The orchestrator tracks resource usage:
- **Tokens**: Input/output tokens consumed
- **API Calls**: Number of LLM calls
- **Time**: Elapsed execution time
- **Cost**: Estimated USD cost

Set budgets with `/budget`:
```bash
/budget tokens 50000   # Max 50k tokens
/budget cost 0.10      # Max $0.10
/budget time 300       # Max 5 minutes
```
