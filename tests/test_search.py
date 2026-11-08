import sqlite3

import pytest

from devmem.db import MIGRATIONS_DIR, connect
from devmem.ingest import ingest_spool
from devmem.search import search, turn_into_fts_query

# ---------- helpers ----------


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "test.db")
    yield c
    c.close()


_counter = 0


def add(conn, command, start_ms=1000, exit_code=0, cwd="/tmp"):
    """Insert one event directly (bypasses ingest, so search is tested on its own)."""
    global _counter
    _counter += 1
    conn.execute(
        "INSERT INTO events (id, device_id, type, start_ms, duration_ms, exit_code, cwd, command)"
        " VALUES (?, 'dev', 'shell', ?, 10, ?, ?, ?)",
        (f"id{_counter}", start_ms, exit_code, cwd, command),
    )
    conn.commit()


def found(conn, text, **kw):
    return [h.command for h in search(conn, text, **kw)]


# ---------- turn_into_fts_query ----------


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("rebase", '"rebase"*'),
        ("git rebase", '"git"* "rebase"*'),
        (
            "git commit -m",
            '"git"* "commit"* "m"*',
        ),  # the dash is dropped, not a syntax error
        ("", ""),
        ("   ", ""),
        ("--- !!!", ""),
    ],
)
def test_turn_into_fts_query(typed, expected):
    assert turn_into_fts_query(typed) == expected


# ---------- basic searching ----------


def test_finds_a_word(conn):
    add(conn, "git rebase -i HEAD~3")
    add(conn, "ls -la")
    assert found(conn, "rebase") == ["git rebase -i HEAD~3"]


def test_no_match_returns_empty_list(conn):
    add(conn, "ls -la")
    assert found(conn, "kubernetes") == []


def test_search_is_case_insensitive(conn):
    add(conn, "Docker Compose UP")
    assert found(conn, "docker") == ["Docker Compose UP"]
    assert found(conn, "COMPOSE") == ["Docker Compose UP"]


def test_punctuation_splits_words(conn):
    add(conn, "docker-compose down")
    assert found(conn, "compose") == ["docker-compose down"]


def test_partial_word_matches_by_prefix(conn):
    add(conn, "git rebase -i")
    assert found(conn, "rebas") == ["git rebase -i"]


def test_all_words_must_match(conn):
    add(conn, "git rebase -i")
    add(conn, "git status")
    assert found(conn, "git rebase") == ["git rebase -i"]


def test_words_can_appear_in_any_order(conn):
    add(conn, "git rebase -i")
    assert found(conn, "rebase git") == ["git rebase -i"]


def test_underscored_names(conn):
    add(conn, "python my_script.py --verbose")
    assert found(conn, "my_script") == ["python my_script.py --verbose"]


def test_unicode(conn):
    add(conn, "echo café")
    assert found(conn, "café") == ["echo café"]


# ---------- ordering, limits, returned fields ----------


def test_newest_first(conn):
    add(conn, "docker old", start_ms=1000)
    add(conn, "docker new", start_ms=3000)
    add(conn, "docker middle", start_ms=2000)
    assert found(conn, "docker") == ["docker new", "docker middle", "docker old"]


def test_limit(conn):
    for i in range(10):
        add(conn, f"docker run {i}", start_ms=i)
    assert len(found(conn, "docker", limit=3)) == 3


def test_hit_has_all_fields(conn):
    add(conn, "make build", start_ms=1792805765980, exit_code=2, cwd="/home/me/proj")
    hit = search(conn, "make")[0]
    assert (hit.start_ms, hit.exit_code, hit.cwd, hit.command) == (
        1792805765980,
        2,
        "/home/me/proj",
        "make build",
    )


# ---------- hostile or odd input must never crash ----------


@pytest.mark.parametrize(
    "typed",
    [
        "",
        "   ",
        "-i",
        '"',
        '"unbalanced',
        "git commit -m",
        "AND",
        "OR",
        "NOT",
        "foo:bar",
        "*",
        "(",
        ")",
        "a AND",
        "NEAR(a b)",
        "'; DROP TABLE events; --",
    ],
)
def test_odd_input_does_not_crash(conn, typed):
    add(conn, "git commit -m 'fix'")
    search(conn, typed)  # passing means: no exception
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1


def test_command_words_that_look_like_operators_are_searchable(conn):
    add(conn, "echo and or not")
    assert found(conn, "and") == ["echo and or not"]


# ---------- the index stays in sync with the events table ----------


def test_rows_added_by_ingest_are_searchable(tmp_path, conn):
    spool = tmp_path / "spool"
    spool.write_text(
        "1792805765980\t1000\t0\t/tmp\tkubectl get pods\n", encoding="utf-8"
    )
    ingest_spool(spool, conn)
    assert found(conn, "kubectl") == ["kubectl get pods"]


def test_deleted_rows_disappear_from_search(conn):
    add(conn, "secret command")
    conn.execute("DELETE FROM events")
    conn.commit()
    assert found(conn, "secret") == []


def test_updated_command_is_reindexed(conn):
    add(conn, "old words")
    conn.execute("UPDATE events SET command = 'new words'")
    conn.commit()
    assert found(conn, "old") == []
    assert found(conn, "new") == ["new words"]


def test_rows_that_existed_before_the_migration_get_indexed(tmp_path):
    # Build a database by hand with only migrations 1 and 2, add a row, then apply 3.
    raw = sqlite3.connect(tmp_path / "old.db")
    for name in ("0001_create_events.sql", "0002_create_ingest_state.sql"):
        raw.executescript((MIGRATIONS_DIR / name).read_text())
    raw.execute(
        "INSERT INTO events (id, device_id, type, start_ms, command)"
        " VALUES ('x', 'dev', 'shell', 1, 'terraform apply')"
    )
    raw.commit()
    raw.executescript((MIGRATIONS_DIR / "0003_add_fts.sql").read_text())
    assert found(raw, "terraform") == ["terraform apply"]
    raw.close()
