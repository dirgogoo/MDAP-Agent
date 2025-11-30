"""
Test MDAP Agent using Claude CLI (headless mode)

Não precisa de API key - usa o próprio Claude Code CLI.

Uso:
    python examples/test_cli_mode.py
"""
import asyncio
import sys
sys.path.insert(0, '.')

from mdap.types import Step, StepType, Language, MDAPConfig
from mdap.llm.client_cli import ClaudeCLIClient
from mdap.mdap.voter import Voter
from mdap.mdap.red_flag import RedFlagFilter


async def test_single_generation():
    """Testa uma geração simples."""
    print("=" * 60)
    print("TEST 1: Single Generation (sem MDAP)")
    print("=" * 60)

    client = ClaudeCLIClient()

    response = await client.generate_code(
        specification="def is_even(n: int) -> bool que retorna True se n é par",
        language="python",
    )

    print(f"\nResposta do CLI:")
    print("-" * 40)
    print(response.content)
    print("-" * 40)
    print(f"Tokens estimados: {response.tokens_total}")
    print(f"Chamadas: {client.call_count}")

    return response.content


async def test_discriminator():
    """Testa comparação semântica."""
    print("\n" + "=" * 60)
    print("TEST 2: Discriminator (comparação semântica)")
    print("=" * 60)

    client = ClaudeCLIClient()

    code_a = "def is_even(n): return n % 2 == 0"
    code_b = "def is_even(num): return num % 2 == 0"
    code_c = "def is_even(n): return n % 2 != 0"  # DIFERENTE!

    print(f"\nCode A: {code_a}")
    print(f"Code B: {code_b}")
    print(f"Code C: {code_c}")

    result_ab = await client.compare_semantic(code_a, code_b)
    result_ac = await client.compare_semantic(code_a, code_c)

    print(f"\nA == B ? {result_ab} (esperado: True)")
    print(f"A == C ? {result_ac} (esperado: False)")
    print(f"Chamadas: {client.call_count}")


async def test_voting_simple():
    """Testa votação MDAP simples."""
    print("\n" + "=" * 60)
    print("TEST 3: Votação MDAP (k=2)")
    print("=" * 60)

    config = MDAPConfig(
        k=2,           # 2 votos de vantagem
        max_samples=5, # máximo 5 tentativas
    )

    client = ClaudeCLIClient(config)
    voter = Voter(client, config)

    step = Step(
        type=StepType.GENERATE,
        description="Função que verifica se número é primo",
        signature="def is_prime(n: int) -> bool",
    )

    async def generator(s: Step, ctx: str):
        return await client.generate_code(
            specification=f"{s.signature}: {s.description}",
            language="python",
        )

    print(f"\nIniciando votação para: {step.signature}")
    print(f"Config: k={config.k}, max_samples={config.max_samples}")
    print("\nGerando candidatos...")

    try:
        result = await voter.vote(
            step=step,
            context="",
            generator=generator,
            language=Language.PYTHON,
        )

        print(f"\n{'=' * 40}")
        print("RESULTADO DA VOTAÇÃO")
        print(f"{'=' * 40}")
        print(f"Total de amostras: {result.total_samples}")
        print(f"Grupos formados: {len(result.groups)}")
        print(f"Votos por grupo: {result.votes_per_group}")
        print(f"Margem de vitória: {result.winning_margin}")
        print(f"\nCódigo vencedor:")
        print("-" * 40)
        print(result.winner.code)
        print("-" * 40)
        print(f"\nChamadas ao CLI: {client.call_count}")

    except Exception as e:
        print(f"Erro na votação: {e}")


async def test_full_flow():
    """Testa fluxo completo simplificado."""
    print("\n" + "=" * 60)
    print("TEST 4: Fluxo Completo (Expand → Decompose → Generate)")
    print("=" * 60)

    client = ClaudeCLIClient()

    # 1. EXPAND
    print("\n[1/3] EXPAND - Descobrindo requisitos...")
    expand_response = await client.generate(
        prompt='Tarefa: "Criar validador de CPF"\n\nListe os requisitos atômicos (formato JSON array):',
        system="Liste requisitos como JSON array. Exemplo: [\"req1\", \"req2\"]"
    )
    print(f"Requisitos: {expand_response.content[:200]}...")

    # 2. DECOMPOSE
    print("\n[2/3] DECOMPOSE - Organizando em funções...")
    decompose_response = await client.generate(
        prompt=f'Requisitos: {expand_response.content}\n\nDecomponha em funções Python (formato JSON):',
        system='Liste funções como JSON. Exemplo: [{"signature": "def foo()", "description": "..."}]'
    )
    print(f"Funções: {decompose_response.content[:200]}...")

    # 3. GENERATE (uma função)
    print("\n[3/3] GENERATE - Implementando primeira função...")
    generate_response = await client.generate_code(
        specification="def validar_cpf(cpf: str) -> bool: Valida formato e dígitos verificadores de CPF",
        language="python",
    )
    print(f"Código gerado:")
    print("-" * 40)
    print(generate_response.content)
    print("-" * 40)

    print(f"\nTotal de chamadas ao CLI: {client.call_count}")


async def main():
    """Roda todos os testes."""
    print("\n" + "=" * 60)
    print("MDAP Agent - Testes com Claude CLI")
    print("=" * 60)
    print("\nUsando Claude Code CLI em modo headless")
    print("Não consome tokens da API!\n")

    # Testa se CLI está disponível
    import platform
    try:
        if platform.system() == "Windows":
            cmd = ["cmd", "/c", "claude", "--version"]
        else:
            cmd = ["claude", "--version"]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        print(f"Claude CLI: {stdout.decode().strip()}\n")
    except FileNotFoundError:
        print("ERRO: 'claude' CLI nao encontrado no PATH")
        print("Certifique-se que Claude Code esta instalado e no PATH")
        return

    # Roda testes
    await test_single_generation()
    await test_discriminator()
    await test_voting_simple()
    # await test_full_flow()  # Descomente para teste completo

    print("\n" + "=" * 60)
    print("TESTES CONCLUÍDOS")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
