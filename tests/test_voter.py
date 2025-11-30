"""
Tests for mdap/mdap/voter.py
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mdap.types import Step, StepType, Candidate, Language, MDAPConfig
from mdap.llm.client import LLMResponse
from mdap.mdap.voter import Voter, VotingSession, first_to_ahead_by_k


class TestVotingSession:
    """Tests for VotingSession."""

    def test_create_session(self, sample_step):
        session = VotingSession(
            step=sample_step,
            context="test context",
        )

        assert session.step == sample_step
        assert session.is_complete is False
        assert len(session.samples) == 0

    def test_session_tracking(self, sample_step):
        session = VotingSession(step=sample_step, context="")

        valid = Candidate(id="v1", code="valid", is_valid=True)
        invalid = Candidate(id="i1", code="invalid", is_valid=False)

        session.samples.append(valid)
        session.samples.append(invalid)
        session.valid_samples.append(valid)
        session.invalid_samples.append(invalid)

        assert len(session.samples) == 2
        assert len(session.valid_samples) == 1
        assert len(session.invalid_samples) == 1


class TestVoter:
    """Tests for Voter."""

    @pytest.fixture
    def voter(self, mock_client, config):
        return Voter(mock_client, config)

    @pytest.fixture
    def mock_generator(self, mock_llm_response):
        """Mock generator function."""
        async def generator(step, context):
            return mock_llm_response("def test(): return 42")
        return generator

    @pytest.mark.asyncio
    async def test_vote_finds_winner(self, voter, mock_client, sample_step):
        """Vote should find winner with k margin."""
        # Setup: All responses are equivalent
        mock_client.compare_semantic = AsyncMock(return_value=True)

        call_count = [0]

        async def mock_gen(step, ctx):
            call_count[0] += 1
            return LLMResponse(
                content=f"def test(): return {call_count[0]}",
                tokens_input=10,
                tokens_output=20,
                model="test",
                stop_reason="end_turn",
            )

        result = await voter.vote(
            step=sample_step,
            context="test",
            generator=mock_gen,
            language=Language.PYTHON,
            k=2,
        )

        assert result.winner is not None
        assert result.total_samples >= 2

    @pytest.mark.asyncio
    async def test_vote_respects_max_samples(self, voter, mock_client, sample_step):
        """Vote should stop at max_samples."""
        # Setup: No consensus (all different)
        mock_client.compare_semantic = AsyncMock(return_value=False)

        call_count = [0]

        async def mock_gen(step, ctx):
            call_count[0] += 1
            return LLMResponse(
                content=f"def test{call_count[0]}(): pass",
                tokens_input=10,
                tokens_output=20,
                model="test",
                stop_reason="end_turn",
            )

        result = await voter.vote(
            step=sample_step,
            context="test",
            generator=mock_gen,
            k=10,  # High k
            max_samples=5,  # Low max
        )

        assert result.total_samples <= 5

    @pytest.mark.asyncio
    async def test_vote_filters_red_flags(self, voter, mock_client, sample_step):
        """Vote should filter out red-flagged candidates."""
        mock_client.compare_semantic = AsyncMock(return_value=True)

        responses = [
            "def broken(",  # Invalid syntax - will be red-flagged
            "def valid(): pass",  # Valid
            "def valid(): pass",  # Valid (same)
        ]
        response_idx = [0]

        async def mock_gen(step, ctx):
            code = responses[response_idx[0] % len(responses)]
            response_idx[0] += 1
            return LLMResponse(
                content=code,
                tokens_input=10,
                tokens_output=20,
                model="test",
                stop_reason="end_turn",
            )

        result = await voter.vote(
            step=sample_step,
            context="test",
            generator=mock_gen,
            k=2,
            max_samples=10,
        )

        # Should have filtered the invalid one
        assert result.winner.code != "def broken("

    @pytest.mark.asyncio
    async def test_vote_parallel_faster(self, voter, mock_client, sample_step):
        """Parallel voting should work with batches."""
        mock_client.compare_semantic = AsyncMock(return_value=True)

        async def mock_gen(step, ctx):
            return LLMResponse(
                content="def test(): pass",
                tokens_input=10,
                tokens_output=20,
                model="test",
                stop_reason="end_turn",
            )

        result = await voter.vote_parallel(
            step=sample_step,
            context="test",
            generator=mock_gen,
            k=2,
            batch_size=3,
        )

        assert result.winner is not None


class TestFirstToAheadByK:
    """Tests for first_to_ahead_by_k helper."""

    @pytest.mark.asyncio
    async def test_helper_function(self, mock_client, sample_step):
        """Helper should work like Voter.vote."""
        mock_client.compare_semantic = AsyncMock(return_value=True)
        mock_client.generate_code = AsyncMock(return_value=LLMResponse(
            content="def test(): pass",
            tokens_input=10,
            tokens_output=20,
            model="test",
            stop_reason="end_turn",
        ))

        result = await first_to_ahead_by_k(
            step=sample_step,
            context="test",
            client=mock_client,
            k=2,
            max_samples=5,
        )

        assert result.winner is not None
