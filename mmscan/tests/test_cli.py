from typer.testing import CliRunner

from mmscan.cli import app


def test_help_lists_commands():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ["check", "scan", "enrich", "score", "report", "run", "watch", "notify", "quota"]:
        assert name in result.output


def test_check_dry_run_sends_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["check", "--dry-run"])
    assert result.exit_code == 0
    assert "Would send 4 requests" in result.output
    assert not (tmp_path / "data").exists()


def test_check_without_key_fails_cleanly(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SEATS_AERO_API_KEY", raising=False)
    result = CliRunner().invoke(app, ["check"])
    assert result.exit_code == 1
    assert "SEATS_AERO_API_KEY is not set" in result.output
