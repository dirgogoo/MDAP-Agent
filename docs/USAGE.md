# Guia de Uso

## Instalação

### Requisitos
- Python 3.10+
- Claude CLI instalado e configurado
- Rich library

### Setup

```bash
# Clonar repositório
git clone https://github.com/dirgogoo/MDAP-Agent.git
cd MDAP-Agent

# Instalar dependências
pip install rich

# Verificar Claude CLI
claude --version
```

## Modos de Execução

### 1. Modo Automático

Executa o pipeline completo sem interação.

```bash
python mdap_runner.py "descrição da tarefa"
```

**Exemplo:**
```bash
python mdap_runner.py "Criar validador de CPF brasileiro"
```

**Output:**
```
============================================================
[MDAP] AGENT LOOP DINAMICO
============================================================
[MDAP] Tarefa: Criar validador de CPF brasileiro
[MDAP] Config: k=2, max_samples=5

[MDAP] [1] EXPAND
[MDAP] EXPAND: Criar validador de CPF brasileiro...
[MDAP]   -> 9 requisitos encontrados

[MDAP] [2] DECOMPOSE
[MDAP] DECOMPOSE: 9 requisitos
[MDAP]   -> 5 funcoes planejadas

[MDAP] [3] GENERATE
[MDAP] GENERATE (MDAP): def limpar_cpf(cpf: str) -> str
[MDAP]   -> Votacao: samples=2, grupos=1, votos={'group_0': 2}
...
```

### 2. Modo Interativo

Executa com checkpoints para você aprovar cada fase.

```bash
python mdap_interactive.py "descrição da tarefa"
```

**Exemplo:**
```bash
python mdap_interactive.py "Criar validador de CPF brasileiro"
```

**Checkpoints:**

1. **Após EXPAND** - Aprovar requisitos
   ```
   Opções:
   [1] Continuar com estes requisitos
   [2] Adicionar mais requisitos
   [3] Remover alguns
   [4] Refazer EXPAND
   ```

2. **Após DECOMPOSE** - Aprovar funções
   ```
   Opções:
   [1] Aprovar e gerar código
   [2] Adicionar função
   [3] Remover função
   [4] Renomear função
   [5] Refazer DECOMPOSE
   ```

3. **Após cada GENERATE** - Aprovar código
   ```
   Opções:
   [Enter/1] Aprovar e continuar
   [2] Regenerar (nova votação)
   [3] Editar código manualmente
   [4] Pular esta função
   ```

## Parâmetros

| Parâmetro | Default | Descrição |
|-----------|---------|-----------|
| `tarefa` | - | Descrição da tarefa (obrigatório) |
| `k` | 2 | Votos de vantagem para vencer |
| `max_samples` | 5 | Máximo de candidatos por votação |

**Exemplo com parâmetros:**
```bash
python mdap_interactive.py "Criar API REST" 3 10
```

## Resultado

O resultado é salvo em `mdap_resultado.json`:

```json
{
  "tarefa": "Criar validador de CPF brasileiro",
  "config": {"k": 2, "max_samples": 5},
  "requisitos": [
    "Validar formato do CPF (11 dígitos)",
    "Calcular primeiro dígito verificador",
    ...
  ],
  "funcoes": [
    "def limpar_cpf(cpf: str) -> str",
    "def validar_cpf(cpf: str) -> bool",
    ...
  ],
  "codigos": {
    "def limpar_cpf(cpf: str) -> str": "código...",
    ...
  },
  "metricas": {
    "iterations": 8,
    "chamadas_cli": 7,
    "tempo_total": "02:35"
  }
}
```

## Exportar Código

No modo interativo, ao final você pode exportar o código para um arquivo `.py`:

```
Exportar código para arquivo .py? [y/n]: y
Código exportado para: mdap_codigo_gerado.py
```

## Exemplos de Uso

### Validador de CPF
```bash
python mdap_interactive.py "Criar validador de CPF brasileiro"
```

### API REST
```bash
python mdap_interactive.py "Criar API REST para gerenciar usuários com CRUD"
```

### Módulo de Autenticação
```bash
python mdap_interactive.py "Criar módulo de autenticação JWT com login e refresh token"
```

### Funções de Utilidade
```bash
python mdap_interactive.py "Criar funções para manipular strings: slugify, truncate, capitalize_words"
```

## Dicas

1. **Seja específico na tarefa** - Quanto mais detalhes, melhor o resultado
2. **Use o modo interativo** - Permite corrigir problemas durante a execução
3. **Revise os requisitos** - O EXPAND às vezes gera requisitos desnecessários
4. **Regenere se necessário** - Se o código não ficou bom, peça para regenerar
5. **k=2 é suficiente** - Para a maioria dos casos, k=2 funciona bem
