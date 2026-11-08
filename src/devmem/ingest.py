import os
import socket
from pathlib import Path
from ulid import ULID
from devmem.db import connect
from typing import NamedTuple

DEVICE_ID = socket.gethostname()

INSERT_EVENT = (
    "INSERT INTO events (id, device_id, type, start_ms, duration_ms, exit_code, cwd, command)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)

class IngestResult(NamedTuple):
    added: int       # rows inserted
    skipped: int     # non-blank lines that could not be parsed
    missing: bool    # the spool file does not exist

def unescape(s: str) -> str:
    result = ""
    i = 0
    while i < len(s):   
        if s[i] == "\\" and i + 1 < len(s):    # a backslash with something after it
            nxt = s[i + 1]
            if nxt == "n":
                result += "\n"                  # \n  ->  real line break
            elif nxt == "t":
                result += "\t"                  # \t  ->  real tab
            elif nxt == "\\":
                result += "\\"                  # \\  ->  one real backslash
            else:
                result += s[i] + nxt
            i += 2
        else:
            result += s[i]                      # ordinary character, copy it
            i += 1
    return result

def parse_line(line: str) -> tuple[int, int, int, str, str]:
    fields = line.rstrip('\n').split('\t', 4)
    start_ms, dur_ms, exit_code, cwd, command = fields
    return (
        int(start_ms),
        int(dur_ms),
        int(exit_code),
        cwd,
        unescape(command)
    )
    
 
 
def ingest_spool(spool_path, conn) -> IngestResult:
    """Insert any NEW complete lines from the spool file."""
    spool_path = Path(spool_path)
    if not spool_path.exists():
        return IngestResult(0, 0, True)
    key = str(spool_path.resolve())
 
    # Find previous byte offset (where we stopped reading last time)
    row = conn.execute(
        "SELECT byte_offset FROM ingest_state WHERE spool_path = ?", (key,)
    ).fetchone()
    offset = row[0] if row else 0
 
    # Read starting from were we left off
    with open(spool_path, "rb") as f:
        size = f.seek(0, os.SEEK_END)
        if size < offset:
            offset = 0
        f.seek(offset)
        data = f.read()
 
    # Only trust COMPLETE lines. The hook may be mid-write, so the last piece
    # might be half a line; leave it for next time.
    complete_len = data.rfind(b"\n") + 1
    complete = data[:complete_len]
    new_offset = offset + complete_len
 
    # Turn each line into a row
    rows = []
    skipped = 0
    for raw in complete.split(b"\n")[:-1]:
        try:
            start_ms, dur_ms, exit_code, cwd, command = parse_line(
                raw.decode("utf-8", errors="replace")
            )
        except ValueError:
            if raw.strip():     # blank lines are harmless
                skipped += 1
            continue
        rows.append(
            (str(ULID()), DEVICE_ID, "shell", start_ms, dur_ms, exit_code, cwd, command)
        )
 
    # Save the rows AND the new offset together
    with conn:
        conn.executemany(INSERT_EVENT, rows)
        conn.execute(
            "INSERT OR REPLACE INTO ingest_state (spool_path, byte_offset) VALUES (?, ?)",
            (key, new_offset),
        )
    return IngestResult(len(rows), skipped, False)
