from pathlib import Path

import pytest
from typer.testing import CliRunner

from devmem.cli import app

runner = CliRunner()


def good_line(command, start=1792805765980):
    return f"{start}\t1000\t0\t/tmp\t{command}\n"


@pytest.fixture
def env(tmp_path):
    return {
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "DEVMEM_SPOOL": str(tmp_path / "spool"),
    }


def write_spool(env, text):
    Path(env["DEVMEM_SPOOL"]).write_text(text, encoding="utf-8")


def run(env, *args):
    return runner.invoke(app, list(args), env=env)


def test_healthy_after_ingest(env):
    write_spool(env, good_line("ls") + good_line("pwd"))
    run(env, "ingest")
    out = run(env, "status").output
    assert "events: 2, searchable: 2" in out
    assert "No problems found." in out


def test_missing_spool_is_explained(env):
    out = run(env, "status").output
    assert "NOT FOUND" in out
    assert "does not exist" in out


def test_empty_spool_is_explained(env):
    write_spool(env, "")
    assert "hook is not recording" in run(env, "status").output


def test_before_first_ingest(env):
    write_spool(env, good_line("ls"))
    out = run(env, "status").output
    assert "not created yet" in out
    assert "have not been ingested yet" in out


def test_status_does_not_create_the_database(env):
    write_spool(env, good_line("ls"))
    run(env, "status")
    assert not (Path(env["XDG_DATA_HOME"]) / "devmem" / "devmem.db").exists()


def test_old_hook_format_is_detected(env):
    write_spool(
        env, "1000\t0\t/tmp\tls\n1000\t0\t/tmp\tpwd\n"
    )  # 4 fields: no start time
    out = run(env, "status").output
    assert "2 line(s) with 4 fields" in out
    assert "hook is probably out of date" in out


def test_lines_read_but_nothing_stored(env):
    write_spool(env, "1000\t0\t/tmp\tls\n")
    run(env, "ingest")  # skips the 4-field line
    out = run(env, "status").output
    assert "events: 0" in out
    assert "no events were stored" in out


def test_new_lines_after_ingest_are_reported_as_pending(env):
    write_spool(env, good_line("ls"))
    run(env, "ingest")
    write_spool(env, good_line("ls") + good_line("pwd"))
    assert "have not been ingested yet" in run(env, "status").output
