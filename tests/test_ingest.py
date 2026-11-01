from devmem.ingest import unescape, ingest_spool
from devmem.db import connect

def test_unescape_newline():
    assert unescape("one\\ntwo") == "one\ntwo"

def test_unescape_keeps_literal_backslash_n():
    # the spool holds a\\nb, which means you typed a\nb
    assert unescape("a\\\\nb") == "a\\nb"

def test_ingest_inserts_one_row(tmp_path):
    tmp_spool = tmp_path / "spool"
    tmp_spool.write_text("1792805765980\t1000\t0\t/tmp\tgit status\n")
    
    conn = connect(tmp_path / "test.db")
    ingest_spool(tmp_spool, conn)
    
    rows = conn.execute("SELECT command, exit_code FROM events").fetchall()
    
    conn.close()
    
    assert rows == [("git status", 0)]
    