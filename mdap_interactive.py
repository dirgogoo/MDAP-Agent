#!/usr/bin/env python3
"""
MDAP Interactive - CLI Interativa com Checkpoints

Modo interativo do MDAP Agent com:
- Display em tempo real
- Checkpoints para validar decisoes
- Codigo com syntax highlight
- Controle do usuario em cada fase

Uso:
    python mdap_interactive.py "descricao da tarefa"

Exemplo:
    python mdap_interactive.py "Criar validador de CPF brasileiro"
"""

import asyncio
import sys
import json
import re
import time
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich import box

from mdap.types import Step, StepType, Language, MDAPConfig
from mdap.llm.client_cli import ClaudeCLIClient
from mdap.mdap.voter import Voter

from mdap_cli.events import EventBus, EventType
from mdap_cli.prompts import InteractivePrompt
from mdap_cli.code_view import render_code, print_code_block, CodeViewer


class MDAPInteractive:
    """
    MDAP Agent com interface interativa.

    Executa o pipeline EXPAND -> DECOMPOSE -> GENERATE
    com checkpoints para o usuario validar cada fase.
    """

    def __init__(self, config: MDAPConfig):
        self.config = config
        self.client = ClaudeCLIClient(config)
        self.voter = Voter(self.client, config)
        self.console = Console()
        self.prompt = InteractivePrompt(self.console)
        self.event_bus = EventBus()
        self.code_viewer = CodeViewer(self.console)
        self.call_count = 0
        self.start_time = time.time()

    def _emit(self, event_type: EventType, **data):
        """Emite evento"""
        self.event_bus.emit_simple(event_type, **data)

    def _elapsed(self) -> str:
        """Tempo decorrido"""
        seconds = int(time.time() - self.start_time)
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def _header(self, title: str):
        """Imprime header de fase"""
        self.console.print()
        self.console.print(Panel(
            f"[bold blue]{title}[/bold blue]",
            box=box.DOUBLE,
            border_style="blue"
        ))

    def _status(self, msg: str):
        """Imprime status"""
        self.console.print(f"[dim]{self._elapsed()}[/dim] {msg}")

    async def expand(self, tarefa: str) -> list[str]:
        """
        EXPAND: Descobre requisitos atomicos.
        Checkpoint para usuario aprovar/modificar.
        """
        self._header("FASE 1: EXPAND - Descobrindo Requisitos")
        self._status("Analisando tarefa...")

        prompt = f"Liste requisitos atomicos para: {tarefa}. Um por linha, numerados. Apenas a lista."
        resp = await self.client.generate(prompt)
        self.call_count += 1

        # Parse requisitos
        requisitos = []
        for linha in resp.content.split('\n'):
            linha = linha.strip()
            linha = re.sub(r'^[\d]+[.\)]\s*', '', linha)
            linha = re.sub(r'^[-*]\s*', '', linha)
            if linha and len(linha) > 5:
                requisitos.append(linha)

        requisitos = requisitos[:10]

        self._status(f"Encontrados {len(requisitos)} requisitos")

        # CHECKPOINT
        while True:
            action, data = self.prompt.ask_expand_approval(requisitos)

            if action == "continuar":
                break
            elif action == "adicionar" and data:
                requisitos.extend(data)
                self._status(f"Adicionados {len(data)} requisitos")
            elif action == "remover" and data:
                requisitos = [r for i, r in enumerate(requisitos) if i not in data]
                self._status(f"Removidos requisitos")
            elif action == "refazer":
                self._status("Refazendo EXPAND...")
                resp = await self.client.generate(prompt)
                self.call_count += 1
                requisitos = []
                for linha in resp.content.split('\n'):
                    linha = linha.strip()
                    linha = re.sub(r'^[\d]+[.\)]\s*', '', linha)
                    linha = re.sub(r'^[-*]\s*', '', linha)
                    if linha and len(linha) > 5:
                        requisitos.append(linha)
                requisitos = requisitos[:10]

        return requisitos

    async def decompose(self, requisitos: list[str]) -> list[str]:
        """
        DECOMPOSE: Organiza em funcoes.
        Checkpoint para usuario aprovar/modificar.
        """
        self._header("FASE 2: DECOMPOSE - Planejando Funcoes")
        self._status("Organizando requisitos em funcoes...")

        reqs_texto = "; ".join(requisitos[:5])
        prompt = f"Crie 5 funcoes Python para: {reqs_texto}. Responda APENAS com assinaturas, uma por linha. Exemplo: def criar_usuario(nome: str, email: str) -> dict"
        resp = await self.client.generate(prompt)
        self.call_count += 1

        # Parse funcoes
        funcoes = []
        templates = {'def nome', 'def funcao', 'def exemplo', 'def function'}

        for linha in resp.content.split('\n'):
            linha = linha.strip()
            match = re.search(r'(def\s+[a-z_][a-z0-9_]*\s*\([^)]*\)\s*(?:->\s*[\w\[\],\s]+)?)', linha, re.IGNORECASE)
            if match:
                sig = match.group(1).strip().rstrip(':')
                if not any(t in sig.lower() for t in templates):
                    funcoes.append(sig)

        funcoes = funcoes[:8]

        self._status(f"Planejadas {len(funcoes)} funcoes")

        # CHECKPOINT
        while True:
            action, data = self.prompt.ask_decompose_approval(funcoes)

            if action == "continuar":
                break
            elif action == "adicionar" and data:
                funcoes.append(data)
                self._status(f"Adicionada funcao: {data}")
            elif action == "remover" and isinstance(data, int):
                removed = funcoes.pop(data)
                self._status(f"Removida funcao: {removed}")
            elif action == "renomear" and data:
                idx, nova = data
                funcoes[idx] = nova
                self._status(f"Renomeada funcao")
            elif action == "refazer":
                self._status("Refazendo DECOMPOSE...")
                resp = await self.client.generate(prompt)
                self.call_count += 1
                funcoes = []
                for linha in resp.content.split('\n'):
                    linha = linha.strip()
                    match = re.search(r'(def\s+[a-z_][a-z0-9_]*\s*\([^)]*\)\s*(?:->\s*[\w\[\],\s]+)?)', linha, re.IGNORECASE)
                    if match:
                        sig = match.group(1).strip().rstrip(':')
                        if not any(t in sig.lower() for t in templates):
                            funcoes.append(sig)
                funcoes = funcoes[:8]

        return funcoes

    async def generate(self, funcao: str) -> tuple[str, dict]:
        """
        GENERATE: Implementa funcao com votacao MDAP.
        Retorna (codigo, info_votacao)
        """
        self._status(f"Gerando: {funcao[:50]}...")

        step = Step(
            type=StepType.GENERATE,
            signature=funcao,
            description=f"Implementar {funcao}",
        )

        async def gen(s, ctx):
            return await self.client.generate_code(f'{s.signature}: {s.description}')

        votacao_info = {}
        try:
            result = await self.voter.vote(step, '', gen, Language.PYTHON)
            self.call_count += 1
            codigo = result.winner.code
            votacao_info = {
                "samples": result.total_samples,
                "grupos": len(result.groups),
                "votos": result.votes_per_group,
                "margem": result.winning_margin,
            }
        except ValueError as e:
            self._status(f"Votacao falhou, gerando direto...")
            resp = await self.client.generate_code(f'{funcao}: implementar esta funcao')
            self.call_count += 1
            codigo = resp.code if hasattr(resp, 'code') else str(resp)
            votacao_info = {"samples": 1, "grupos": 1, "votos": {"fallback": 1}, "margem": 0}

        return codigo, votacao_info

    async def run(self, tarefa: str) -> dict:
        """
        Executa pipeline completo com checkpoints interativos.
        """
        self.start_time = time.time()

        # Header inicial
        self.console.print()
        self.console.print(Panel(
            f"[bold blue]MDAP Interactive[/bold blue]\n\n"
            f"[white]Tarefa:[/white] {tarefa}\n"
            f"[dim]Config: k={self.config.k}, max_samples={self.config.max_samples}[/dim]",
            box=box.DOUBLE,
            border_style="blue"
        ))

        resultado = {
            "tarefa": tarefa,
            "config": {"k": self.config.k, "max_samples": self.config.max_samples},
            "requisitos": [],
            "funcoes": [],
            "codigos": {},
            "metricas": {
                "inicio": datetime.now().isoformat(),
                "votacoes": [],
                "chamadas_cli": 0,
            }
        }

        # ============ FASE 1: EXPAND ============
        requisitos = await self.expand(tarefa)
        resultado["requisitos"] = requisitos

        if not requisitos:
            self.prompt.show_error("Nenhum requisito encontrado")
            return resultado

        # ============ FASE 2: DECOMPOSE ============
        funcoes = await self.decompose(requisitos)
        resultado["funcoes"] = funcoes

        if not funcoes:
            self.prompt.show_error("Nenhuma funcao planejada")
            return resultado

        # ============ FASE 3: GENERATE ============
        self._header("FASE 3: GENERATE - Implementando com MDAP")

        for i, funcao in enumerate(funcoes, 1):
            self._status(f"[{i}/{len(funcoes)}] Gerando codigo...")

            while True:
                codigo, votacao_info = await self.generate(funcao)
                resultado["metricas"]["votacoes"].append(votacao_info)

                # CHECKPOINT
                action, data = self.prompt.ask_generate_approval(
                    funcao, codigo, votacao_info
                )

                if action == "continuar":
                    resultado["codigos"][funcao] = codigo
                    self.code_viewer.add_code(funcao, codigo)
                    break
                elif action == "regenerar":
                    self._status("Regenerando...")
                    continue
                elif action == "editar" and data:
                    resultado["codigos"][funcao] = data
                    self.code_viewer.add_code(funcao, data)
                    break
                elif action == "pular":
                    self._status("Funcao pulada")
                    break

        # ============ RESULTADO FINAL ============
        resultado["metricas"]["chamadas_cli"] = self.call_count
        resultado["metricas"]["fim"] = datetime.now().isoformat()
        resultado["metricas"]["tempo_total"] = self._elapsed()

        # Checkpoint final
        self._header("RESULTADO FINAL")

        if self.prompt.ask_final_approval(resultado):
            # Mostra codigo completo
            self.prompt.show_code_preview(resultado["codigos"])

            # Salva
            with open("mdap_resultado.json", "w", encoding="utf-8") as f:
                json.dump(resultado, f, indent=2, ensure_ascii=False)

            self.prompt.show_success(f"Salvo em mdap_resultado.json")

            # Pergunta se quer exportar codigo
            if self.prompt.ask_continue("Exportar codigo para arquivo .py?"):
                self.code_viewer.export_to_file("mdap_codigo_gerado.py")

        return resultado


async def main_async(tarefa: str, k: int = 2, max_samples: int = 5):
    """Executa MDAP interativo"""
    config = MDAPConfig(k=k, max_samples=max_samples)
    agent = MDAPInteractive(config)
    return await agent.run(tarefa)


def main():
    if len(sys.argv) < 2:
        console = Console()
        console.print(Panel(
            "[bold]MDAP Interactive[/bold]\n\n"
            "CLI interativa para geracao de codigo com MDAP.\n\n"
            "[bold]Uso:[/bold]\n"
            "  python mdap_interactive.py \"descricao da tarefa\" [k] [max_samples]\n\n"
            "[bold]Exemplos:[/bold]\n"
            "  python mdap_interactive.py \"Criar validador de CPF brasileiro\"\n"
            "  python mdap_interactive.py \"Criar API REST para usuarios\" 3 10\n\n"
            "[bold]Features:[/bold]\n"
            "  - Checkpoints interativos em cada fase\n"
            "  - Codigo com syntax highlight\n"
            "  - Regenerar/editar codigo\n"
            "  - Exportar para arquivo",
            title="Ajuda",
            border_style="blue"
        ))
        sys.exit(0)

    tarefa = sys.argv[1]
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    max_samples = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    asyncio.run(main_async(tarefa, k, max_samples))


if __name__ == "__main__":
    main()
