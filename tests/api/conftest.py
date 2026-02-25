"""
Pytest configuration for API tests.

Sets up proper Python paths for importing the API modules.
"""

import sys
from pathlib import Path

import pytest

# Get paths
tests_dir = Path(__file__).parent
api_dir = tests_dir.parent
apps_dir = api_dir.parent
root_dir = apps_dir.parent

# Add the apps directory (so 'api' can be imported as a package)
# Add the root directory (so 'models' can be imported)
# The order matters - insert in reverse order of priority
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(apps_dir))
sys.path.insert(0, str(api_dir))


@pytest.fixture
def mock_claude_base(tmp_path, monkeypatch):
    """
    Fixture that redirects settings.claude_base to a temp directory.

    Creates the necessary directory structure and patches settings.
    Returns the temp .claude directory path.
    """
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "projects").mkdir(exist_ok=True)

    from config import settings

    monkeypatch.setattr(settings, "claude_base", claude_dir)

    return claude_dir
