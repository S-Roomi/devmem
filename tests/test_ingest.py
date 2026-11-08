import pytest

from devmem.db import connect
from devmem.ingest import ingest_spool, parse_line, unescape

# ---------- helpers ----------


def spool_line(command, start=1792805765980, dur=1000, code=0, cwd="/tmp"):
    """Build one spool line. `command` must already be in escaped (spool) form."""
    return f"{start}\t{dur}\t{code}\t{cwd}\t{command}\n"


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "test.db")  # throwaway database, never your real one
    yield c
    c.close()


def run_ingest(tmp_path, conn, *lines):
    """Write a fake spool file, ingest it, and return the spool path."""
    spool = tmp_path / "spool"
    spool.write_text("".join(lines), encoding="utf-8")
    ingest_spool(spool, conn)
    return spool


def commands(conn):
    """All stored commands, in the order they were inserted."""
    return [r[0] for r in conn.execute("SELECT command FROM events ORDER BY rowid")]


# ---------- unescape ----------
# Raw strings (r"...") let us write a backslash exactly as it appears in the spool.


@pytest.mark.parametrize(
    "spool_text, expected",
    [
        pytest.param("plain", "plain", id="plain-text-unchanged"),
        pytest.param("", "", id="empty-string"),
        pytest.param(r"one\ntwo", "one\ntwo", id="newline"),
        pytest.param(r"a\tb", "a\tb", id="tab"),
        pytest.param(r"a\\b", "a\\b", id="escaped-backslash"),
        pytest.param(r"a\\nb", "a\\nb", id="literal-backslash-then-n"),
        pytest.param(r"\\\\", "\\\\", id="two-backslashes"),
        pytest.param(r"\n\n", "\n\n", id="two-newlines-in-a-row"),
        pytest.param(r"\x", r"\x", id="unknown-escape-left-alone"),
        pytest.param("trailing\\", "trailing\\", id="lone-backslash-at-end"),
    ],
)
def test_unescape(spool_text, expected):
    assert unescape(spool_text) == expected


# ---------- parse_line ----------


def test_parse_line_normal():
    line = spool_line("git status")
    assert parse_line(line) == (1792805765980, 1000, 0, "/tmp", "git status")


def test_parse_line_without_trailing_newline():
    line = spool_line("ls").rstrip("\n")
    assert parse_line(line)[4] == "ls"


def test_parse_line_failed_command_keeps_exit_code():
    assert parse_line(spool_line("false", code=1))[2] == 1


def test_parse_line_folder_with_spaces():
    assert (
        parse_line(spool_line("ls", cwd="/home/me/my project"))[3]
        == "/home/me/my project"
    )


def test_parse_line_command_keeps_spaces_and_quotes():
    cmd = """echo "hello   world" 'x'"""
    assert parse_line(spool_line(cmd))[4] == cmd


def test_parse_line_unescapes_tab_and_newline():
    assert parse_line(spool_line(r"echo a\tb\nc"))[4] == "echo a\tb\nc"


def test_parse_line_too_few_fields_raises():
    with pytest.raises(ValueError):
        parse_line("1792805765980\t1000\n")


def test_parse_line_non_numeric_duration_raises():
    with pytest.raises(ValueError):
        parse_line("1792805765980\tabc\t0\t/tmp\tls\n")


# ---------- ingest_spool: things that should work today ----------


def test_ingest_inserts_one_row(tmp_path, conn):
    run_ingest(tmp_path, conn, spool_line("git status"))
    row = conn.execute(
        "SELECT type, start_ms, duration_ms, exit_code, cwd, command FROM events"
    ).fetchall()
    assert row == [("shell", 1792805765980, 1000, 0, "/tmp", "git status")]


def test_ingest_multiple_rows_keep_order(tmp_path, conn):
    run_ingest(
        tmp_path, conn, spool_line("first"), spool_line("second"), spool_line("third")
    )
    assert commands(conn) == ["first", "second", "third"]


def test_ingest_empty_file_does_nothing(tmp_path, conn):
    run_ingest(tmp_path, conn)  # no lines at all
    assert commands(conn) == []


def test_ingest_ids_are_unique(tmp_path, conn):
    run_ingest(tmp_path, conn, *[spool_line(f"cmd{i}") for i in range(50)])
    ids = [r[0] for r in conn.execute("SELECT id FROM events")]
    assert len(ids) == len(set(ids)) == 50


def test_ingest_awkward_characters_round_trip(tmp_path, conn):
    run_ingest(
        tmp_path,
        conn,
        spool_line(r"echo a\tb"),  # real tab
        spool_line(r"echo a\nb"),  # real newline
        spool_line(r"echo a\\nb"),  # literal backslash + n
    )
    assert commands(conn) == ["echo a\tb", "echo a\nb", "echo a\\nb"]


def test_ingest_unicode_command(tmp_path, conn):
    run_ingest(tmp_path, conn, spool_line("echo café ☕ 日本語"))
    assert commands(conn) == ["echo café ☕ 日本語"]


def test_ingest_very_long_command(tmp_path, conn):
    long_cmd = "x" * 10_000
    run_ingest(tmp_path, conn, spool_line(long_cmd))
    assert commands(conn) == [long_cmd]


def test_ingest_sql_looking_command_is_stored_as_plain_text(tmp_path, conn):
    nasty = """echo "it's"; DROP TABLE events; --"""
    run_ingest(tmp_path, conn, spool_line(nasty))
    assert commands(conn) == [nasty]  # stored as typed...
    assert (
        conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    )  # ...table still there


def test_ingest_many_rows(tmp_path, conn):
    run_ingest(tmp_path, conn, *[spool_line(f"cmd{i}", start=i) for i in range(1000)])
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1000


# ---------- ingest_spool: bad lines and remembering progress ----------


def test_ingest_skips_line_with_too_few_fields(tmp_path, conn):
    run_ingest(
        tmp_path, conn, spool_line("good one"), "garbage\n", spool_line("good two")
    )
    assert commands(conn) == ["good one", "good two"]


def test_ingest_skips_blank_line(tmp_path, conn):
    run_ingest(tmp_path, conn, spool_line("a"), "\n", spool_line("b"))
    assert commands(conn) == ["a", "b"]


def test_running_twice_does_not_duplicate(tmp_path, conn):
    spool = run_ingest(tmp_path, conn, spool_line("a"), spool_line("b"))
    ingest_spool(spool, conn)  # same file, second time
    assert commands(conn) == ["a", "b"]


def test_second_run_picks_up_only_new_lines(tmp_path, conn):
    spool = run_ingest(tmp_path, conn, spool_line("a"), spool_line("b"))
    with open(spool, "a", encoding="utf-8") as f:  # the hook appends a new command
        f.write(spool_line("c"))
    ingest_spool(spool, conn)
    assert commands(conn) == ["a", "b", "c"]


def test_half_written_last_line_waits_for_next_run(tmp_path, conn):
    spool = tmp_path / "spool"
    # second line is cut off: no newline at the end yet (the hook is mid-write)
    spool.write_text(
        spool_line("done") + "1792805765980\t1000\t0\t/tmp\tpart", encoding="utf-8"
    )
    ingest_spool(spool, conn)
    assert commands(conn) == ["done"]
    with open(spool, "a", encoding="utf-8") as f:  # the hook finishes the line
        f.write("ial\n")
    ingest_spool(spool, conn)
    assert commands(conn) == ["done", "partial"]


def test_bad_line_does_not_block_later_lines_on_next_run(tmp_path, conn):
    spool = run_ingest(tmp_path, conn, "garbage\n", spool_line("a"))
    with open(spool, "a", encoding="utf-8") as f:
        f.write(spool_line("b"))
    ingest_spool(spool, conn)
    assert commands(conn) == ["a", "b"]


def test_file_that_shrinks_is_read_again_from_the_start(tmp_path, conn):
    spool = run_ingest(tmp_path, conn, spool_line("old one"), spool_line("old two"))
    spool.write_text(spool_line("new"), encoding="utf-8")  # smaller than before
    ingest_spool(spool, conn)
    assert commands(conn)[-1] == "new"
