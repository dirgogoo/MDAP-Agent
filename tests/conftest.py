"""
Pytest configuration and fixtures for MDAP Agent tests.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

# Add parent to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mdap.types import (
    Step, StepType, Candidate, VoteResult, Context,
    ContextSnapshot, ExecutionResult, Language, MDAPConfig
)
from mdap.llm.client import ClaudeClient, LLMResponse


# --- Event Loop ---

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# --- Mock LLM Client ---

@pytest.fixture
def mock_llm_response():
    """Factory for mock LLM responses."""
    def _create(content: str, tokens_input: int = 100, tokens_output: int = 50):
        return LLMResponse(
            content=content,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            model="claude-3-haiku-20240307",
            stop_reason="end_turn",
        )
    return _create


@pytest.fixture
def mock_client(mock_llm_response):
    """Mock Claude client."""
    client = MagicMock(spec=ClaudeClient)
    client.config = MDAPConfig()

    # Default response
    async def mock_generate(*args, **kwargs):
        return mock_llm_response("def example(): pass")

    client.generate = AsyncMock(side_effect=mock_generate)
    client.generate_code = AsyncMock(side_effect=mock_generate)
    client.compare_semantic = AsyncMock(return_value=True)
    client.close = AsyncMock()

    return client


# --- Config Fixtures ---

@pytest.fixture
def config():
    """Default MDAP config for tests."""
    return MDAPConfig(
        k=2,  # Lower k for faster tests
        max_samples=5,
        max_tokens_response=200,
        temperature=0.1,
        model="claude-3-haiku-20240307",
    )


# --- Type Fixtures ---

@pytest.fixture
def sample_step():
    """Sample step for testing."""
    return Step(
        id="test-step-1",
        type=StepType.GENERATE,
        description="Test function",
        signature="def test_func(x: int) -> int",
        context="# Test context",
    )


@pytest.fixture
def sample_candidate():
    """Sample candidate for testing."""
    return Candidate(
        id="test-candidate-1",
        code="def test_func(x: int) -> int:\n    return x * 2",
        tokens_used=50,
        is_valid=True,
    )


@pytest.fixture
def sample_context():
    """Sample context for testing."""
    return Context(
        task="Create a test module",
        language=Language.PYTHON,
        requirements=["Requirement 1", "Requirement 2"],
    )


@pytest.fixture
def sample_snapshot(sample_context):
    """Sample context snapshot for testing."""
    return sample_context.snapshot()


# --- Temp Files ---

@pytest.fixture
def temp_dir(tmp_path):
    """Temporary directory for file tests."""
    return tmp_path


@pytest.fixture
def temp_python_file(temp_dir):
    """Create a temporary Python file."""
    file_path = temp_dir / "test_module.py"
    file_path.write_text('''
def hello():
    """Say hello."""
    return "Hello, World!"

def add(a, b):
    """Add two numbers."""
    return a + b

class Calculator:
    """Simple calculator."""
    def multiply(self, a, b):
        return a * b
''')
    return file_path


# --- Helper Functions ---

def create_candidates(codes: list[str]) -> list[Candidate]:
    """Create list of candidates from code strings."""
    return [
        Candidate(
            id=f"candidate-{i}",
            code=code,
            tokens_used=len(code) // 4,
            is_valid=True,
        )
        for i, code in enumerate(codes)
    ]


# Make helper available
@pytest.fixture
def candidate_factory():
    """Factory to create candidates."""
    return create_candidates
