"""
Tests for mdap/mdap/discriminator.py
"""
import pytest
from unittest.mock import AsyncMock

from mdap.types import Candidate, MDAPConfig
from mdap.mdap.discriminator import Discriminator, SemanticGroup


class TestSemanticGroup:
    """Tests for SemanticGroup."""

    def test_create_group(self):
        candidate = Candidate(id="c1", code="def foo(): pass")
        group = SemanticGroup(
            id="group_0",
            representative=candidate,
            members=[candidate],
        )

        assert group.id == "group_0"
        assert group.votes == 1

    def test_add_member(self):
        c1 = Candidate(id="c1", code="code1")
        c2 = Candidate(id="c2", code="code2")

        group = SemanticGroup(id="g0", representative=c1, members=[c1])
        group.add(c2)

        assert group.votes == 2
        assert c2.group_id == "g0"


class TestDiscriminator:
    """Tests for Discriminator."""

    @pytest.fixture
    def discriminator(self, mock_client, config):
        return Discriminator(mock_client, config)

    @pytest.mark.asyncio
    async def test_compare_equivalent(self, discriminator, mock_client):
        """Test comparing equivalent code."""
        mock_client.compare_semantic = AsyncMock(return_value=True)

        result = await discriminator.compare(
            "def add(a, b): return a + b",
            "def add(x, y): return x + y",
            "Add two numbers",
        )

        assert result is True
        mock_client.compare_semantic.assert_called_once()

    @pytest.mark.asyncio
    async def test_compare_different(self, discriminator, mock_client):
        """Test comparing different code."""
        mock_client.compare_semantic = AsyncMock(return_value=False)

        result = await discriminator.compare(
            "def add(a, b): return a + b",
            "def add(a, b): return a - b",  # Different!
            "",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_compare_caching(self, discriminator, mock_client):
        """Comparison results should be cached."""
        mock_client.compare_semantic = AsyncMock(return_value=True)

        code_a = "def foo(): pass"
        code_b = "def bar(): pass"

        # First call
        await discriminator.compare(code_a, code_b)
        # Second call (should use cache)
        await discriminator.compare(code_a, code_b)
        # Reverse order (should also use cache)
        await discriminator.compare(code_b, code_a)

        # Should only call LLM once
        assert mock_client.compare_semantic.call_count == 1

    @pytest.mark.asyncio
    async def test_classify_new_group(self, discriminator, mock_client):
        """First candidate creates new group."""
        mock_client.compare_semantic = AsyncMock(return_value=False)

        candidate = Candidate(id="c1", code="def foo(): pass")
        group = await discriminator.classify(candidate, "context")

        assert group is not None
        assert group.id == "group_0"
        assert candidate in group.members
        assert candidate.group_id == "group_0"

    @pytest.mark.asyncio
    async def test_classify_existing_group(self, discriminator, mock_client):
        """Similar candidate joins existing group."""
        mock_client.compare_semantic = AsyncMock(return_value=True)

        c1 = Candidate(id="c1", code="def add(a,b): return a+b")
        c2 = Candidate(id="c2", code="def add(x,y): return x+y")

        group1 = await discriminator.classify(c1)
        group2 = await discriminator.classify(c2)

        assert group1 == group2
        assert group1.votes == 2

    @pytest.mark.asyncio
    async def test_classify_batch(self, discriminator, mock_client):
        """Classify multiple candidates."""
        # First two are equivalent, third is different
        call_count = [0]

        async def mock_compare(a, b, ctx=""):
            call_count[0] += 1
            # c1 and c2 are equivalent, c3 is different
            if "foo" in a and "foo" in b:
                return True
            if "bar" in a and "bar" in b:
                return True
            return False

        mock_client.compare_semantic = AsyncMock(side_effect=mock_compare)

        candidates = [
            Candidate(id="c1", code="def foo(): pass"),
            Candidate(id="c2", code="def foo(): return"),
            Candidate(id="c3", code="def bar(): pass"),
        ]

        groups = await discriminator.classify_batch(candidates)

        assert len(groups) >= 1  # At least one group

    @pytest.mark.asyncio
    async def test_get_winner_no_winner(self, discriminator):
        """No winner when margin < k."""
        # Create two groups with same votes
        c1 = Candidate(id="c1", code="code1")
        c2 = Candidate(id="c2", code="code2")

        discriminator.groups = {
            "g0": SemanticGroup(id="g0", representative=c1, members=[c1]),
            "g1": SemanticGroup(id="g1", representative=c2, members=[c2]),
        }

        winner = discriminator.get_winner(k=2)
        assert winner is None  # Margin is 0, need 2

    @pytest.mark.asyncio
    async def test_get_winner_with_margin(self, discriminator):
        """Winner when margin >= k."""
        c1 = Candidate(id="c1", code="code1")
        c2 = Candidate(id="c2", code="code2")
        c3 = Candidate(id="c3", code="code3")

        group0 = SemanticGroup(id="g0", representative=c1, members=[c1, c2, c3])
        group1 = SemanticGroup(id="g1", representative=Candidate(id="x", code="x"), members=[])

        discriminator.groups = {"g0": group0, "g1": group1}

        winner = discriminator.get_winner(k=2)
        assert winner == group0

    def test_reset(self, discriminator):
        """Reset should clear groups and cache."""
        discriminator.groups = {"g0": SemanticGroup(id="g0", representative=Candidate(id="x", code="x"), members=[])}
        discriminator._comparison_cache = {("a", "b"): True}

        discriminator.reset()

        assert len(discriminator.groups) == 0
        assert len(discriminator._comparison_cache) == 0

    def test_stats(self, discriminator):
        """Stats should return correct counts."""
        c1 = Candidate(id="c1", code="code1")
        c2 = Candidate(id="c2", code="code2")

        discriminator.groups = {
            "g0": SemanticGroup(id="g0", representative=c1, members=[c1, c2]),
        }
        discriminator._comparison_cache = {("a", "b"): True, ("c", "d"): False}

        stats = discriminator.stats()

        assert stats["groups"] == 1
        assert stats["total_candidates"] == 2
        assert stats["cache_hits"] == 2
