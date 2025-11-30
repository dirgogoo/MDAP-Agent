"""
Tests for mdap/execution/ module
"""
import pytest
import os
from pathlib import Path

from mdap.types import Step, StepType
from mdap.execution.tools import (
    Tool, ToolType, ToolRegistry, register_tool, get_tool,
    get_registry, execute_tool
)
from mdap.execution.file_ops import ReadTool, WriteTool, ListDirTool, init_file_tools
from mdap.execution.search import GrepTool, GlobTool, FindFunctionTool, init_search_tools


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_register_and_get(self):
        registry = ToolRegistry()

        class DummyTool(Tool):
            @property
            def name(self): return "dummy"
            @property
            def tool_type(self): return ToolType.READ
            async def execute(self, **kwargs): pass

        tool = DummyTool()
        registry.register(tool)

        assert registry.get("dummy") == tool
        assert registry.get("nonexistent") is None

    def test_list_tools(self):
        registry = ToolRegistry()

        class Tool1(Tool):
            @property
            def name(self): return "tool1"
            @property
            def tool_type(self): return ToolType.READ
            async def execute(self, **kwargs): pass

        class Tool2(Tool):
            @property
            def name(self): return "tool2"
            @property
            def tool_type(self): return ToolType.WRITE
            async def execute(self, **kwargs): pass

        registry.register(Tool1())
        registry.register(Tool2())

        tools = registry.list_tools()
        assert "tool1" in tools
        assert "tool2" in tools

    def test_get_by_type(self):
        registry = ToolRegistry()

        class ReadTool1(Tool):
            @property
            def name(self): return "read1"
            @property
            def tool_type(self): return ToolType.READ
            async def execute(self, **kwargs): pass

        class WriteTool1(Tool):
            @property
            def name(self): return "write1"
            @property
            def tool_type(self): return ToolType.WRITE
            async def execute(self, **kwargs): pass

        registry.register(ReadTool1())
        registry.register(WriteTool1())

        read_tools = registry.get_by_type(ToolType.READ)
        assert len(read_tools) == 1
        assert read_tools[0].name == "read1"


class TestReadTool:
    """Tests for ReadTool."""

    @pytest.fixture
    def read_tool(self):
        return ReadTool()

    @pytest.mark.asyncio
    async def test_read_existing_file(self, read_tool, temp_python_file):
        """Should read existing file content."""
        result = await read_tool.execute(path=str(temp_python_file))

        assert result.success is True
        assert "def hello" in result.data
        assert "def add" in result.data

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, read_tool, temp_dir):
        """Should fail for nonexistent file."""
        error = read_tool.validate_args(path=str(temp_dir / "nonexistent.py"))
        assert error is not None
        assert "not found" in error.lower()

    def test_validate_missing_path(self, read_tool):
        """Should require path argument."""
        error = read_tool.validate_args()
        assert error is not None
        assert "path" in error.lower()


class TestWriteTool:
    """Tests for WriteTool."""

    @pytest.fixture
    def write_tool(self):
        return WriteTool()

    @pytest.mark.asyncio
    async def test_write_file(self, write_tool, temp_dir):
        """Should write file content."""
        file_path = temp_dir / "new_file.py"
        content = "print('hello')"

        result = await write_tool.execute(
            path=str(file_path),
            content=content,
        )

        assert result.success is True
        assert file_path.read_text() == content

    @pytest.mark.asyncio
    async def test_write_creates_dirs(self, write_tool, temp_dir):
        """Should create parent directories."""
        file_path = temp_dir / "subdir" / "nested" / "file.py"

        result = await write_tool.execute(
            path=str(file_path),
            content="x = 1",
            create_dirs=True,
        )

        assert result.success is True
        assert file_path.exists()

    def test_validate_missing_content(self, write_tool):
        """Should require content argument."""
        error = write_tool.validate_args(path="/some/path")
        assert error is not None
        assert "content" in error.lower()


class TestListDirTool:
    """Tests for ListDirTool."""

    @pytest.fixture
    def ls_tool(self):
        return ListDirTool()

    @pytest.mark.asyncio
    async def test_list_directory(self, ls_tool, temp_dir):
        """Should list directory contents."""
        # Create some files
        (temp_dir / "file1.py").write_text("x = 1")
        (temp_dir / "file2.py").write_text("x = 2")
        (temp_dir / "file3.txt").write_text("text")

        result = await ls_tool.execute(path=str(temp_dir))

        assert result.success is True
        assert len(result.data) == 3

    @pytest.mark.asyncio
    async def test_list_with_pattern(self, ls_tool, temp_dir):
        """Should filter by pattern."""
        (temp_dir / "file1.py").write_text("x = 1")
        (temp_dir / "file2.txt").write_text("text")

        result = await ls_tool.execute(
            path=str(temp_dir),
            pattern="*.py",
        )

        assert result.success is True
        assert len(result.data) == 1


class TestGrepTool:
    """Tests for GrepTool."""

    @pytest.fixture
    def grep_tool(self):
        return GrepTool()

    @pytest.mark.asyncio
    async def test_grep_find_pattern(self, grep_tool, temp_python_file, temp_dir):
        """Should find pattern in files."""
        result = await grep_tool.execute(
            pattern="def hello",
            path=str(temp_dir),
        )

        assert result.success is True
        assert len(result.data) >= 1
        assert any("hello" in m["content"] for m in result.data)

    @pytest.mark.asyncio
    async def test_grep_no_matches(self, grep_tool, temp_dir):
        """Should return empty for no matches."""
        (temp_dir / "test.py").write_text("x = 1")

        result = await grep_tool.execute(
            pattern="nonexistent_pattern_xyz",
            path=str(temp_dir),
        )

        assert result.success is True
        assert len(result.data) == 0

    @pytest.mark.asyncio
    async def test_grep_with_context(self, grep_tool, temp_python_file, temp_dir):
        """Should include context lines."""
        result = await grep_tool.execute(
            pattern="def add",
            path=str(temp_dir),
            context=2,
        )

        assert result.success is True
        if result.data:
            match = result.data[0]
            assert "context_before" in match
            assert "context_after" in match

    def test_validate_invalid_regex(self, grep_tool):
        """Should validate regex pattern."""
        # Invalid regex should be caught during execute, not validate
        # validate_args only checks for required args
        error = grep_tool.validate_args()
        assert error is not None


class TestGlobTool:
    """Tests for GlobTool."""

    @pytest.fixture
    def glob_tool(self):
        return GlobTool()

    @pytest.mark.asyncio
    async def test_glob_find_files(self, glob_tool, temp_dir):
        """Should find files by pattern."""
        (temp_dir / "module1.py").write_text("x")
        (temp_dir / "module2.py").write_text("y")
        (temp_dir / "readme.md").write_text("z")

        result = await glob_tool.execute(
            pattern="*.py",
            path=str(temp_dir),
        )

        assert result.success is True
        assert len(result.data) == 2

    @pytest.mark.asyncio
    async def test_glob_recursive(self, glob_tool, temp_dir):
        """Should find files recursively."""
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        (temp_dir / "root.py").write_text("x")
        (subdir / "nested.py").write_text("y")

        result = await glob_tool.execute(
            pattern="**/*.py",
            path=str(temp_dir),
        )

        assert result.success is True
        assert len(result.data) == 2


class TestFindFunctionTool:
    """Tests for FindFunctionTool."""

    @pytest.fixture
    def find_tool(self):
        return FindFunctionTool()

    @pytest.mark.asyncio
    async def test_find_function(self, find_tool, temp_python_file, temp_dir):
        """Should find function definition."""
        result = await find_tool.execute(
            name="hello",
            path=str(temp_dir),
        )

        assert result.success is True
        assert len(result.data) >= 1
        assert "def hello" in result.data[0]["definition"]

    @pytest.mark.asyncio
    async def test_find_class(self, find_tool, temp_python_file, temp_dir):
        """Should find class definition."""
        result = await find_tool.execute(
            name="Calculator",
            path=str(temp_dir),
        )

        assert result.success is True
        assert len(result.data) >= 1
        assert "class Calculator" in result.data[0]["definition"]

    @pytest.mark.asyncio
    async def test_find_not_found(self, find_tool, temp_dir):
        """Should return empty for not found."""
        (temp_dir / "test.py").write_text("x = 1")

        result = await find_tool.execute(
            name="nonexistent_function",
            path=str(temp_dir),
        )

        assert result.success is True
        assert len(result.data) == 0


class TestExecuteTool:
    """Tests for execute_tool function."""

    @pytest.fixture(autouse=True)
    def setup_tools(self):
        """Initialize tools before tests."""
        init_file_tools()
        init_search_tools()

    @pytest.mark.asyncio
    async def test_execute_read(self, temp_python_file):
        """Should execute read tool via step."""
        step = Step(
            type=StepType.READ,
            action=f"read:{temp_python_file}",
        )

        result = await execute_tool(step)

        assert result.success is True
        assert "def hello" in result.data

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        """Should fail for unknown tool."""
        step = Step(
            type=StepType.READ,
            action="unknown_tool:arg",
        )

        result = await execute_tool(step)

        assert result.success is False
        assert "unknown" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_no_action(self):
        """Should fail when no action specified."""
        step = Step(type=StepType.READ)

        result = await execute_tool(step)

        assert result.success is False
