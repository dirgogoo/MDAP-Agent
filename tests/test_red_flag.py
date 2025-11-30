"""
Tests for mdap/mdap/red_flag.py
"""
import pytest
from mdap.types import Candidate, MDAPConfig, Language
from mdap.mdap.red_flag import RedFlagFilter, RedFlagResult, quick_check


class TestRedFlagFilter:
    """Tests for RedFlagFilter."""

    @pytest.fixture
    def filter(self):
        config = MDAPConfig(max_tokens_response=100)
        return RedFlagFilter(config)

    def test_valid_python_code(self, filter):
        """Valid Python code should pass."""
        candidate = Candidate(
            code="def hello():\n    return 'world'",
            tokens_used=20,
        )
        result = filter.check(candidate, Language.PYTHON)

        assert result.passed is True
        assert result.checks.get("syntax") is True

    def test_invalid_python_syntax(self, filter):
        """Invalid Python syntax should fail."""
        candidate = Candidate(
            code="def hello(\n    return",  # Syntax error
            tokens_used=20,
        )
        result = filter.check(candidate, Language.PYTHON)

        assert result.passed is False
        assert "syntax" in result.reason.lower()

    def test_too_long_response(self, filter):
        """Response exceeding token limit should fail."""
        candidate = Candidate(
            code="x = 1",
            tokens_used=200,  # Exceeds limit of 100
        )
        result = filter.check(candidate, Language.PYTHON)

        assert result.passed is False
        assert "too long" in result.reason.lower()

    def test_empty_code(self, filter):
        """Empty code should fail."""
        candidate = Candidate(code="", tokens_used=0)
        result = filter.check(candidate, Language.PYTHON)

        assert result.passed is False
        assert "empty" in result.reason.lower()

    def test_too_short_code(self, filter):
        """Very short code should fail."""
        candidate = Candidate(code="x", tokens_used=1)
        result = filter.check(candidate, Language.PYTHON)

        assert result.passed is False

    def test_explanation_instead_of_code(self, filter):
        """Explanatory text should fail."""
        explanations = [
            "Here's the function you requested:",
            "I'll create a function that...",
            "This function will handle...",
            "The following code implements...",
        ]

        for text in explanations:
            candidate = Candidate(code=text, tokens_used=20)
            result = filter.check(candidate, Language.PYTHON)
            assert result.passed is False, f"Should reject: {text}"

    def test_code_in_markdown_block(self, filter):
        """Code in markdown block should be extracted and validated."""
        candidate = Candidate(
            code="```python\ndef hello():\n    return 'world'\n```",
            tokens_used=30,
        )
        result = filter.check(candidate, Language.PYTHON)

        assert result.passed is True

    def test_typescript_basic_check(self, filter):
        """TypeScript should pass basic bracket check."""
        candidate = Candidate(
            code="function hello(): string { return 'world'; }",
            tokens_used=20,
        )
        result = filter.check(candidate, Language.TYPESCRIPT)

        assert result.passed is True

    def test_typescript_unbalanced_brackets(self, filter):
        """TypeScript with unbalanced brackets should fail."""
        candidate = Candidate(
            code="function hello() { return 'world';",  # Missing }
            tokens_used=20,
        )
        result = filter.check(candidate, Language.TYPESCRIPT)

        assert result.passed is False
        assert "bracket" in result.reason.lower()

    def test_disabled_checks(self):
        """Checks can be disabled in config."""
        config = MDAPConfig(
            enable_syntax_check=False,
            enable_length_check=False,
            enable_format_check=False,
        )
        filter = RedFlagFilter(config)

        # This would normally fail syntax check
        candidate = Candidate(
            code="def broken(",
            tokens_used=10,
        )
        result = filter.check(candidate, Language.PYTHON)

        # With all checks disabled, it should pass
        assert result.passed is True


class TestQuickCheck:
    """Tests for quick_check helper function."""

    def test_quick_check_valid(self):
        code = "def add(a, b):\n    return a + b"
        assert quick_check(code) is True

    def test_quick_check_invalid(self):
        code = "def broken syntax"
        assert quick_check(code) is False

    def test_quick_check_with_language(self):
        ts_code = "const x: number = 5;"
        assert quick_check(ts_code, Language.TYPESCRIPT) is True

    def test_quick_check_custom_max_tokens(self):
        code = "result = 42"  # ~11 chars, enough to pass format check
        assert quick_check(code, max_tokens=10) is True


class TestRedFlagResult:
    """Tests for RedFlagResult dataclass."""

    def test_passed_result(self):
        result = RedFlagResult(
            passed=True,
            checks={"syntax": True, "length": True},
        )
        assert result.passed is True
        assert result.reason is None

    def test_failed_result(self):
        result = RedFlagResult(
            passed=False,
            reason="Code too long",
            checks={"length": False},
        )
        assert result.passed is False
        assert result.reason == "Code too long"
