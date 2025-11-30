"""
Tests for mdap/decision/ module
"""
import pytest
from unittest.mock import AsyncMock, patch
import json

from mdap.types import Step, StepType, Context, Language, MDAPConfig
from mdap.llm.client import LLMResponse
from mdap.decision.expander import Expander
from mdap.decision.decomposer import Decomposer
from mdap.decision.generator import Generator
from mdap.decision.validator import Validator, ValidationResult
from mdap.decision.decider import Decider, Decision, DecisionType


class TestExpander:
    """Tests for Expander."""

    @pytest.fixture
    def expander(self, mock_client, config):
        return Expander(mock_client, config)

    @pytest.mark.asyncio
    async def test_expand_returns_requirements(self, expander, mock_client):
        """Should expand task into requirements."""
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content='["User can login", "Password validation", "Token generation"]',
            tokens_input=50,
            tokens_output=30,
            model="test",
            stop_reason="end_turn",
        ))

        requirements = await expander.expand(
            task="Create auth module",
            use_mdap=False,
        )

        assert len(requirements) == 3
        assert "User can login" in requirements

    @pytest.mark.asyncio
    async def test_expand_parses_markdown_list(self, expander, mock_client):
        """Should parse markdown list format."""
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content="- Requirement 1\n- Requirement 2\n- Requirement 3",
            tokens_input=50,
            tokens_output=30,
            model="test",
            stop_reason="end_turn",
        ))

        requirements = await expander.expand("task", use_mdap=False)

        assert len(requirements) == 3

    @pytest.mark.asyncio
    async def test_expand_parses_numbered_list(self, expander, mock_client):
        """Should parse numbered list format."""
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content="1. First requirement\n2. Second requirement",
            tokens_input=50,
            tokens_output=30,
            model="test",
            stop_reason="end_turn",
        ))

        requirements = await expander.expand("task", use_mdap=False)

        assert len(requirements) == 2


class TestDecomposer:
    """Tests for Decomposer."""

    @pytest.fixture
    def decomposer(self, mock_client, config):
        return Decomposer(mock_client, config)

    @pytest.mark.asyncio
    async def test_decompose_returns_steps(self, decomposer, mock_client):
        """Should decompose requirements into steps."""
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content=json.dumps([
                {
                    "signature": "def validate_email(email: str) -> bool",
                    "description": "Validate email format",
                    "dependencies": [],
                    "requirements": [0]
                },
                {
                    "signature": "def create_user(email: str, password: str) -> User",
                    "description": "Create new user",
                    "dependencies": ["validate_email"],
                    "requirements": [1]
                }
            ]),
            tokens_input=100,
            tokens_output=150,
            model="test",
            stop_reason="end_turn",
        ))

        steps = await decomposer.decompose(
            requirements=["Valid email", "Create user"],
            use_mdap=False,
        )

        assert len(steps) == 2
        assert steps[0].type == StepType.GENERATE
        assert "validate_email" in steps[0].signature

    @pytest.mark.asyncio
    async def test_decompose_fallback_parsing(self, decomposer, mock_client):
        """Should fallback to pattern matching if JSON fails."""
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content="def foo(x: int) -> int:\ndef bar(y: str) -> str:",
            tokens_input=50,
            tokens_output=30,
            model="test",
            stop_reason="end_turn",
        ))

        steps = await decomposer.decompose(["Req"], use_mdap=False)

        assert len(steps) >= 1


class TestGenerator:
    """Tests for Generator."""

    @pytest.fixture
    def generator(self, mock_client, config):
        return Generator(mock_client, config)

    @pytest.mark.asyncio
    async def test_generate_code(self, generator, mock_client, sample_step):
        """Should generate code for step."""
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content="def test_func(x: int) -> int:\n    return x * 2",
            tokens_input=50,
            tokens_output=30,
            model="test",
            stop_reason="end_turn",
        ))

        code = await generator.generate(
            step=sample_step,
            use_mdap=False,
        )

        assert "def test_func" in code
        assert "return x * 2" in code

    @pytest.mark.asyncio
    async def test_generate_cleans_markdown(self, generator, mock_client, sample_step):
        """Should remove markdown code blocks."""
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content="```python\ndef foo(): pass\n```",
            tokens_input=50,
            tokens_output=30,
            model="test",
            stop_reason="end_turn",
        ))

        code = await generator.generate(sample_step, use_mdap=False)

        assert "```" not in code
        assert "def foo" in code

    @pytest.mark.asyncio
    async def test_generate_removes_explanations(self, generator, mock_client, sample_step):
        """Should remove explanatory text."""
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content="Here's the function:\n\ndef foo():\n    pass",
            tokens_input=50,
            tokens_output=30,
            model="test",
            stop_reason="end_turn",
        ))

        code = await generator.generate(sample_step, use_mdap=False)

        assert "Here's" not in code
        assert "def foo" in code


class TestValidator:
    """Tests for Validator."""

    @pytest.fixture
    def validator(self, mock_client, config):
        return Validator(mock_client, config)

    @pytest.mark.asyncio
    async def test_validate_valid_code(self, validator, mock_client, sample_step):
        """Should pass valid code."""
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content="VALID: yes\nERRORS: []\nWARNINGS: []\nSUGGESTIONS: []",
            tokens_input=50,
            tokens_output=30,
            model="test",
            stop_reason="end_turn",
        ))

        result = await validator.validate(
            code="def foo(): return 1",
            step=sample_step,
        )

        assert result.is_valid is True
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_validate_syntax_error(self, validator, sample_step):
        """Should catch syntax errors."""
        result = await validator.validate(
            code="def broken(",
            step=sample_step,
        )

        assert result.is_valid is False
        assert any("syntax" in e.lower() for e in result.errors)

    @pytest.mark.asyncio
    async def test_validate_returns_warnings(self, validator, mock_client, sample_step):
        """Should return warnings from LLM."""
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content="VALID: yes\nERRORS: []\nWARNINGS: [No type hints]\nSUGGESTIONS: []",
            tokens_input=50,
            tokens_output=30,
            model="test",
            stop_reason="end_turn",
        ))

        result = await validator.validate(
            code="def foo(): return 1",
            step=sample_step,
        )

        assert result.is_valid is True
        assert len(result.warnings) >= 1


class TestValidationResult:
    """Tests for ValidationResult."""

    def test_passed_when_valid_no_errors(self):
        result = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=["Minor issue"],
            suggestions=[],
        )
        assert result.passed is True

    def test_not_passed_when_errors(self):
        result = ValidationResult(
            is_valid=True,
            errors=["Critical bug"],
            warnings=[],
            suggestions=[],
        )
        assert result.passed is False

    def test_not_passed_when_invalid(self):
        result = ValidationResult(
            is_valid=False,
            errors=[],
            warnings=[],
            suggestions=[],
        )
        assert result.passed is False


class TestDecider:
    """Tests for Decider."""

    @pytest.fixture
    def decider(self, mock_client, config):
        return Decider(mock_client, config)

    @pytest.mark.asyncio
    async def test_decide_expand(self, decider, mock_client, sample_snapshot):
        """Should decide to expand when no requirements."""
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content="ACTION: expand\nTARGET: requirements\nREASON: No requirements yet",
            tokens_input=50,
            tokens_output=30,
            model="test",
            stop_reason="end_turn",
        ))

        # Clear requirements
        sample_snapshot.requirements = []

        decision = await decider.decide(sample_snapshot, use_mdap=False)

        assert decision.type == DecisionType.EXPAND

    @pytest.mark.asyncio
    async def test_decide_done(self, decider, mock_client, sample_snapshot):
        """Should decide done when complete."""
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content="ACTION: done\nTARGET: \nREASON: All complete",
            tokens_input=50,
            tokens_output=30,
            model="test",
            stop_reason="end_turn",
        ))

        decision = await decider.decide(sample_snapshot, use_mdap=False)

        assert decision.type == DecisionType.DONE

    @pytest.mark.asyncio
    async def test_decide_from_options(self, decider, mock_client, sample_snapshot):
        """Should choose from predefined options."""
        mock_client.generate = AsyncMock(return_value=LLMResponse(
            content="1",
            tokens_input=50,
            tokens_output=5,
            model="test",
            stop_reason="end_turn",
        ))

        options = [
            Step(type=StepType.EXPAND, description="Expand"),
            Step(type=StepType.GENERATE, description="Generate"),
        ]

        chosen = await decider.decide_from_options(sample_snapshot, options)

        assert chosen == options[1]


class TestDecision:
    """Tests for Decision dataclass."""

    def test_create_decision(self):
        step = Step(type=StepType.GENERATE)
        decision = Decision(
            type=DecisionType.GENERATE,
            step=step,
            reason="Need to implement",
            confidence=0.9,
        )

        assert decision.type == DecisionType.GENERATE
        assert decision.confidence == 0.9
