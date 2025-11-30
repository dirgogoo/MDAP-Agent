# CLI Interativa

## Visão Geral

A CLI interativa (`mdap_interactive.py`) oferece uma experiência estilo Claude Code com:
- Display em tempo real
- Checkpoints para validar decisões
- Código com syntax highlight
- Opções para regenerar/editar

## Como Usar

```bash
python mdap_interactive.py "descrição da tarefa" [k] [max_samples]
```

## Layout da Interface

```
╔═══════════════════════════════════════════════════════════════════╗
║  MDAP Interactive                                                  ║
║                                                                    ║
║  Tarefa: Criar validador de CPF brasileiro                        ║
║  Config: k=2, max_samples=5                                        ║
╚═══════════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════════╗
║  FASE 1: EXPAND - Descobrindo Requisitos                          ║
╠═══════════════════════════════════════════════════════════════════╣
║                                                                    ║
║  00:05 Analisando tarefa...                                       ║
║  00:12 Encontrados 9 requisitos                                   ║
║                                                                    ║
╚═══════════════════════════════════════════════════════════════════╝
```

## Checkpoints

### Checkpoint 1: Após EXPAND

Mostra os requisitos encontrados e pergunta como proceder:

```
╔═══════════════════════════════════════════════════════════════════╗
║  CHECKPOINT: Requisitos Encontrados                               ║
╠═══════════════════════════════════════════════════════════════════╣
║                                                                    ║
║  ┌─ 9 Requisitos ─────────────────────────────────────────────┐   ║
║  │  1. Validar formato do CPF (11 dígitos)                    │   ║
║  │  2. Remover formatação (pontos e traços)                   │   ║
║  │  3. Calcular primeiro dígito verificador                   │   ║
║  │  4. Calcular segundo dígito verificador                    │   ║
║  │  5. Rejeitar CPFs com todos dígitos iguais                │   ║
║  │  ...                                                       │   ║
║  └────────────────────────────────────────────────────────────┘   ║
║                                                                    ║
║  Opções:                                                           ║
║    [1] Continuar com estes requisitos                             ║
║    [2] Adicionar mais requisitos                                  ║
║    [3] Remover alguns requisitos                                  ║
║    [4] Refazer EXPAND                                             ║
║                                                                    ║
║  Escolha [1/2/3/4]: _                                             ║
║                                                                    ║
╚═══════════════════════════════════════════════════════════════════╝
```

**Ações:**
- `1` - Continua para DECOMPOSE
- `2` - Permite digitar requisitos adicionais
- `3` - Permite escolher quais remover (por número)
- `4` - Refaz a fase EXPAND do zero

### Checkpoint 2: Após DECOMPOSE

Mostra as funções planejadas:

```
╔═══════════════════════════════════════════════════════════════════╗
║  CHECKPOINT: Funções Planejadas                                   ║
╠═══════════════════════════════════════════════════════════════════╣
║                                                                    ║
║  1. def limpar_cpf(cpf: str) -> str                               ║
║  2. def validar_tamanho(cpf: str) -> bool                         ║
║  3. def validar_digitos_iguais(cpf: str) -> bool                  ║
║  4. def calcular_digito(cpf: str, pos: int) -> int                ║
║  5. def validar_cpf(cpf: str) -> bool                             ║
║                                                                    ║
║  Opções:                                                           ║
║    [1] Aprovar e gerar código                                     ║
║    [2] Adicionar função                                           ║
║    [3] Remover função                                             ║
║    [4] Renomear função                                            ║
║    [5] Refazer DECOMPOSE                                          ║
║                                                                    ║
║  Escolha [1/2/3/4/5]: _                                           ║
║                                                                    ║
╚═══════════════════════════════════════════════════════════════════╝
```

### Checkpoint 3: Após Cada GENERATE

Mostra o código gerado com syntax highlight:

```
╔═══════════════════════════════════════════════════════════════════╗
║  CHECKPOINT: Código Gerado                                        ║
╠═══════════════════════════════════════════════════════════════════╣
║                                                                    ║
║  Função: def limpar_cpf(cpf: str) -> str                          ║
║                                                                    ║
║  ┌─ Código ───────────────────────────────────────────────────┐   ║
║  │   1 │ def limpar_cpf(cpf: str) -> str:                     │   ║
║  │   2 │     """Remove formatação do CPF."""                  │   ║
║  │   3 │     return ''.join(c for c in cpf if c.isdigit())    │   ║
║  └────────────────────────────────────────────────────────────┘   ║
║                                                                    ║
║  Votação: 2 candidatos, 1 grupo, {'group_0': 2}                   ║
║                                                                    ║
║  Opções:                                                           ║
║    [Enter/1] Aprovar e continuar                                  ║
║    [2] Regenerar (nova votação)                                   ║
║    [3] Editar código manualmente                                  ║
║    [4] Pular esta função                                          ║
║                                                                    ║
║  Escolha: _                                                        ║
║                                                                    ║
╚═══════════════════════════════════════════════════════════════════╝
```

**Ações:**
- `Enter` ou `1` - Aprova e vai para próxima função
- `2` - Regenera com nova votação MDAP
- `3` - Abre editor para modificar manualmente
- `4` - Pula esta função (não gera código)

### Checkpoint Final

```
╔═══════════════════════════════════════════════════════════════════╗
║  CHECKPOINT: Resultado Final                                      ║
╠═══════════════════════════════════════════════════════════════════╣
║                                                                    ║
║  ┌─ Resumo ───────────────────────────────────────────────────┐   ║
║  │  Tarefa:      Criar validador de CPF brasileiro            │   ║
║  │  Requisitos:  9                                            │   ║
║  │  Funções:     5                                            │   ║
║  │  Códigos:     5                                            │   ║
║  └────────────────────────────────────────────────────────────┘   ║
║                                                                    ║
║  Salvar resultado? [y/n]: _                                       ║
║                                                                    ║
╚═══════════════════════════════════════════════════════════════════╝
```

## Edição Manual de Código

Ao escolher opção `3` (Editar):

```
Cole o código editado (linha vazia + 'FIM' para terminar):
def limpar_cpf(cpf: str) -> str:
    # Minha versão editada
    return cpf.replace('.', '').replace('-', '')

FIM
```

## Exportar para Arquivo

Ao final, pergunta se quer exportar:

```
Exportar código para arquivo .py? [y/n]: y
Código exportado para: mdap_codigo_gerado.py
```

O arquivo gerado contém todas as funções:

```python
# def limpar_cpf(cpf: str) -> str
def limpar_cpf(cpf: str) -> str:
    return ''.join(c for c in cpf if c.isdigit())

# def validar_cpf(cpf: str) -> bool
def validar_cpf(cpf: str) -> bool:
    # ...
```

## Componentes da CLI

### InteractivePrompt (`mdap_cli/prompts.py`)

```python
class InteractivePrompt:
    def ask_expand_approval(self, requisitos) -> tuple[str, Optional[list[str]]]
    def ask_decompose_approval(self, funcoes) -> tuple[str, Optional[any]]
    def ask_generate_approval(self, funcao, codigo, votacao_info) -> tuple[str, Optional[str]]
    def ask_final_approval(self, resultado) -> bool
    def show_code_preview(self, codigos)
```

### CodeViewer (`mdap_cli/code_view.py`)

```python
def render_code(code, language="python", title="Código") -> Panel
def print_code_block(console, code, title=None)
def print_function_list(console, functions, title="Funções")

class CodeViewer:
    def add_code(self, name, code)
    def show(self, name=None)
    def export_to_file(self, filepath)
```

## Atalhos

| Tecla | Ação |
|-------|------|
| `Enter` | Aceitar opção default |
| `1-5` | Selecionar opção |
| `Ctrl+C` | Cancelar execução |

## Dicas

1. **Use Enter para aprovar** - Na maioria dos casos, o default é continuar
2. **Regenere se necessário** - Às vezes a segunda votação gera código melhor
3. **Edite código simples** - Para pequenos ajustes, é mais rápido editar
4. **Exporte sempre** - O arquivo .py é mais fácil de usar
