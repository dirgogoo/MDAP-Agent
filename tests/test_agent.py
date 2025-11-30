"""
Tests for mdap/agent/ module
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from mdap.types import (
    Step, StepType, Context, ContextSnapshot, ExecutionResult,
    Language, MDAPConfig
)
from mdap.llm.client import LLMResponse
from mdap.agent.context import AgentContext, AgentMetrics
from mdap.agent.step import StepExecutor
from mdap.agent.loop import AgentLoop, agent_loop


class TestAgentMetrics:
    """Tests for AgentMetrics."""

    def test_initial_metrics(self):
        metrics = AgentMetrics()

        assert metrics.steps_total == 0
        assert metrics.tokens_total == 0
        assert metrics.errors_count == 0

    def test_tokens_total(self):
        metrics = AgentMetrics(
            tokens_input=100,
            tokens_output=50,
        )

        assert metrics.tokens_total == 150

    def test_duration(self):
        metrics = AgentMetrics()
        # Duration should be > 0 since start_time is set

        assert metrics.duration_seconds >= 0

    def test_to_dict(self):
        metrics = AgentMetrics(
            steps_total=10,
            tokens_input=500,
            tokens_output=300,
        )

        data = metrics.to_dict()

        assert data["steps_total"] == 10
        assert data["tokens"]["total"] == 800


class TestAgentContext:
    """Tests for AgentContext."""

    @pytest.fixture
    def agent_context(self, config):
        return AgentContext(
            task="Test task",
            language=Language.PYTHON,
            config=config,
        )

    def test_create_context(self, agent_context):
        assert agent_context.task == "Test task"
        assert agent_context.language == Language.PYTHON
        assert agent_context.is_complete is False

    def test_add_requirements(self, agent_context):
        agent_context.add_requirements(["Req 1", "Req 2"])

        assert len(agent_context.context.requirements) == 2

    def test_add_functions(self, agent_context):
        steps = [
            Step(type=StepType.GENERATE, signature="def foo()"),
            Step(type=StepType.GENERATE, signature="def bar()"),
        ]
        agent_context.add_functions(steps)

        assert len(agent_context.context.functions) == 2

    def test_add_generated_code(self, agent_context):
        step = Step(id="s1", type=StepType.GENERATE)
        agent_context.add_generated_code(step, "def foo(): pass")

        assert "s1" in agent_context.context.generated_code

    def test_add_execution_result(self, agent_context):
        step = Step(type=StepType.TEST)
        result = ExecutionResult(success=True, output="OK")

        agent_context.add_execution_result(step, result)

        assert len(agent_context.context.execution_results) == 1

    def test_add_failed_result_increments_errors(self, agent_context):
        step = Step(type=StepType.TEST)
        result = ExecutionResult(success=False, error="Failed")

        agent_context.add_execution_result(step, result)

        assert agent_context.metrics.errors_count == 1

    def test_mark_complete(self, agent_context):
        agent_context.mark_complete()

        assert agent_context.is_complete is True
        assert agent_context.metrics.end_time is not None

    def test_snapshot(self, agent_context):
        snapshot = agent_context.snapshot()

        assert isinstance(snapshot, ContextSnapshot)
        assert snapshot.task == "Test task"

    def test_record_step(self, agent_context):
        step = Step(type=StepType.GENERATE)
        agent_context.record_step(step)

        assert agent_context.metrics.steps_total == 1
        assert agent_context.metrics.steps_generate == 1

    def test_record_tokens(self, agent_context):
        agent_context.record_tokens(100, 50)

        assert agent_context.metrics.tokens_input == 100
        assert agent_context.metrics.tokens_output == 50

    def test_final_result(self, agent_context):
        step = Step(id="s1")
        agent_context.add_generated_code(step, "code")
        agent_context.add_requirements(["req1"])

        result = agent_context.final_result()

        assert result["task"] == "Test task"
        assert "req1" in result["requirements"]
        assert "s1" in result["code"]

    def test_get_log(self, agent_context):
        agent_context.add_requirements(["req"])

        log = agent_context.get_log()

        assert len(log) >= 1
        assert log[0]["event"] == "requirements_added"


class TestStepExecutor:
    """Tests for StepExecutor."""

    @pytest.fixture
    def executor(self, mock_client, config):
        return StepExecutor(mock_client, config)

    @pytest.fixture
    def agent_context(self, config):
        return AgentContext(
            task="Test",
            language=Language.PYTHON,
            config=config,
        )

    @pytest.mark.asyncio
    async def test_execute_done(self, executor, agent_context):
        """DONE step should mark context complete."""
        step = Step(type=StepType.DONE)

        result = await executor.execute(step, agent_context)

        assert result.success is True
        assert agent_context.is_complete is True

    @pytest.mark.asyncio
    async def test_execute_expand(self, executor, agent_context, mock_client):
        """EXPAND should call expander."""
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content='["Req 1", "Req 2"]',
            tokens_input=50,
            tokens_output=30,
            model="test",
            stop_reason="end_turn",
        ))

        step = Step(type=StepType.EXPAND)
        result = await executor.execute(step, agent_context)

        assert result.success is True
        assert len(agent_context.context.requirements) >= 1

    @pytest.mark.asyncio
    async def test_decide_next_expand_first(self, executor, agent_context):
        """Should expand first if no requirements."""
        next_step = await executor.decide_next(agent_context)

        assert next_step.type == StepType.EXPAND

    @pytest.mark.asyncio
    async def test_decide_next_decompose(self, executor, agent_context):
        """Should decompose after requirements."""
        agent_context.add_requirements(["Req 1"])

        next_step = await executor.decide_next(agent_context)

        assert next_step.type == StepType.DECOMPOSE

    @pytest.mark.asyncio
    async def test_decide_next_generate(self, executor, agent_context):
        """Should generate after decompose."""
        agent_context.add_requirements(["Req"])
        func = Step(id="f1", type=StepType.GENERATE, signature="def foo()")
        agent_context.add_functions([func])

        next_step = await executor.decide_next(agent_context)

        assert next_step.type == StepType.GENERATE
        assert next_step.id == "f1"

    @pytest.mark.asyncio
    async def test_decide_next_done(self, executor, agent_context):
        """Should be done when all implemented."""
        agent_context.add_requirements(["Req"])
        func = Step(id="f1", type=StepType.GENERATE)
        agent_context.add_functions([func])
        agent_context.add_generated_code(func, "code")

        next_step = await executor.decide_next(agent_context)

        assert next_step.type == StepType.DONE


class TestAgentLoop:
    """Tests for AgentLoop."""

    @pytest.fixture
    def mock_loop(self, mock_client, config):
        with patch('mdap.agent.loop.get_client', return_value=mock_client):
            with patch('mdap.agent.loop.init_all_tools'):
                return AgentLoop(client=mock_client, config=config)

    @pytest.mark.asyncio
    async def test_run_simple_task(self, mock_loop, mock_client):
        """Should complete simple task."""
        # Mock responses for expand, decompose, generate
        responses = [
            '["Req 1"]',  # expand
            '[{"signature": "def foo()", "description": "test", "dependencies": [], "requirements": [0]}]',  # decompose
            'def foo(): pass',  # generate
        ]
        response_idx = [0]

        async def mock_gen(*args, **kwargs):
            content = responses[min(response_idx[0], len(responses) - 1)]
            response_idx[0] += 1
            return LLMResponse(
                content=content,
                tokens_input=50,
                tokens_output=30,
                model="test",
                stop_reason="end_turn",
            )

        mock_client.generate = AsyncMock(side_effect=mock_gen)
        mock_client.compare_semantic = AsyncMock(return_value=True)

        context = await mock_loop.run(
            task="Create foo function",
            max_steps=10,
        )

        assert context.is_complete is True

    @pytest.mark.asyncio
    async def test_run_respects_max_steps(self, mock_loop, mock_client):
        """Should stop at max_steps."""
        # Mock to never complete
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content='["Req"]',
            tokens_input=50,
            tokens_output=30,
            model="test",
            stop_reason="end_turn",
        ))

        # Patch decide_next to always return EXPAND (never completes)
        with patch.object(
            mock_loop.executor,
            'decide_next',
            return_value=Step(type=StepType.EXPAND)
        ):
            context = await mock_loop.run(
                task="Test",
                max_steps=3,
            )

        assert context.metrics.steps_total <= 3

    @pytest.mark.asyncio
    async def test_callbacks(self, mock_loop, mock_client):
        """Should call registered callbacks."""
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content='["Req"]',
            tokens_input=50,
            tokens_output=30,
            model="test",
            stop_reason="end_turn",
        ))

        step_starts = []
        step_ends = []

        async def on_start(step):
            step_starts.append(step)

        async def on_end(step, success):
            step_ends.append((step, success))

        mock_loop.on_step_start(on_start)
        mock_loop.on_step_end(on_end)

        await mock_loop.run("Test", max_steps=2)

        assert len(step_starts) >= 1
        assert len(step_ends) >= 1

    @pytest.mark.asyncio
    async def test_decision_callback_can_stop(self, mock_loop, mock_client):
        """Decision callback can stop execution."""
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content='["Req"]',
            tokens_input=50,
            tokens_output=30,
            model="test",
            stop_reason="end_turn",
        ))

        async def stop_immediately(step):
            return False  # Don't continue

        mock_loop.on_decision(stop_immediately)

        context = await mock_loop.run("Test", max_steps=10)

        assert context.metrics.steps_total == 0


class TestAgentLoopHelper:
    """Tests for agent_loop helper function."""

    @pytest.mark.asyncio
    async def test_agent_loop_returns_dict(self, mock_client):
        """Helper should return result dict."""
        with patch('mdap.agent.loop.get_client', return_value=mock_client):
            with patch('mdap.agent.loop.init_all_tools'):
                mock_client.generate = AsyncMock(return_value=LLMResponse(
                    content='["Req"]',
                    tokens_input=50,
                    tokens_output=30,
                    model="test",
                    stop_reason="end_turn",
                ))
                mock_client.compare_semantic = AsyncMock(return_value=True)
                mock_client.close = AsyncMock()

                # Patch to complete immediately
                with patch('mdap.agent.step.StepExecutor.decide_next') as mock_decide:
                    mock_decide.return_value = Step(type=StepType.DONE)

                    result = await agent_loop("Test", max_steps=5)

                assert isinstance(result, dict)
                assert "task" in result
                assert "metrics" in result
