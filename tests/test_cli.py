import datetime as dt

import pytest
from typer.testing import CliRunner

from devmem.cli import app, default_spool_path, format_hit
from devmem.search import Hit

runner = CliRunner()


def spool_line(command, start=1792805765980, code=0, cwd="/tmp"):
    return f"{start}\t1000\t{code}\t{cwd}\t{command}\n"


@pytest.fixture
def env(tmp_path):
    """Point the CLI at throwaway files so your real history is never touched."""
    return {
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "DEVMEM_SPOOL": str(tmp_path / "spool"),
    }


def write_spool(env, *lines):
    from pathlib import Path

    Path(env["DEVMEM_SPOOL"]).write_text("".join(lines), encoding="utf-8")


def run(env, *args):
    return runner.invoke(app, list(args), env=env)


# ---------- format_hit (pure function, no database needed) ----------


def test_format_hit_ok():
    ms = 1792805765980
    line = format_hit(Hit(ms, 0, "/tmp", "git status"))
    assert dt.datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M") in line
    assert "ok" in line and "/tmp" in line and line.endswith("git status")


def test_format_hit_failed_shows_exit_code():
    assert "exit 2" in format_hit(Hit(1, 2, "/tmp", "make"))


def test_format_hit_unknown_exit_code():
    assert "?" in format_hit(Hit(1, None, "/tmp", "make"))


def test_format_hit_abbreviates_home(monkeypatch):
    monkeypatch.setenv("HOME", "/home/me")
    assert "~/proj" in format_hit(Hit(1, 0, "/home/me/proj", "ls"))
    assert "/home/meow" in format_hit(
        Hit(1, 0, "/home/meow", "ls")
    )  # not a false match


def test_format_hit_keeps_multiline_commands_on_one_line():
    line = format_hit(Hit(1, 0, "/tmp", "echo a\nb\tc"))
    assert "\n" not in line and "\t" not in line
    assert "echo a\\nb\\tc" in line


# ---------- default_spool_path ----------


def test_spool_path_prefers_devmem_spool(monkeypatch):
    monkeypatch.setenv("DEVMEM_SPOOL", "/x/spool")
    assert str(default_spool_path()) == "/x/spool"


def test_spool_path_falls_back_to_xdg_state(monkeypatch):
    monkeypatch.delenv("DEVMEM_SPOOL", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", "/state")
    assert str(default_spool_path()) == "/state/devmem/spool"


# ---------- dm ingest ----------


def test_ingest_reports_count_then_zero(env):
    write_spool(env, spool_line("a"), spool_line("b"))
    assert "Ingested 2 new commands." in run(env, "ingest").output
    assert "Ingested 0 new commands." in run(env, "ingest").output


def test_ingest_singular(env):
    write_spool(env, spool_line("a"))
    assert "Ingested 1 new command." in run(env, "ingest").output


def test_ingest_with_missing_spool_is_not_an_error(env):
    result = run(env, "ingest")
    assert result.exit_code == 0 and "Ingested 0" in result.output


# ---------- dm search ----------


def test_search_finds_command(env):
    write_spool(env, spool_line("git rebase -i"), spool_line("ls -la"))
    result = run(env, "search", "rebase")
    assert result.exit_code == 0
    assert "git rebase -i" in result.output
    assert "ls -la" not in result.output


def test_search_several_words_without_quotes(env):
    write_spool(env, spool_line("git rebase -i"), spool_line("git status"))
    result = run(env, "search", "git", "rebase")
    assert "git rebase -i" in result.output
    assert "git status" not in result.output


def test_search_picks_up_new_history_without_running_ingest(env):
    write_spool(env, spool_line("first"))
    run(env, "search", "first")
    write_spool(env, spool_line("first"), spool_line("brand new thing"))
    assert "brand new thing" in run(env, "search", "brand").output


def test_search_no_match(env):
    write_spool(env, spool_line("ls"))
    assert "No matches." in run(env, "search", "kubernetes").output


def test_search_limit(env):
    write_spool(env, *[spool_line(f"docker run {i}", start=i) for i in range(10)])
    result = run(env, "search", "docker", "--limit", "3")
    assert result.output.count("docker run") == 3


def test_search_shows_failures(env):
    write_spool(env, spool_line("make build", code=2))
    assert "exit 2" in run(env, "search", "make").output


def test_search_dash_words_after_double_dash(env):
    write_spool(env, spool_line("rm -rf build"))
    assert "rm -rf build" in run(env, "search", "--", "-rf").output


def test_search_without_words_is_a_usage_error(env):
    assert run(env, "search").exit_code != 0


# ---------- dm recent ----------


def test_recent_newest_first_and_limited(env):
    write_spool(
        env,
        spool_line("old", start=1),
        spool_line("mid", start=2),
        spool_line("new", start=3),
    )
    out = run(env, "recent", "-n", "2").output
    assert "new" in out and "mid" in out and "old" not in out
    assert out.index("new") < out.index("mid")


def test_recent_on_empty_history(env):
    assert "No matches." in run(env, "recent").output


# ---------- help ----------


def test_no_arguments_shows_help(env):
    assert "Usage" in run(env).output


def test_help_lists_commands(env):
    out = run(env, "--help").output
    assert "ingest" in out and "search" in out and "recent" in out
