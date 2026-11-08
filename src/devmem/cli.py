import datetime as dt
import os
from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import Annotated

import typer

from devmem.db import connect, default_db_path
from devmem.ingest import IngestResult, ingest_spool
from devmem.search import Hit, recent, search

app = typer.Typer()


def default_spool_path() -> Path:
    if os.environ.get("DEVMEM_SPOOL"):
        return Path(os.environ["DEVMEM_SPOOL"])
    state = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state) / "devmem" / "spool"


def format_hit(hit: Hit) -> str:
    """One plain-text line for one command."""
    when = dt.datetime.fromtimestamp(hit.start_ms / 1000).strftime("%Y-%m-%d %H:%M")
    if hit.exit_code is None:
        status = "?"
    elif hit.exit_code == 0:
        status = "ok"
    else:
        status = f"exit {hit.exit_code}"

    cwd = hit.cwd or "?"
    home = str(Path.home())
    if cwd == home or cwd.startswith(home + os.sep):
        cwd = "~" + cwd[len(home) :]

    command = hit.command.replace("\n", "\\n").replace(
        "\t", "\\t"
    )  # keep it on one line
    return f"{when}  {status:<7} {cwd}  {command}"


def warn_about_problems(result: IngestResult, spool: Path) -> None:
    """Say so (on stderr) when the spool is missing or has lines we could not read."""
    if result.missing:
        typer.secho(
            f"Warning: spool file not found: {spool}", fg=typer.colors.YELLOW, err=True
        )
    if result.skipped:
        typer.secho(
            f"Warning: skipped {result.skipped} unreadable line(s) in {spool}",
            fg=typer.colors.YELLOW,
            err=True,
        )


def print_hits(hits: list[Hit]) -> None:
    if not hits:
        typer.echo("No matches.")
        return
    for hit in hits:
        failed = hit.exit_code not in (None, 0)
        typer.secho(format_hit(hit), fg=typer.colors.RED if failed else None)


@app.command()
def ingest(
    spool: Annotated[
        Path | None, typer.Option(help="Spool file to read (default: the hook's file).")
    ] = None,
) -> None:
    """Load new commands from the spool file into the database."""
    with closing(connect()) as conn:
        added = ingest_spool(spool or default_spool_path(), conn)
    typer.echo(f"Ingested {added} new command{'' if added == 1 else 's'}.")


# The function is called search_cmd so it doesn't clash with the imported search();
# the name given to @app.command() is what the user types.
@app.command("search")
def search_cmd(
    words: Annotated[
        list[str], typer.Argument(help="Words to look for (no quotes needed).")
    ],
    limit: Annotated[
        int, typer.Option("--limit", "-n", help="Maximum number of results.")
    ] = 20,
) -> None:
    """Search recorded commands, newest first. Picks up new history automatically."""
    with closing(connect()) as conn:
        ingest_spool(default_spool_path(), conn)
        hits = search(conn, " ".join(words), limit=limit)
    print_hits(hits)


@app.command("recent")
def recent_cmd(
    limit: Annotated[
        int, typer.Option("--limit", "-n", help="How many commands to show.")
    ] = 20,
) -> None:
    """Show your most recent commands."""
    with closing(connect()) as conn:
        ingest_spool(default_spool_path(), conn)
        hits = recent(conn, limit=limit)
    print_hits(hits)


@app.command()
def status() -> None:
    """Show what devmem can see: the spool, the database, and how far ingest has got."""
    spool = default_spool_path()
    db_path = default_db_path()
    hints: list[str] = []

    # --- the spool file the shell hook writes ---
    size = 0
    if spool.exists():
        data = spool.read_bytes()
        size = len(data)
        lines = [ln for ln in data.split(b"\n") if ln.strip()]
        by_fields = Counter(ln.count(b"\t") + 1 for ln in lines)
        typer.echo(f"Spool     {spool}  ({size:,} bytes, {len(lines)} lines)")
        for n_fields, count in sorted(by_fields.items()):
            note = "" if n_fields == 5 else "   <-- expected 5"
            typer.echo(f"          {count} line(s) with {n_fields} fields{note}")
        bad = sum(c for n, c in by_fields.items() if n != 5)
        if bad:
            hints.append(
                f"{bad} spool line(s) do not have 5 tab-separated fields "
                "(start, duration, exit code, folder, command). "
                "The hook is probably out of date: use the latest devmem.zsh."
            )
        if size == 0:
            hints.append(
                "The spool is empty, so the hook is not recording. "
                "Is devmem.zsh sourced in ~/.zshrc, and did you open a new terminal?"
            )
    else:
        typer.echo(f"Spool     {spool}  (NOT FOUND)")
        hints.append(
            "The spool file does not exist. The hook may be writing somewhere else: "
            "check DEVMEM_SPOOL and the path in devmem.zsh."
        )

    # --- the database (not created by this command) ---
    events = indexed = None
    offset = 0
    if db_path.exists():
        with closing(connect(db_path)) as conn:
            events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            indexed = conn.execute("SELECT COUNT(*) FROM events_fts").fetchone()[0]
            row = conn.execute(
                "SELECT byte_offset FROM ingest_state WHERE spool_path = ?",
                (str(spool.resolve()),),
            ).fetchone()
            offset = row[0] if row else 0
        typer.echo(f"Database  {db_path}  (events: {events}, searchable: {indexed})")
    else:
        typer.echo(f"Database  {db_path}  (not created yet)")

    if spool.exists():
        typer.echo(f"Ingest    read {offset:,} of {size:,} bytes of the spool")
        if size > offset:
            hints.append(
                f"{size - offset:,} bytes of the spool have not been ingested yet. Run: dm ingest"
            )
    if events == 0 and offset > 0:
        hints.append(
            "The spool was read but no events were stored, so its lines were unreadable "
            "(see the field counts above)."
        )
    if events is not None and events != indexed:
        hints.append(
            f"The search index has {indexed} entries for {events} events; they should match."
        )

    typer.echo()
    if not hints:
        typer.echo("No problems found.")
    for hint in hints:
        typer.secho(f"Problem: {hint}", fg=typer.colors.YELLOW)


if __name__ == "__main__":
    app()
