"""
Tests for the analytics report router.

Covers:
- _build_prompt()      — pure prompt builder
- _save_report() / _load_all_reports() / _find_report_file() — disk helpers
- _prune_old_reports() — MAX_REPORTS cap
- POST /analytics/report  — happy path, no-data 400, claude failures (503/504/429)
- GET  /analytics/report  — list endpoint
- GET  /analytics/report/{id} — single report
- DELETE /analytics/report/{id} — delete endpoint

Run from api/:
    pytest tests/api/test_analytics_report.py -v
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from routers.analytics_report import (
    MAX_REPORTS,
    _build_prompt,
    _find_report_file,
    _load_all_reports,
    _prune_old_reports,
    _save_report,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_ANALYTICS = {
    "total_sessions": 10,
    "estimated_cost_usd": 1.23,
    "cache_hit_rate": 0.45,
    "total_tokens": 50_000,
    "total_input_tokens": 30_000,
    "total_output_tokens": 20_000,
    "total_duration_seconds": 3600,
    "projects_active": 3,
    "peak_hours": [9, 14, 21],
    "time_distribution": {
        "morning_pct": 30,
        "afternoon_pct": 40,
        "evening_pct": 20,
        "night_pct": 10,
        "dominant_period": "afternoon",
    },
    "models_categorized": {"sonnet": 7, "haiku": 3},
    "tools_used": {"Read": 120, "Write": 40, "Bash": 30},
}


@pytest.fixture
def reports_in_tmp(tmp_path, monkeypatch):
    """Redirect _reports_dir() to a temp directory for isolation."""
    reports_dir = tmp_path / "analytics-reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    import routers.analytics_report as mod

    monkeypatch.setattr(mod, "_reports_dir", lambda: reports_dir)
    return reports_dir


@pytest.fixture
def client(reports_in_tmp):
    """TestClient with reports dir redirected to tmp."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# _build_prompt
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    def test_contains_filter_label(self):
        prompt = _build_prompt(SAMPLE_ANALYTICS, "Last 7 days")
        assert "Last 7 days" in prompt

    def test_contains_key_stats(self):
        prompt = _build_prompt(SAMPLE_ANALYTICS, "All time")
        assert "10" in prompt  # total_sessions
        assert "1.23" in prompt  # estimated_cost_usd
        assert "45.0%" in prompt  # cache hit rate formatted

    def test_contains_top_tools(self):
        prompt = _build_prompt(SAMPLE_ANALYTICS, "All time")
        assert "Read" in prompt
        assert "Write" in prompt

    def test_contains_peak_hours(self):
        prompt = _build_prompt(SAMPLE_ANALYTICS, "All time")
        assert "9:00" in prompt

    def test_empty_tools_graceful(self):
        data = {**SAMPLE_ANALYTICS, "tools_used": {}}
        prompt = _build_prompt(data, "All time")
        assert "none" in prompt

    def test_empty_models_graceful(self):
        data = {**SAMPLE_ANALYTICS, "models_categorized": {}}
        prompt = _build_prompt(data, "All time")
        assert "none" in prompt

    def test_no_peak_hours_graceful(self):
        data = {**SAMPLE_ANALYTICS, "peak_hours": []}
        prompt = _build_prompt(data, "All time")
        assert "unknown" in prompt


# ---------------------------------------------------------------------------
# Disk helpers
# ---------------------------------------------------------------------------


class TestDiskHelpers:
    def test_save_and_load_report(self, reports_in_tmp):
        _save_report(
            "abc12345", "2025-01-15T10:00:00+00:00", "Last week", "Report body.", SAMPLE_ANALYTICS
        )

        reports = _load_all_reports()
        assert len(reports) == 1
        r = reports[0]
        assert r.id == "abc12345"
        assert r.filter_label == "Last week"
        assert r.preview == "Report body."
        assert r.stats_snapshot.total_sessions == 10
        assert r.stats_snapshot.estimated_cost_usd == pytest.approx(1.23)

    def test_preview_truncated_at_150_chars(self, reports_in_tmp):
        long_body = "x" * 300
        _save_report("aaa00001", "2025-01-15T10:00:00+00:00", "All", long_body, SAMPLE_ANALYTICS)

        reports = _load_all_reports()
        assert len(reports[0].preview) == 150

    def test_load_returns_most_recent_first(self, reports_in_tmp):
        _save_report(
            "old00001", "2025-01-10T10:00:00+00:00", "Old", "Old report.", SAMPLE_ANALYTICS
        )
        _save_report(
            "new00001", "2025-01-15T10:00:00+00:00", "New", "New report.", SAMPLE_ANALYTICS
        )

        # Set explicit mtimes so ordering is deterministic on all filesystems
        old_path = _find_report_file("old00001")
        new_path = _find_report_file("new00001")
        os.utime(old_path, (1_000_000.0, 1_000_000.0))
        os.utime(new_path, (2_000_000.0, 2_000_000.0))

        reports = _load_all_reports()
        ids = [r.id for r in reports]
        assert ids.index("new00001") < ids.index("old00001")

    def test_find_report_file_returns_path(self, reports_in_tmp):
        _save_report("find1234", "2025-01-15T10:00:00+00:00", "All", "Body.", SAMPLE_ANALYTICS)
        path = _find_report_file("find1234")
        assert path is not None
        assert path.exists()

    def test_find_report_file_missing_returns_none(self, reports_in_tmp):
        assert _find_report_file("doesnotexist") is None

    def test_load_skips_corrupt_files(self, reports_in_tmp):
        (reports_in_tmp / "2025-01-15-bad.json").write_text("not valid json{{{")
        reports = _load_all_reports()
        assert len(reports) == 0

    def test_prune_keeps_max_reports(self, reports_in_tmp):
        for i in range(MAX_REPORTS + 5):
            _save_report(
                f"rep{i:05d}",
                f"2025-01-{(i % 28) + 1:02d}T10:00:00+00:00",
                "All",
                f"Report {i}",
                SAMPLE_ANALYTICS,
            )
        _prune_old_reports()
        remaining = list(reports_in_tmp.glob("*.json"))
        assert len(remaining) == MAX_REPORTS


# ---------------------------------------------------------------------------
# POST /analytics/report
# ---------------------------------------------------------------------------


class TestGenerateReportEndpoint:
    def _mock_claude_success(
        self, text="## Summary\n\nYou've been productive.\n\n## Suggestions\n- Keep it up."
    ):
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = text
        mock.stderr = ""
        return mock

    def test_generate_report_happy_path(self, client, reports_in_tmp):
        with patch(
            "routers.analytics_report.subprocess.run", return_value=self._mock_claude_success()
        ):
            resp = client.post(
                "/analytics/report",
                json={"filter_label": "Last 7 days", "analytics": SAMPLE_ANALYTICS},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["filter_label"] == "Last 7 days"
        assert "## Summary" in data["report"]
        assert data["id"]
        assert data["preview"]
        assert data["stats_snapshot"]["total_sessions"] == 10

        # Report should be persisted on disk
        assert _find_report_file(data["id"]) is not None

    def test_generate_report_saved_and_listable(self, client, reports_in_tmp):
        with patch(
            "routers.analytics_report.subprocess.run", return_value=self._mock_claude_success()
        ):
            gen_resp = client.post(
                "/analytics/report",
                json={"filter_label": "All time", "analytics": SAMPLE_ANALYTICS},
            )
        report_id = gen_resp.json()["id"]

        list_resp = client.get("/analytics/report")
        assert list_resp.status_code == 200
        ids = [r["id"] for r in list_resp.json()]
        assert report_id in ids

    def test_generate_report_no_data_returns_400(self, client, reports_in_tmp):
        resp = client.post(
            "/analytics/report",
            json={"filter_label": "Empty", "analytics": {"total_sessions": 0}},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "no_data"

    def test_generate_report_claude_not_found_returns_503(self, client, reports_in_tmp):
        with patch(
            "routers.analytics_report.subprocess.run",
            side_effect=FileNotFoundError("claude not found"),
        ):
            resp = client.post(
                "/analytics/report",
                json={"filter_label": "All time", "analytics": SAMPLE_ANALYTICS},
            )
        assert resp.status_code == 503
        assert resp.json()["detail"] == "claude_not_found"

    def test_generate_report_timeout_returns_504(self, client, reports_in_tmp):
        import subprocess

        with patch(
            "routers.analytics_report.subprocess.run",
            side_effect=subprocess.TimeoutExpired("claude", 45),
        ):
            resp = client.post(
                "/analytics/report",
                json={"filter_label": "All time", "analytics": SAMPLE_ANALYTICS},
            )
        assert resp.status_code == 504
        assert resp.json()["detail"] == "timeout"

    def test_generate_report_rate_limit_returns_429(self, client, reports_in_tmp):
        mock = MagicMock()
        mock.returncode = 1
        mock.stdout = ""
        mock.stderr = "rate limit exceeded"
        with patch("routers.analytics_report.subprocess.run", return_value=mock):
            resp = client.post(
                "/analytics/report",
                json={"filter_label": "All time", "analytics": SAMPLE_ANALYTICS},
            )
        assert resp.status_code == 429
        assert resp.json()["detail"] == "rate_limit"

    def test_generate_report_auth_error_returns_503(self, client, reports_in_tmp):
        mock = MagicMock()
        mock.returncode = 1
        mock.stdout = ""
        mock.stderr = "unauthorized: invalid api key"
        with patch("routers.analytics_report.subprocess.run", return_value=mock):
            resp = client.post(
                "/analytics/report",
                json={"filter_label": "All time", "analytics": SAMPLE_ANALYTICS},
            )
        assert resp.status_code == 503
        assert resp.json()["detail"] == "auth_error"

    def test_generate_report_empty_stdout_returns_503(self, client, reports_in_tmp):
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = "   "  # whitespace only
        mock.stderr = ""
        with patch("routers.analytics_report.subprocess.run", return_value=mock):
            resp = client.post(
                "/analytics/report",
                json={"filter_label": "All time", "analytics": SAMPLE_ANALYTICS},
            )
        assert resp.status_code == 503
        assert resp.json()["detail"] == "generation_failed"


# ---------------------------------------------------------------------------
# GET /analytics/report/{id}
# ---------------------------------------------------------------------------


class TestGetReportEndpoint:
    def test_get_existing_report(self, client, reports_in_tmp):
        with patch(
            "routers.analytics_report.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="Full report text.", stderr=""),
        ):
            gen = client.post(
                "/analytics/report",
                json={"filter_label": "All time", "analytics": SAMPLE_ANALYTICS},
            )
        report_id = gen.json()["id"]

        resp = client.get(f"/analytics/report/{report_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == report_id
        assert data["report"] == "Full report text."

    def test_get_missing_report_returns_404(self, client, reports_in_tmp):
        resp = client.get("/analytics/report/00000000")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /analytics/report/{id}
# ---------------------------------------------------------------------------


class TestDeleteReportEndpoint:
    def test_delete_existing_report(self, client, reports_in_tmp):
        with patch(
            "routers.analytics_report.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="Report text.", stderr=""),
        ):
            gen = client.post(
                "/analytics/report",
                json={"filter_label": "All time", "analytics": SAMPLE_ANALYTICS},
            )
        report_id = gen.json()["id"]

        del_resp = client.delete(f"/analytics/report/{report_id}")
        assert del_resp.status_code == 204

        # Should be gone from disk and list
        assert _find_report_file(report_id) is None
        ids = [r["id"] for r in client.get("/analytics/report").json()]
        assert report_id not in ids

    def test_delete_missing_report_returns_404(self, client, reports_in_tmp):
        resp = client.delete("/analytics/report/00000000")
        assert resp.status_code == 404
