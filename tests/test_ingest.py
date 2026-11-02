from devmem.ingest import unescape, ingest_spool, parse_line
from devmem.db import connect


# --- helper functions ---
def spool_line(command, start=1792805765980, dur=1000, code=0, cwd="/tmp"):
    return f"{start}\t{dur}\t{code}\t{cwd}\t{command}\n"


def test_unescape_newline():
    assert unescape("one\\ntwo") == "one\ntwo"

def test_unescape_keeps_literal_backslash_n():
    assert unescape("a\\\\nb") == "a\\nb"



# --- parse_line test cases --- 
def test_parse_line_normal():
    line = spool_line("git status")
    assert parse_line(line) == (1792805765980, 1000, 0, "/tmp", "git status")

def test_parse_line_without_trailing_newline():
    line = spool_line("ls").rstrip("\n")
    assert parse_line(line)[4] == "ls"
 
 
def test_parse_line_failed_command_keeps_exit_code():
    assert parse_line(spool_line("false", code=1))[2] == 1


def test_ingest_inserts_one_row(tmp_path):
    tmp_spool = tmp_path / "spool"
    tmp_spool.write_text("1792805765980\t1000\t0\t/tmp\tgit status\n")
    
    conn = connect(tmp_path / "test.db")
    ingest_spool(tmp_spool, conn)
    
    rows = conn.execute("SELECT command, exit_code FROM events").fetchall()
    
    conn.close()
    
    assert rows == [("git status", 0)]

