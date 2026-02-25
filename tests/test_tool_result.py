"""
Unit tests for ToolResult model.

Tests cover instantiation, validation, class methods, and file operations.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from models import ToolResult

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def tool_results_dir(tmp_path: Path) -> Path:
    """Create a temporary tool-results directory."""
    tool_results = tmp_path / "session-uuid" / "tool-results"
    tool_results.mkdir(parents=True)
    return tool_results


@pytest.fixture
def sample_tool_result_file(tool_results_dir: Path) -> Path:
    """Create a sample tool result file with content."""
    tool_file = tool_results_dir / "toolu_01ABC123.txt"
    tool_file.write_text("Sample tool output content\nLine 2\nLine 3")
    return tool_file


@pytest.fixture
def empty_tool_result_file(tool_results_dir: Path) -> Path:
    """Create an empty tool result file."""
    tool_file = tool_results_dir / "toolu_empty.txt"
    tool_file.write_text("")
    return tool_file


@pytest.fixture
def valid_tool_result_path(tool_results_dir: Path) -> Path:
    """Return a valid tool result path (file may not exist)."""
    return tool_results_dir / "toolu_valid123.txt"


# =============================================================================
# Test: ToolResult Instantiation
# =============================================================================


class TestToolResultInstantiation:
    """Tests for ToolResult instantiation with valid data."""

    def test_instantiation_with_valid_tool_use_id_and_path(self, tool_results_dir: Path):
        """Test ToolResult instantiation with valid tool_use_id and path."""
        path = tool_results_dir / "toolu_01XYZ.txt"
        result = ToolResult(tool_use_id="toolu_01XYZ", path=path)

        assert result.tool_use_id == "toolu_01XYZ"
        assert result.path == path

    def test_instantiation_with_string_path(self, tool_results_dir: Path):
        """Test ToolResult instantiation with string path (converted to Path)."""
        path_str = str(tool_results_dir / "toolu_01ABC.txt")
        result = ToolResult(tool_use_id="toolu_01ABC", path=path_str)

        assert isinstance(result.path, Path)
        assert str(result.path) == path_str

    def test_instantiation_with_various_valid_ids(self, tool_results_dir: Path):
        """Test instantiation with various valid tool use ID formats."""
        valid_ids = [
            "toolu_01ABC",
            "toolu_a",
            "toolu_ABC123xyz",
            "toolu_with-dashes",
            "toolu_with_underscores",
            "toolu_MixedCase123",
            "toolu_01234567890",
        ]

        for tool_id in valid_ids:
            path = tool_results_dir / f"{tool_id}.txt"
            result = ToolResult(tool_use_id=tool_id, path=path)
            assert result.tool_use_id == tool_id


# =============================================================================
# Test: tool_use_id Validation
# =============================================================================


class TestToolUseIdValidation:
    """Tests for tool_use_id validation."""

    def test_valid_tool_use_id_simple(self, tool_results_dir: Path):
        """Test valid simple tool_use_id format (toolu_xxx)."""
        path = tool_results_dir / "toolu_01ABC.txt"
        result = ToolResult(tool_use_id="toolu_01ABC", path=path)
        assert result.tool_use_id == "toolu_01ABC"

    def test_valid_tool_use_id_with_alphanumeric(self, tool_results_dir: Path):
        """Test valid tool_use_id with alphanumeric characters."""
        path = tool_results_dir / "toolu_AbCdEf123456.txt"
        result = ToolResult(tool_use_id="toolu_AbCdEf123456", path=path)
        assert result.tool_use_id == "toolu_AbCdEf123456"

    def test_valid_tool_use_id_with_dashes(self, tool_results_dir: Path):
        """Test valid tool_use_id with dashes."""
        path = tool_results_dir / "toolu_abc-def-123.txt"
        result = ToolResult(tool_use_id="toolu_abc-def-123", path=path)
        assert result.tool_use_id == "toolu_abc-def-123"

    def test_valid_tool_use_id_with_underscores(self, tool_results_dir: Path):
        """Test valid tool_use_id with underscores."""
        path = tool_results_dir / "toolu_abc_def_123.txt"
        result = ToolResult(tool_use_id="toolu_abc_def_123", path=path)
        assert result.tool_use_id == "toolu_abc_def_123"

    def test_invalid_tool_use_id_missing_prefix(self, tool_results_dir: Path):
        """Test that tool_use_id without 'toolu_' prefix raises ValueError."""
        path = tool_results_dir / "invalid.txt"
        with pytest.raises(ValidationError) as exc_info:
            ToolResult(tool_use_id="01ABC", path=path)

        assert "Invalid tool_use_id format" in str(exc_info.value)

    def test_invalid_tool_use_id_wrong_prefix(self, tool_results_dir: Path):
        """Test that tool_use_id with wrong prefix raises ValueError."""
        path = tool_results_dir / "tool_01ABC.txt"
        with pytest.raises(ValidationError) as exc_info:
            ToolResult(tool_use_id="tool_01ABC", path=path)

        assert "Invalid tool_use_id format" in str(exc_info.value)

    def test_invalid_tool_use_id_empty_after_prefix(self, tool_results_dir: Path):
        """Test that 'toolu_' alone (empty suffix) raises ValueError."""
        path = tool_results_dir / "toolu_.txt"
        with pytest.raises(ValidationError) as exc_info:
            ToolResult(tool_use_id="toolu_", path=path)

        assert "Invalid tool_use_id format" in str(exc_info.value)

    def test_invalid_tool_use_id_empty_string(self, tool_results_dir: Path):
        """Test that empty string raises ValueError."""
        path = tool_results_dir / "empty.txt"
        with pytest.raises(ValidationError) as exc_info:
            ToolResult(tool_use_id="", path=path)

        assert "Invalid tool_use_id format" in str(exc_info.value)

    def test_invalid_tool_use_id_special_characters(self, tool_results_dir: Path):
        """Test that tool_use_id with invalid special characters raises ValueError."""
        invalid_ids = [
            "toolu_abc@123",
            "toolu_abc#def",
            "toolu_abc!xyz",
            "toolu_abc.def",
            "toolu_abc def",  # space
        ]

        for invalid_id in invalid_ids:
            path = tool_results_dir / "invalid.txt"
            with pytest.raises(ValidationError) as exc_info:
                ToolResult(tool_use_id=invalid_id, path=path)

            assert "Invalid tool_use_id format" in str(exc_info.value)


# =============================================================================
# Test: Path Validation
# =============================================================================


class TestPathValidation:
    """Tests for path validation."""

    def test_valid_path_in_tool_results_directory(self, tool_results_dir: Path):
        """Test valid path in tool-results/ directory with .txt extension."""
        path = tool_results_dir / "toolu_01ABC.txt"
        result = ToolResult(tool_use_id="toolu_01ABC", path=path)
        assert result.path == path

    def test_invalid_path_not_in_tool_results_directory(self, tmp_path: Path):
        """Test that path not in tool-results/ directory raises ValueError."""
        path = tmp_path / "other-dir" / "toolu_01ABC.txt"
        path.parent.mkdir(parents=True, exist_ok=True)

        with pytest.raises(ValidationError) as exc_info:
            ToolResult(tool_use_id="toolu_01ABC", path=path)

        assert "must be in tool-results/ directory" in str(exc_info.value)

    def test_invalid_path_wrong_extension_json(self, tool_results_dir: Path):
        """Test that path with .json extension raises ValueError."""
        path = tool_results_dir / "toolu_01ABC.json"

        with pytest.raises(ValidationError) as exc_info:
            ToolResult(tool_use_id="toolu_01ABC", path=path)

        assert "must have .txt extension" in str(exc_info.value)

    def test_invalid_path_wrong_extension_md(self, tool_results_dir: Path):
        """Test that path with .md extension raises ValueError."""
        path = tool_results_dir / "toolu_01ABC.md"

        with pytest.raises(ValidationError) as exc_info:
            ToolResult(tool_use_id="toolu_01ABC", path=path)

        assert "must have .txt extension" in str(exc_info.value)

    def test_invalid_path_no_extension(self, tool_results_dir: Path):
        """Test that path without extension raises ValueError."""
        path = tool_results_dir / "toolu_01ABC"

        with pytest.raises(ValidationError) as exc_info:
            ToolResult(tool_use_id="toolu_01ABC", path=path)

        assert "must have .txt extension" in str(exc_info.value)

    def test_valid_path_nested_tool_results(self, tmp_path: Path):
        """Test valid path when tool-results is nested in directory structure."""
        nested_path = tmp_path / "project" / "session" / "tool-results" / "toolu_01ABC.txt"
        nested_path.parent.mkdir(parents=True, exist_ok=True)

        result = ToolResult(tool_use_id="toolu_01ABC", path=nested_path)
        assert result.path == nested_path


# =============================================================================
# Test: from_path() Class Method
# =============================================================================


class TestFromPathClassMethod:
    """Tests for the from_path() class method."""

    def test_from_path_creates_tool_result(self, sample_tool_result_file: Path):
        """Test from_path() creates ToolResult with correct tool_use_id."""
        result = ToolResult.from_path(sample_tool_result_file)

        assert result.tool_use_id == "toolu_01ABC123"
        assert result.path == sample_tool_result_file

    def test_from_path_extracts_tool_use_id_from_filename(self, tool_results_dir: Path):
        """Test from_path() correctly extracts tool_use_id from filename."""
        path = tool_results_dir / "toolu_XYZ789.txt"
        path.touch()

        result = ToolResult.from_path(path)
        assert result.tool_use_id == "toolu_XYZ789"

    def test_from_path_with_complex_id(self, tool_results_dir: Path):
        """Test from_path() with complex tool_use_id containing dashes/underscores."""
        path = tool_results_dir / "toolu_abc-def_123.txt"
        path.touch()

        result = ToolResult.from_path(path)
        assert result.tool_use_id == "toolu_abc-def_123"

    def test_from_path_invalid_filename_raises_error(self, tool_results_dir: Path):
        """Test from_path() with invalid filename raises ValidationError."""
        path = tool_results_dir / "invalid_filename.txt"
        path.touch()

        with pytest.raises(ValidationError) as exc_info:
            ToolResult.from_path(path)

        assert "Invalid tool_use_id format" in str(exc_info.value)

    def test_from_path_invalid_directory_raises_error(self, tmp_path: Path):
        """Test from_path() with path not in tool-results raises ValidationError."""
        path = tmp_path / "wrong-dir" / "toolu_01ABC.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

        with pytest.raises(ValidationError) as exc_info:
            ToolResult.from_path(path)

        assert "must be in tool-results/ directory" in str(exc_info.value)


# =============================================================================
# Test: read_content()
# =============================================================================


class TestReadContent:
    """Tests for the read_content() method."""

    def test_read_content_returns_file_content(self, sample_tool_result_file: Path):
        """Test read_content() returns the file content as string."""
        result = ToolResult.from_path(sample_tool_result_file)
        content = result.read_content()

        assert content == "Sample tool output content\nLine 2\nLine 3"

    def test_read_content_empty_file(self, empty_tool_result_file: Path):
        """Test read_content() returns empty string for empty file."""
        result = ToolResult.from_path(empty_tool_result_file)
        content = result.read_content()

        assert content == ""

    def test_read_content_file_not_found_raises_error(self, valid_tool_result_path: Path):
        """Test read_content() raises FileNotFoundError for missing file."""
        result = ToolResult(tool_use_id="toolu_valid123", path=valid_tool_result_path)

        with pytest.raises(FileNotFoundError):
            result.read_content()

    def test_read_content_with_unicode(self, tool_results_dir: Path):
        """Test read_content() handles unicode content correctly."""
        path = tool_results_dir / "toolu_unicode.txt"
        unicode_content = "Hello 世界! Émojis: 🎉🚀"
        path.write_text(unicode_content, encoding="utf-8")

        result = ToolResult.from_path(path)
        content = result.read_content()

        assert content == unicode_content

    def test_read_content_multiline(self, tool_results_dir: Path):
        """Test read_content() handles multiline content."""
        path = tool_results_dir / "toolu_multiline.txt"
        multiline_content = """Line 1
Line 2
Line 3

Line 5 after blank"""
        path.write_text(multiline_content)

        result = ToolResult.from_path(path)
        content = result.read_content()

        assert content == multiline_content


# =============================================================================
# Test: read_content_safe()
# =============================================================================


class TestReadContentSafe:
    """Tests for the read_content_safe() method."""

    def test_read_content_safe_returns_content(self, sample_tool_result_file: Path):
        """Test read_content_safe() returns content when file exists."""
        result = ToolResult.from_path(sample_tool_result_file)
        content = result.read_content_safe()

        assert content == "Sample tool output content\nLine 2\nLine 3"

    def test_read_content_safe_returns_none_for_missing_file(self, valid_tool_result_path: Path):
        """Test read_content_safe() returns None when file doesn't exist."""
        result = ToolResult(tool_use_id="toolu_valid123", path=valid_tool_result_path)
        content = result.read_content_safe()

        assert content is None

    def test_read_content_safe_empty_file(self, empty_tool_result_file: Path):
        """Test read_content_safe() returns empty string for empty file."""
        result = ToolResult.from_path(empty_tool_result_file)
        content = result.read_content_safe()

        assert content == ""

    def test_read_content_safe_does_not_raise(self, valid_tool_result_path: Path):
        """Test read_content_safe() does not raise FileNotFoundError."""
        result = ToolResult(tool_use_id="toolu_valid123", path=valid_tool_result_path)

        # Should not raise
        content = result.read_content_safe()
        assert content is None


# =============================================================================
# Test: exists Property
# =============================================================================


class TestExistsProperty:
    """Tests for the exists property."""

    def test_exists_returns_true_for_existing_file(self, sample_tool_result_file: Path):
        """Test exists property returns True for existing file."""
        result = ToolResult.from_path(sample_tool_result_file)
        assert result.exists is True

    def test_exists_returns_false_for_missing_file(self, valid_tool_result_path: Path):
        """Test exists property returns False for missing file."""
        result = ToolResult(tool_use_id="toolu_valid123", path=valid_tool_result_path)
        assert result.exists is False

    def test_exists_after_file_deleted(self, sample_tool_result_file: Path):
        """Test exists property returns False after file is deleted."""
        result = ToolResult.from_path(sample_tool_result_file)
        assert result.exists is True

        # Delete the file
        sample_tool_result_file.unlink()

        assert result.exists is False


# =============================================================================
# Test: size_bytes Property
# =============================================================================


class TestSizeBytesProperty:
    """Tests for the size_bytes property."""

    def test_size_bytes_returns_file_size(self, sample_tool_result_file: Path):
        """Test size_bytes returns correct file size."""
        result = ToolResult.from_path(sample_tool_result_file)
        expected_size = len("Sample tool output content\nLine 2\nLine 3")

        assert result.size_bytes == expected_size

    def test_size_bytes_returns_zero_for_missing_file(self, valid_tool_result_path: Path):
        """Test size_bytes returns 0 for missing file."""
        result = ToolResult(tool_use_id="toolu_valid123", path=valid_tool_result_path)
        assert result.size_bytes == 0

    def test_size_bytes_empty_file(self, empty_tool_result_file: Path):
        """Test size_bytes returns 0 for empty file."""
        result = ToolResult.from_path(empty_tool_result_file)
        assert result.size_bytes == 0

    def test_size_bytes_large_content(self, tool_results_dir: Path):
        """Test size_bytes for file with larger content."""
        path = tool_results_dir / "toolu_large.txt"
        large_content = "x" * 10000  # 10KB of 'x'
        path.write_text(large_content)

        result = ToolResult.from_path(path)
        assert result.size_bytes == 10000

    def test_size_bytes_unicode_content(self, tool_results_dir: Path):
        """Test size_bytes accounts for unicode byte size."""
        path = tool_results_dir / "toolu_unicode.txt"
        # Unicode characters take multiple bytes
        unicode_content = "世界"  # 2 Chinese characters, 3 bytes each in UTF-8
        path.write_text(unicode_content, encoding="utf-8")

        result = ToolResult.from_path(path)
        # Each Chinese character is 3 bytes in UTF-8
        assert result.size_bytes == 6


# =============================================================================
# Test: Immutability (frozen=True)
# =============================================================================


class TestImmutability:
    """Tests for model immutability (frozen=True)."""

    def test_cannot_modify_tool_use_id(self, sample_tool_result_file: Path):
        """Test that tool_use_id cannot be modified after creation."""
        result = ToolResult.from_path(sample_tool_result_file)

        with pytest.raises(ValidationError):
            result.tool_use_id = "toolu_newid"

    def test_cannot_modify_path(self, sample_tool_result_file: Path):
        """Test that path cannot be modified after creation."""
        result = ToolResult.from_path(sample_tool_result_file)
        new_path = sample_tool_result_file.parent / "toolu_other.txt"

        with pytest.raises(ValidationError):
            result.path = new_path

    def test_model_is_hashable(self, sample_tool_result_file: Path):
        """Test that frozen model is hashable (can be used in sets/dicts)."""
        result = ToolResult.from_path(sample_tool_result_file)

        # Should be hashable
        hash_value = hash(result)
        assert isinstance(hash_value, int)

        # Can be used in a set
        result_set = {result}
        assert result in result_set

    def test_equal_instances_have_same_hash(self, tool_results_dir: Path):
        """Test that equal instances have the same hash."""
        path = tool_results_dir / "toolu_01ABC.txt"
        path.touch()

        result1 = ToolResult(tool_use_id="toolu_01ABC", path=path)
        result2 = ToolResult(tool_use_id="toolu_01ABC", path=path)

        assert result1 == result2
        assert hash(result1) == hash(result2)

    def test_different_instances_are_not_equal(self, tool_results_dir: Path):
        """Test that different instances are not equal."""
        path1 = tool_results_dir / "toolu_01ABC.txt"
        path2 = tool_results_dir / "toolu_02DEF.txt"
        path1.touch()
        path2.touch()

        result1 = ToolResult(tool_use_id="toolu_01ABC", path=path1)
        result2 = ToolResult(tool_use_id="toolu_02DEF", path=path2)

        assert result1 != result2
