import os
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def default_db_path() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share" ))
    return base / "devmen" / "devmen.db"

def migrate(conn: sqlite3.Connection) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(f.name.split("_")[0])
        if version <= current:
            continue
        
        conn.executescript(
            f"BEGIN;\n{f.read_text()}\nPRAGMA user_version = {version};\nCOMMIT;"
        )

def connect(path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(path) if path else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode = WAL")
    migrate(conn)
    return conn