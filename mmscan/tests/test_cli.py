from typer.testing import CliRunner

from mmscan.cli import app


def test_help_lists_commands():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ["check", "scan", "enrich", "score", "report", "run", "quota"]:
        assert name in result.output
