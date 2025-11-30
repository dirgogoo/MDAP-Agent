# Votação MDAP

## O Que É MDAP

MDAP (Massively Decomposed Agentic Processes) é uma técnica do paper **"Solving a Million-Step LLM Task with Zero Errors"** (arXiv:2511.09030).

A ideia central: **gerar múltiplos candidatos e votar para escolher o melhor**.

## Por Que Funciona

LLMs são probabilísticos - podem gerar respostas diferentes para o mesmo prompt. Algumas respostas são melhores que outras.

**Sem MDAP:**
```
Prompt → LLM → 1 resposta (pode ser boa ou ruim)
```

**Com MDAP:**
```
Prompt → LLM → N respostas → Votação → Melhor resposta
```

## First-to-ahead-by-k

O algoritmo de votação usado é **first-to-ahead-by-k**:

1. Gera candidatos um por vez
2. Compara cada novo candidato com os existentes
3. Agrupa candidatos semanticamente equivalentes
4. Quando um grupo tem **k votos de vantagem**, ele vence

### Exemplo com k=2

```
Candidato 1: def foo(): return x + 1
  → Grupo A: [Candidato 1]  (1 voto)

Candidato 2: def foo(): return 1 + x
  → Discriminador: "São equivalentes?"
  → SIM (mesma semântica)
  → Grupo A: [Candidato 1, Candidato 2]  (2 votos)
  → Grupo A tem 2 votos de vantagem → VENCEDOR!
```

## LLM Discriminador

Para comparar candidatos, usamos o próprio LLM como discriminador:

```
Prompt: "Estes dois códigos são semanticamente equivalentes?
         Código A: ...
         Código B: ...
         Responda apenas YES ou NO."
```

Se YES → Mesmo grupo
Se NO → Grupos diferentes

## Red-Flagging

Antes de votar, candidatos inválidos são descartados:

- **Syntax error** - Código não parseia
- **Muito longo** - Excede limite de tokens
- **Mal formatado** - Não segue o formato esperado

```python
def red_flag_check(candidate: str) -> bool:
    # Verifica se parseia
    try:
        compile(candidate, '<string>', 'exec')
    except SyntaxError:
        return False  # Descarta

    # Verifica tamanho
    if len(candidate) > MAX_TOKENS:
        return False  # Descarta

    return True  # OK para votar
```

## Fluxo Completo

```
┌─────────────────────────────────────────────────────────────┐
│                    VOTAÇÃO MDAP                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. GERAR candidato                                          │
│     │                                                        │
│     ▼                                                        │
│  2. RED-FLAG check                                           │
│     │                                                        │
│     ├─ FALHOU → Descartar, voltar a 1                       │
│     │                                                        │
│     ▼                                                        │
│  3. DISCRIMINAR com candidatos existentes                    │
│     │                                                        │
│     ├─ Equivalente a grupo X → Adicionar ao grupo X         │
│     │                                                        │
│     └─ Não equivalente → Criar novo grupo                   │
│     │                                                        │
│     ▼                                                        │
│  4. VERIFICAR vantagem                                       │
│     │                                                        │
│     ├─ Grupo tem k votos de vantagem → VENCEDOR!            │
│     │                                                        │
│     └─ Nenhum grupo venceu → Voltar a 1                     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Parâmetros

| Parâmetro | Default | Descrição |
|-----------|---------|-----------|
| `k` | 2-3 | Votos de vantagem para vencer. k=2 é mais rápido, k=3 é mais seguro |
| `max_samples` | 5-20 | Máximo de candidatos antes de desistir |
| `temperature` | 0.1 | Temperatura do LLM (baixo = mais consistente) |

## Implementação

### Voter (`mdap/mdap/voter.py`)

```python
async def vote(
    self,
    step: Step,
    context: str,
    generator: Callable,
    language: Language
) -> VoteResult:
    """
    Executa votação first-to-ahead-by-k.

    Args:
        step: Passo a ser votado
        context: Contexto (snapshot)
        generator: Função que gera candidatos
        language: Linguagem do código

    Returns:
        VoteResult com vencedor e métricas
    """
```

### Resultado da Votação

```python
@dataclass
class VoteResult:
    winner: Candidate          # Candidato vencedor
    total_samples: int         # Total de candidatos gerados
    groups: dict[str, list]    # Grupos formados
    votes_per_group: dict      # Votos por grupo
    winning_margin: int        # Margem de vitória
```

## Prova que MDAP Funciona

No output, procure:

```
[MDAP] GENERATE (MDAP): def validate_cpf(cpf: str) -> bool
[MDAP]   -> Votacao: samples=2, grupos=1, votos={'group_0': 2}
```

- `samples=2` → 2 candidatos foram gerados
- `grupos=1` → Discriminador agrupou em 1 grupo (equivalentes)
- `votos={'group_0': 2}` → Grupo 0 tem 2 votos → VENCEU com k=2

## Benefícios

1. **Maior confiabilidade** - Múltiplas verificações
2. **Detecção de erros** - Red-flagging elimina código ruim
3. **Consenso** - Só aceita quando há acordo
4. **Custo controlado** - max_samples limita chamadas

## Limitações

1. **Mais lento** - Múltiplas chamadas ao LLM
2. **Mais caro** - Mais tokens consumidos
3. **Discriminador imperfeito** - LLM pode errar comparação

## Quando Usar

✅ **Use MDAP quando:**
- Código crítico onde erros são custosos
- Funções com edge cases complexos
- Quando precisa de alta confiabilidade

❌ **Não use MDAP quando:**
- Código simples e direto
- Prototipagem rápida
- Custo é uma preocupação

## Referência

Paper: **"Solving a Million-Step LLM Task with Zero Errors"**
- arXiv: 2511.09030
- Autores: DeepMind
- Resultado: 1 milhão de passos com 0 erros
