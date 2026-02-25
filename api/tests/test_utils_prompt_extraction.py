"""Tests for get_initial_prompt_from_index() helper function."""

from utils import get_initial_prompt_from_index


class TestGetInitialPromptFromIndex:
    """Test the get_initial_prompt_from_index() helper function."""

    def test_returns_none_for_no_prompt_placeholder(self):
        """Should return None for 'No prompt' placeholder."""
        assert get_initial_prompt_from_index("No prompt") is None

    def test_returns_none_for_empty_string(self):
        """Should return None for empty string."""
        assert get_initial_prompt_from_index("") is None

    def test_returns_none_for_none(self):
        """Should return None for None input."""
        assert get_initial_prompt_from_index(None) is None

    def test_extracts_from_command_args(self):
        """Should extract content from <command-args> tags."""
        command_wrapped = "<command-args>Fix the authentication bug</command-args>"
        result = get_initial_prompt_from_index(command_wrapped)
        assert result == "Fix the authentication bug"

    def test_extracts_from_full_command_structure(self):
        """Should extract from full command structure with multiple tags."""
        command_wrapped = (
            "<command-message>oh-my-claudecode:analyze</command-message>\n"
            "<command-name>/oh-my-claudecode:analyze</command-name>\n"
            "<command-args>Debug the API endpoint</command-args>"
        )
        result = get_initial_prompt_from_index(command_wrapped)
        assert result == "Debug the API endpoint"

    def test_returns_none_for_truncated_command_with_ellipsis(self):
        """Should return None for truncated command content."""
        truncated = "<command-args>…"
        assert get_initial_prompt_from_index(truncated) is None

    def test_returns_none_for_truncated_command_missing_closing_tag(self):
        """Should return None for command with missing closing tag and ellipsis."""
        truncated = "<command-args>Fix the…"
        # This should extract "Fix the" (after stripping ellipsis marker)
        result = get_initial_prompt_from_index(truncated)
        # The extract_prompt_from_content handles this by stripping "…" markers
        assert result == "Fix the"

    def test_returns_none_for_command_before_args_tag(self):
        """Should return None when truncated before <command-args>."""
        truncated = "<command-message>oh-my-claudecode:analyze</command-message>"
        assert get_initial_prompt_from_index(truncated) is None

    def test_returns_regular_prompt_unchanged(self):
        """Should return regular (non-command) prompts as-is."""
        regular_prompt = "Please review this code"
        result = get_initial_prompt_from_index(regular_prompt)
        assert result == "Please review this code"

    def test_truncates_to_max_length(self):
        """Should truncate to max_length parameter."""
        long_prompt = "a" * 1000
        result = get_initial_prompt_from_index(long_prompt, max_length=100)
        assert len(result) == 100
        assert result == "a" * 100

    def test_default_max_length_is_500(self):
        """Should use 500 as default max_length."""
        long_prompt = "b" * 1000
        result = get_initial_prompt_from_index(long_prompt)
        assert len(result) == 500
        assert result == "b" * 500

    def test_does_not_truncate_short_prompts(self):
        """Should not truncate prompts shorter than max_length."""
        short_prompt = "Short prompt"
        result = get_initial_prompt_from_index(short_prompt, max_length=500)
        assert result == "Short prompt"

    def test_handles_multiline_command_args(self):
        """Should handle multiline content in command-args."""
        multiline = "<command-args>\nLine 1: Description\nLine 2: More details\n</command-args>"
        result = get_initial_prompt_from_index(multiline)
        assert "Line 1: Description" in result
        assert "Line 2: More details" in result

    def test_custom_max_length(self):
        """Should respect custom max_length parameter."""
        prompt = "0123456789" * 10  # 100 chars
        result = get_initial_prompt_from_index(prompt, max_length=25)
        assert len(result) == 25
        assert result == "0123456789012345678901234"
