import re
import socket
from ulid import ULID
from devmem.db import connect

DEVICE_ID = socket.gethostname()

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
                result += s[i] + nxt            # unknown pair: keep as is
            i += 2                              # we used two characters
        else:
            result += s[i]                      # ordinary character: copy it
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
    
def ingest_spool(spool_path: str, conn) -> None:
    """
    conn
        SQLite connection
    """
    rows = []
    with open(spool_path) as f:
        for line in f:
            start_ms, dur_ms, exit_code, cwd, command = parse_line(line)
            rows.append(
                (str(ULID()), DEVICE_ID, "shell", start_ms, dur_ms, exit_code, cwd, command)
            )
    conn.executemany(
        "INSERT INTO events (id, device_id, type, start_ms, duration_ms, exit_code, cwd, command)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows
    )
    conn.commit()