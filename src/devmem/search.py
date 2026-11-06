import re
from typing import NamedTuple

class Hit(NamedTuple):
    start_ms: int
    exit_code: int
    cwd: str | None
    command: str

def turn_into_fts_query(text: str) -> str:
    """Turn whatever was passed into a safe FTS5 query

    Args:
        text (str): What should be searched in FTS5 table

    Returns:
        str: A safe string to use when querying
    """
    words = re.findall(r"\w+", text)
    return " ".join(f'"{char}"*' for char in words)

def search(conn, text: str, limit:int = 20) -> list[Hit]:
    """Returns up to limit of matching commands in FTS5 table (newest first).

    Args:
        conn (_type_): SQLITE connection
        text (str): command or text to search for
        limit (int, optional): Number of results to return. Defaults to 20.

    Returns:
        list[Hit]: List of results with information that was store in the table 
    """
    query = turn_into_fts_query(text)
    if not query:
        return []
    
    rows = conn.execute(
        """
        SELECT e.start_ms, e.exit_code, e.cwd, e.command
        FROM events_fts
        JOIN events AS e ON e.id = events_fts.event_id
        WHERE events_fts MATCH ?
        ORDER BY e.start_ms DESC
        LIMIT ?
        """,
        (query, limit)
    ).fetchall()
    
    # unpack all tuples into arguments for Hit object
    return [Hit(*row) for row in rows]