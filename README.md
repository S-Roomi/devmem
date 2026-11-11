# devmem

A local-first command-line memory for developers. devmem records the commands you run in
your terminal and lets you search them later. All data stays on your machine.

> **Status:** early development. Shell capture, ingest, keyword search and the `dm` CLI
> work and are tested.

## How it works

```
terminal --(zsh hook)--> spool file --(dm ingest)--> SQLite database --(dm search)--> results
```

1. **Hook** (`devmem.zsh`) runs inside zsh. After each command it appends one
   tab-separated line to a spool file: start time, duration, exit code, working
   directory and command. Special characters are escaped so each event is one line.
   The hook never prints errors and skips commands that start with a space.
2. **Ingest** (`src/devmem/ingest.py`) reads only new, complete lines from the spool
   using a stored byte offset, skips malformed lines, and writes rows and the new offset
   in a single transaction, so repeated runs never create duplicates.
3. **Database** (`src/devmem/db.py`) is SQLite in WAL mode with an FTS5 full-text index.
   Numbered SQL migrations in `src/devmem/migrations/` are applied automatically.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or `venv` + `pip`
- zsh 5.x
- SQLite with FTS5 (included in most Python builds). To check:

  ```bash
  python3 -c "import sqlite3; sqlite3.connect(':memory:').execute('create virtual table t using fts5(x)'); print('FTS5 OK')"
  ```

## Installation

```bash
git clone https://github.com/S-Roomi/devmem.git
cd devmem
uv sync
```

Then enable the shell hook by adding this near the end of `~/.zshrc` and opening a new
terminal:

```zsh
source /path/to/devmem/devmem.zsh
```

## Usage

```bash
dm ingest                  # load new commands from the spool into the database
dm search docker compose   # search recorded commands, newest first
dm recent -n 50            # show the 50 most recent commands
dm status                  # diagnose the spool, database and ingest progress
```

Run these with `uv run dm ...` if the virtualenv is not activated. `search` and `recent`
ingest new history automatically before running. Failed commands are shown in red.

### Configuration

| File     | Default location                  | Override                             |
|----------|-----------------------------------|--------------------------------------|
| Spool    | `~/.local/state/devmem/spool`     | `DEVMEM_SPOOL` (or `XDG_STATE_HOME`) |
| Database | `~/.local/share/devmem/devmem.db` | `XDG_DATA_HOME`                      |

## Development

```bash
uv run pytest      # run the test suite
uv run ruff check  # lint
uv run mypy src    # type-check
```

Tests use temporary files and databases and never touch your real history.

## Privacy

- The spool and database contain everything you type, including any secrets passed on
  the command line. Both are created with owner-only permissions.
- Secret redaction is not implemented yet. Prefix a command with a space to keep it out
  of the log (e.g. ` export TOKEN=...`).
- Never commit `*.db`, `*.db-wal`, `*.db-shm` or the spool file; they are in `.gitignore`.
- Nothing leaves your machine.

## Known limitations

- zsh only.
- The git branch and repository are not recorded.
- `device_id` is currently the hostname, which is not guaranteed to be unique.
- Long-running commands (such as an open `vim` session) are logged only when they exit.
