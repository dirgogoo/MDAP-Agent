#!/usr/bin/env python3
"""
MDAP Runner - Agent Loop Dinamico com Chamadas Aninhadas

Implementa o plano original:
- Loop dinamico que decide proximo passo
- Separacao DECISAO (MDAP) vs EXECUCAO (deterministico)
- Chamadas aninhadas: funcao pode gerar sub-funcoes
- Contexto acumulado

Uso:
    python mdap_runner.py "descricao da tarefa"

Exemplo:
    python mdap_runner.py "Criar validador de CPF brasileiro"
"""
import asyncio
import sys
import json
import re
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Callable, Any
from enum import Enum

sys.path.insert(0, 'C:/Users/conta/experiment-01/mdap-agent')

from mdap.types import Step, StepType, Language, MDAPConfig
from mdap.llm.client_cli import ClaudeCLIClient
from mdap.mdap.voter import Voter


class StepAction(Enum):
    """Tipos de passos no agent loop"""
    EXPAND = "expand"        # Descobrir requisitos (MDAP)
    DECOMPOSE = "decompose"  # Organizar em funcoes (MDAP)
    GENERATE = "generate"    # Implementar codigo (MDAP)
    VALIDATE = "validate"    # Verificar correcao (MDAP)
    READ = "read"           # Ler arquivo (deterministico)
    SEARCH = "search"       # Buscar codigo (deterministico)
    TEST = "test"           # Rodar testes (deterministico)
    DONE = "done"           # Tarefa completa


@dataclass
class AgentStep:
    """Um passo do agent"""
    action: StepAction
    target: str
    context: str = ""
    result: Any = None
    sub_steps: list = field(default_factory=list)


@dataclass
class AgentContext:
    """Contexto acumulado do agent"""
    task: str
    requisitos: list = field(default_factory=list)
    funcoes: list = field(default_factory=list)
    codigos: dict = field(default_factory=dict)
    steps_history: list = field(default_factory=list)
    depth: int = 0
    max_depth: int = 3

    def snapshot(self) -> str:
        """Retorna snapshot do contexto para votacao"""
        return json.dumps({
            "task": self.task,
            "requisitos": self.requisitos,
            "funcoes": self.funcoes,
            "codigos_gerados": list(self.codigos.keys()),
            "depth": self.depth
        }, indent=2)

    def is_complete(self) -> bool:
        """Verifica se tarefa esta completa"""
        return (
            len(self.requisitos) > 0 and
            len(self.funcoes) > 0 and
            len(self.codigos) >= len(self.funcoes)
        )


class MDAPAgentLoop:
    """Agent Loop Dinamico com MDAP"""

    def __init__(self, config: MDAPConfig):
        self.config = config
        self.client = ClaudeCLIClient(config)
        self.voter = Voter(self.client, config)
        self.call_count = 0

    async def decide_next_step(self, context: AgentContext) -> AgentStep:
        """
        DECISAO: Qual proximo passo? (com MDAP)
        Analisa contexto e decide dinamicamente o que fazer.
        """
        # Contar tentativas de decompose para evitar loop infinito
        decompose_attempts = sum(1 for s in context.steps_history if s.action == StepAction.DECOMPOSE)

        # Logica de decisao baseada no estado atual
        if not context.requisitos:
            return AgentStep(action=StepAction.EXPAND, target=context.task)

        if not context.funcoes:
            if decompose_attempts >= 3:
                # Fallback: criar funcao generica se decompose falhar
                self._log("WARN: DECOMPOSE falhou 3x, criando funcao padrao", context.depth)
                context.funcoes.append(f"def processar_{context.task.split()[0].lower()}(dados: dict) -> dict")
            return AgentStep(action=StepAction.DECOMPOSE, target=str(context.requisitos))

        # Verificar quais funcoes ainda faltam implementar
        funcoes_pendentes = [
            f for f in context.funcoes
            if f not in context.codigos
        ]

        if funcoes_pendentes:
            # Pegar proxima funcao pendente
            proxima = funcoes_pendentes[0]
            return AgentStep(action=StepAction.GENERATE, target=proxima)

        # Tudo pronto
        return AgentStep(action=StepAction.DONE, target="")

    async def expand(self, target: str, context: AgentContext) -> list[str]:
        """
        EXPAND: Descobre requisitos atomicos (MDAP)
        Pode ser chamado recursivamente para sub-requisitos.
        """
        self._log(f"EXPAND: {target[:50]}...", context.depth)

        prompt = f"Liste requisitos atomicos para: {target}. Um por linha, numerados. Apenas a lista."
        resp = await self.client.generate(prompt)
        self.call_count += 1

        requisitos = []
        for linha in resp.content.split('\n'):
            linha = linha.strip()
            linha = re.sub(r'^[\d]+[.\)]\s*', '', linha)
            linha = re.sub(r'^[-*]\s*', '', linha)
            if linha and len(linha) > 5:
                requisitos.append(linha)

        self._log(f"  -> {len(requisitos)} requisitos encontrados", context.depth)
        return requisitos[:10]

    async def decompose(self, requisitos: list[str], context: AgentContext) -> list[str]:
        """
        DECOMPOSE: Organiza em funcoes (MDAP)
        Pode descobrir que uma funcao precisa de sub-funcoes.
        """
        self._log(f"DECOMPOSE: {len(requisitos)} requisitos", context.depth)

        reqs_texto = "; ".join(requisitos[:5])  # Limite para prompt
        prompt = f"Crie 5 funcoes Python para: {reqs_texto}. Responda APENAS com assinaturas, uma por linha. Exemplo: def criar_usuario(nome: str, email: str) -> dict"
        resp = await self.client.generate(prompt)
        self.call_count += 1

        funcoes = []
        # Templates genericos para ignorar
        templates = {'def nome', 'def funcao', 'def exemplo', 'def function'}

        for linha in resp.content.split('\n'):
            linha = linha.strip()
            match = re.search(r'(def\s+[a-z_][a-z0-9_]*\s*\([^)]*\)\s*(?:->\s*[\w\[\],\s]+)?)', linha, re.IGNORECASE)
            if match:
                sig = match.group(1).strip().rstrip(':')
                # Ignora templates genericos
                if not any(t in sig.lower() for t in templates):
                    funcoes.append(sig)

        self._log(f"  -> {len(funcoes)} funcoes planejadas", context.depth)
        return funcoes[:8]  # Aumentei para 8 funcoes max

    async def generate_with_mdap(self, funcao: str, context: AgentContext) -> str:
        """
        GENERATE: Implementa funcao com votacao MDAP
        Se detectar funcao complexa, pode chamar decompose recursivamente.
        """
        self._log(f"GENERATE (MDAP): {funcao[:60]}...", context.depth)

        step = Step(
            type=StepType.GENERATE,
            signature=funcao,
            description=f"Implementar {funcao}",
        )

        async def gen(s, ctx):
            return await self.client.generate_code(f'{s.signature}: {s.description}')

        votacao_info = None
        try:
            result = await self.voter.vote(step, context.snapshot(), gen, Language.PYTHON)
            self.call_count += 1
            codigo = result.winner.code
            votacao_info = f"samples={result.total_samples}, grupos={len(result.groups)}, votos={result.votes_per_group}"
        except ValueError as e:
            # Fallback: gerar sem votacao se voter falhar
            self._log(f"  WARN: Votacao falhou, gerando direto", context.depth)
            resp = await self.client.generate_code(f'{funcao}: implementar esta funcao')
            self.call_count += 1
            codigo = resp.code if hasattr(resp, 'code') else str(resp)

        # Verificar se o codigo gerado chama funcoes que nao existem
        sub_funcoes = self._detectar_sub_funcoes(codigo, context)

        if sub_funcoes and context.depth < context.max_depth:
            self._log(f"  -> Detectadas {len(sub_funcoes)} sub-funcoes necessarias", context.depth)
            # Chamada aninhada: gerar sub-funcoes primeiro
            for sub_func in sub_funcoes:
                if sub_func not in context.codigos:
                    context.depth += 1
                    sub_codigo = await self.generate_with_mdap(sub_func, context)
                    context.codigos[sub_func] = sub_codigo
                    context.depth -= 1

        if votacao_info:
            self._log(f"  -> Votacao: {votacao_info}", context.depth)
        else:
            self._log(f"  -> Gerado (fallback, sem votacao)", context.depth)

        return codigo

    def _detectar_sub_funcoes(self, codigo: str, context: AgentContext) -> list[str]:
        """Detecta chamadas a funcoes que nao existem ainda"""
        # Procura por chamadas de funcao (ignora metodos com . antes)
        # (?<!\.) = negative lookbehind para ignorar .metodo()
        pattern = r'(?<![.\w])([a-z_][a-z0-9_]*)\s*\('
        chamadas = re.findall(pattern, codigo, re.IGNORECASE)

        # Filtra built-ins e funcoes ja existentes
        builtins = {'print', 'len', 'str', 'int', 'float', 'bool', 'list', 'dict', 'set',
                    'range', 'enumerate', 'zip', 'map', 'filter', 'sum', 'min', 'max',
                    'abs', 'round', 'sorted', 'reversed', 'any', 'all', 'isinstance',
                    'type', 'open', 'input', 'format'}

        funcoes_existentes = set(context.codigos.keys())
        funcoes_planejadas = set(context.funcoes)

        # Funcoes que precisam ser geradas
        novas = []
        for chamada in chamadas:
            if chamada not in builtins:
                # Verifica se nao esta nas funcoes existentes
                existe = any(chamada in f for f in funcoes_existentes)
                planejada = any(chamada in f for f in funcoes_planejadas)
                if not existe and not planejada:
                    sig = f"def {chamada}()"  # Assinatura basica
                    if sig not in novas:
                        novas.append(sig)

        return novas[:3]  # Maximo 3 sub-funcoes

    async def validate(self, codigo: str, context: AgentContext) -> bool:
        """VALIDATE: Verifica correcao (MDAP)"""
        self._log(f"VALIDATE: verificando codigo", context.depth)

        # Por ora, apenas verifica se parseia
        try:
            compile(codigo, '<string>', 'exec')
            return True
        except SyntaxError:
            return False

    async def run(self, task: str) -> dict:
        """
        Loop principal do agent.
        Decide dinamicamente o proximo passo ate completar.
        """
        context = AgentContext(task=task)
        max_iterations = 20
        iteration = 0

        print(f"\n{'='*60}")
        print(f"[MDAP] AGENT LOOP DINAMICO")
        print(f"{'='*60}")
        print(f"[MDAP] Tarefa: {task}")
        print(f"[MDAP] Config: k={self.config.k}, max_samples={self.config.max_samples}")
        print()

        while iteration < max_iterations:
            iteration += 1

            # DECISAO: Qual proximo passo?
            step = await self.decide_next_step(context)
            context.steps_history.append(step)

            print(f"[MDAP] [{iteration}] {step.action.value.upper()}")

            if step.action == StepAction.DONE:
                print(f"[MDAP] Tarefa completa!")
                break

            elif step.action == StepAction.EXPAND:
                requisitos = await self.expand(step.target, context)
                context.requisitos.extend(requisitos)

            elif step.action == StepAction.DECOMPOSE:
                funcoes = await self.decompose(context.requisitos, context)
                context.funcoes.extend(funcoes)

            elif step.action == StepAction.GENERATE:
                codigo = await self.generate_with_mdap(step.target, context)
                context.codigos[step.target] = codigo

            print()

        # Resultado final
        resultado = {
            "tarefa": task,
            "config": {"k": self.config.k, "max_samples": self.config.max_samples},
            "requisitos": context.requisitos,
            "funcoes": context.funcoes,
            "codigos": context.codigos,
            "metricas": {
                "iterations": iteration,
                "steps": [s.action.value for s in context.steps_history],
                "chamadas_cli": self.call_count,
                "timestamp": datetime.now().isoformat()
            }
        }

        print(f"{'='*60}")
        print(f"[MDAP] RESULTADO FINAL")
        print(f"{'='*60}")
        print(f"[MDAP] Requisitos: {len(resultado['requisitos'])}")
        print(f"[MDAP] Funcoes: {len(resultado['funcoes'])}")
        print(f"[MDAP] Codigos: {len(resultado['codigos'])}")
        print(f"[MDAP] Iterations: {iteration}")
        print(f"[MDAP] Chamadas CLI: {self.call_count}")
        print()

        # Mostra codigo gerado
        print(f"{'='*60}")
        print(f"[MDAP] CODIGO GERADO")
        print(f"{'='*60}")
        for sig, codigo in resultado['codigos'].items():
            print(f"\n# {sig}")
            print(codigo)

        return resultado

    def _log(self, msg: str, depth: int = 0):
        """Log com indentacao baseada na profundidade"""
        indent = "  " * depth
        print(f"[MDAP] {indent}{msg}")


async def main_async(tarefa: str, k: int = 2, max_samples: int = 5):
    """Executa o agent loop"""
    config = MDAPConfig(k=k, max_samples=max_samples)
    agent = MDAPAgentLoop(config)
    return await agent.run(tarefa)


def main():
    if len(sys.argv) < 2:
        print("MDAP Runner - Agent Loop Dinamico")
        print("")
        print("Uso:")
        print("  python mdap_runner.py \"descricao da tarefa\" [k] [max_samples]")
        print("")
        print("Exemplos:")
        print("  python mdap_runner.py \"Criar validador de CPF brasileiro\"")
        print("  python mdap_runner.py \"Criar modulo de autenticacao JWT\"")
        print("  python mdap_runner.py \"Criar funcoes para manipular listas\" 3 10")
        print("")
        print("Caracteristicas:")
        print("  - Loop dinamico: decide proximo passo automaticamente")
        print("  - Chamadas aninhadas: funcao complexa gera sub-funcoes")
        print("  - Separacao Decisao/Execucao: MDAP para decisoes")
        print("  - Contexto acumulado: cada passo atualiza estado")
        sys.exit(1)

    tarefa = sys.argv[1]
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    max_samples = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    resultado = asyncio.run(main_async(tarefa, k, max_samples))

    # Salva resultado
    with open("mdap_resultado.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)
    print(f"\n[MDAP] Resultado salvo em: mdap_resultado.json")


if __name__ == "__main__":
    main()
