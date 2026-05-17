"""
Unit tests for api/services/ticket_parser.py.

Pure I/O-free parser, table-driven.
"""

import sys
from pathlib import Path

import pytest

# Make `api/` importable
_api_dir = Path(__file__).resolve().parent.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from services.ticket_parser import parse_ticket_ref


@pytest.mark.parametrize(
    "raw,hint,expected_provider,expected_key",
    [
        # Linear URLs
        ("https://linear.app/acme/issue/ABC-123", None, "linear", "ABC-123"),
        ("https://linear.app/acme/issue/ABC-123/some-title", None, "linear", "ABC-123"),
        ("https://linear.app/acme/issue/abc-123", None, "linear", "ABC-123"),
        # Jira URLs
        ("https://acme.atlassian.net/browse/PROJ-45", None, "jira", "PROJ-45"),
        ("https://acme.atlassian.net/browse/PROJ-45?focusedId=99", None, "jira", "PROJ-45"),
        # GitHub URLs
        ("https://github.com/octocat/hello-world/issues/42", None, "github", "octocat/hello-world#42"),
        ("https://github.com/octocat/hello-world/pull/42", None, "github", "octocat/hello-world#42"),
        ("https://github.com/Octocat/hello-world/issues/42", None, "github", "Octocat/hello-world#42"),
        # GitHub short
        ("octocat/hello-world#42", None, "github", "octocat/hello-world#42"),
        ("OctoCat/hello-world#1", None, "github", "OctoCat/hello-world#1"),
        # Bare keys with hint
        ("ABC-123", "linear", "linear", "ABC-123"),
        ("PROJ-45", "jira", "jira", "PROJ-45"),
        ("abc-123", "linear", "linear", "ABC-123"),
    ],
)
def test_parse_recognized(raw, hint, expected_provider, expected_key):
    ref = parse_ticket_ref(raw, hint_provider=hint)
    assert ref is not None, f"expected to parse {raw!r}"
    assert ref.provider == expected_provider
    assert ref.external_key == expected_key
    assert ref.url  # always populated


def test_github_url_returns_canonical_form_even_for_pull_url():
    ref = parse_ticket_ref("https://github.com/octocat/repo/pull/9")
    assert ref is not None
    # canonical URL prefers /issues/ even when input was /pull/
    assert ref.url == "https://github.com/octocat/repo/issues/9"


def test_bare_key_without_hint_returns_none():
    """Bare ABC-123 is ambiguous between Linear and Jira; we never guess."""
    assert parse_ticket_ref("ABC-123") is None
    assert parse_ticket_ref("ABC-123", hint_provider="github") is None  # wrong hint


def test_bare_hash_n_is_unsupported():
    """A bare '#42' has no owner/repo; spec explicitly excludes it."""
    assert parse_ticket_ref("#42") is None
    assert parse_ticket_ref("#42", hint_provider="github") is None


@pytest.mark.parametrize(
    "garbage",
    [
        "",
        "   ",
        "not-a-ticket",
        "https://example.com/some/path",
        "linear.app/team/issue/ABC-123",  # missing scheme
        "ABC",  # missing -N
        "https://github.com/owner/repo/discussions/42",  # not issue/pull
    ],
)
def test_parse_garbage_returns_none(garbage):
    assert parse_ticket_ref(garbage) is None


def test_whitespace_trimmed():
    ref = parse_ticket_ref("  https://linear.app/acme/issue/ABC-1  ")
    assert ref is not None
    assert ref.external_key == "ABC-1"


def test_bare_key_url_for_linear_is_search_fallback():
    ref = parse_ticket_ref("ABC-123", hint_provider="linear")
    assert ref is not None
    assert "ABC-123" in ref.url
    assert "linear.app" in ref.url


def test_bare_key_url_for_jira_is_atlassian_browse():
    ref = parse_ticket_ref("PROJ-45", hint_provider="jira")
    assert ref is not None
    assert "PROJ-45" in ref.url
    assert "atlassian.net" in ref.url
