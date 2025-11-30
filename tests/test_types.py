"""
Tests for mdap/types.py
"""
import pytest
from mdap.types import (
    Language, StepType, Step, Candidate, VoteResult,
    ExecutionResult, Context, ContextSnapshot, MDAPConfig
)


class TestLanguage:
    """Tests for Language enum."""

    def test_python_value(self):
        assert Language.PYTHON.value == "python"

    def test_typescript_value(self):
        assert Language.TYPESCRIPT.value == "typescript"


class TestStepType:
    """Tests for StepType enum."""

    def test_decision_types(self):
        """Decision types that use MDAP."""
        decision_types = [
            StepType.EXPAND,
            StepType.DECOMPOSE,
            StepType.GENERATE,
            StepType.VALIDATE,
            StepType.DECIDE,
        ]
        for st in decision_types:
            assert st.value in ["expand", "decompose", "generate", "validate", "decide"]

    def test_execution_types(self):
        """Execution types that don't use MDAP."""
        exec_types = [
            StepType.READ,
            StepType.SEARCH,
            StepType.TEST,
            StepType.APPLY,
        ]
        for st in exec_types:
            assert st.value in ["read", "search", "test", "apply"]


class TestStep:
    """Tests for Step dataclass."""

    def test_create_step(self):
        step = Step(
            type=StepType.GENERATE,
            description="Test function",
            signature="def test() -> None",
        )
        assert step.type == StepType.GENERATE
        assert step.description == "Test function"
        assert step.id  # Auto-generated

    def test_step_with_string_type(self):
        """Step should convert string type to enum."""
        step = Step(type="generate", description="Test")
        assert step.type == StepType.GENERATE

    def test_step_default_values(self):
        step = Step()
        assert step.type == StepType.DECIDE
        assert step.description == ""
        assert step.signature == ""


class TestCandidate:
    """Tests for Candidate dataclass."""

    def test_create_candidate(self):
        candidate = Candidate(
            code="def foo(): pass",
            tokens_used=10,
        )
        assert candidate.code == "def foo(): pass"
        assert candidate.is_valid is True
        assert candidate.id  # Auto-generated

    def test_candidate_hash(self):
        """Candidates should be hashable by id."""
        c1 = Candidate(id="abc", code="x")
        c2 = Candidate(id="abc", code="y")
        c3 = Candidate(id="def", code="x")

        assert hash(c1) == hash(c2)
        assert hash(c1) != hash(c3)

    def test_candidate_equality(self):
        c1 = Candidate(id="abc", code="x")
        c2 = Candidate(id="abc", code="y")
        c3 = Candidate(id="def", code="x")

        assert c1 == c2  # Same id
        assert c1 != c3  # Different id


class TestVoteResult:
    """Tests for VoteResult dataclass."""

    def test_winner_votes(self):
        winner = Candidate(id="w1", code="winner", group_id="group_0")
        result = VoteResult(
            winner=winner,
            votes_per_group={"group_0": 5, "group_1": 2},
            total_samples=7,
        )
        assert result.winner_votes == 5

    def test_winning_margin(self):
        winner = Candidate(id="w1", code="winner")
        result = VoteResult(
            winner=winner,
            winning_margin=3,
            total_samples=10,
        )
        assert result.winning_margin == 3


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_success_result(self):
        result = ExecutionResult(
            success=True,
            output="Done",
            data={"key": "value"},
        )
        assert result.success is True
        assert result.error is None

    def test_failure_result(self):
        result = ExecutionResult(
            success=False,
            error="Something went wrong",
        )
        assert result.success is False
        assert result.error == "Something went wrong"


class TestContext:
    """Tests for Context dataclass."""

    def test_create_context(self):
        ctx = Context(task="Build something")
        assert ctx.task == "Build something"
        assert ctx.language == Language.PYTHON
        assert ctx.is_complete is False

    def test_add_requirement(self):
        ctx = Context(task="Test")
        ctx.add_requirement("Req 1")
        ctx.add_requirement("Req 2")
        ctx.add_requirement("Req 1")  # Duplicate

        assert len(ctx.requirements) == 2
        assert "Req 1" in ctx.requirements

    def test_add_function(self):
        ctx = Context(task="Test")
        step = Step(type=StepType.GENERATE, signature="def foo()")
        ctx.add_function(step)

        assert len(ctx.functions) == 1

    def test_add_code(self):
        ctx = Context(task="Test")
        step = Step(id="s1", type=StepType.GENERATE)
        ctx.add_code(step, "def foo(): pass")

        assert "s1" in ctx.generated_code
        assert step in ctx.history

    def test_snapshot(self):
        ctx = Context(task="Test", requirements=["R1"])
        snapshot = ctx.snapshot()

        assert isinstance(snapshot, ContextSnapshot)
        assert snapshot.task == "Test"
        assert snapshot.requirements == ["R1"]

    def test_mark_complete(self):
        ctx = Context(task="Test")
        assert ctx.is_complete is False

        ctx.mark_complete()
        assert ctx.is_complete is True

    def test_final_result(self):
        ctx = Context(task="Test")
        step = Step(id="s1")
        ctx.add_code(step, "code1")

        result = ctx.final_result()
        assert result == {"s1": "code1"}


class TestContextSnapshot:
    """Tests for ContextSnapshot dataclass."""

    def test_to_prompt_context(self):
        snapshot = ContextSnapshot(
            task="Build auth module",
            requirements=["Login", "Logout"],
        )

        prompt = snapshot.to_prompt_context()

        assert "Build auth module" in prompt
        assert "Login" in prompt
        assert "Logout" in prompt


class TestMDAPConfig:
    """Tests for MDAPConfig dataclass."""

    def test_default_values(self):
        config = MDAPConfig()

        assert config.k == 3
        assert config.max_samples == 20
        assert config.max_tokens_response == 500
        assert config.temperature == 0.1
        assert "haiku" in config.model

    def test_custom_values(self):
        config = MDAPConfig(k=5, max_samples=10)

        assert config.k == 5
        assert config.max_samples == 10
