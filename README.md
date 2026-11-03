# devmem

A local-first command-line memory for developers. devmem records what you do in the
terminal (shell commands now; git and notes later), keeps secrets out of it, and lets
you search it later, first by keyword and then by meaning. Everything stays on your
machine unless you turn on sync.

> **Status: early development (M1 in progress).** The shell hook, database and ingest
> pipeline work and are tested. Search and the `dm` command are the next things to build.

## How it works

```
terminal --(zsh hook)--> spool file --(dm ingest)--> SQLite database --(dm search)--> you
 preexec/precmd          one line per       parse, unescape,        events table +
                         command            skip bad lines          full-text index (next)
```

1. **Hook** (`devmem.zsh`): runs inside your shell. Before a command it remembers the
   command, start time and folder; after it finishes it appends one tab-separated line
   to the spool file: `start_ms, duration_ms, exit_code, cwd, command`.
   Tabs, newlines and backslashes in the command are escaped so each event is one line.
   The hook is pure zsh, never prints errors, and skips commands that start with a space.
2. **Ingest** (`src/devmem/ingest.py`): reads only the *new, complete* lines of the spool
   (it remembers a byte offset), skips malformed lines, and inserts rows into SQLite.
   Rows and the new offset are saved in one transaction, so running it twice never
   duplicates anything.
3. **Database** (`src/devmem/db.py`): SQLite in WAL mode. Schema changes are numbered
   SQL files in `src/devmem/migrations/`, applied automatically in order on connect.

## Project layout

```
devmem/
  pyproject.toml
  README.md
  devmem.zsh                         shell hook (source it from ~/.zshrc)
  src/devmem/
    __init__.py
    db.py                            connect() + migrations
    ingest.py                        unescape, parse_line, ingest_spool
    migrations/
      0001_create_events.sql
      0002_create_ingest_state.sql
  tests/
    test_ingest.py
```

## Requirements

| What | Version | Notes |
|---|---|---|
| Python | 3.12+ | |
| [uv](https://docs.astral.sh/uv/) | recent | Manages the virtualenv and dependencies. Plain `venv` + `pip` also works. |
| zsh | 5.x | Needed for the capture hook. Bash support is planned. |
| SQLite | 3.9+ with FTS5 | Bundled with most Python builds (see check below). |

Python packages used **today**:

| Package | Used for |
|---|---|
| `python-ulid` | Sortable unique IDs for events |
| `pytest` (dev) | Tests |

Check that your Python's SQLite has full-text search:

```bash
python3 -c "import sqlite3; sqlite3.connect(':memory:').execute('create virtual table t using fts5(x)'); print('FTS5 OK')"
```

Packages for **upcoming** milestones (add them when you get there):

| Package | Milestone | Used for |
|---|---|---|
| `typer` | M1 | The `dm` command-line interface |
| `fastembed` | M3 | Local embedding model |
| `sqlite-vec` | M3 | Vector search inside SQLite (NumPy brute force as fallback) |
| `hypothesis` (dev) | M4 | Property-based tests for sync |
| `fastapi`, `uvicorn` | M4 | Sync relay server |
| `pynacl` | M4 (optional) | End-to-end encryption |
| `textual` | M5 | Terminal UI |

Check current versions and licenses (especially the embedding model and `sqlite-vec`)
when you reach M3.

## Setup

```bash
git clone <your-repo-url> devmem
cd devmem

uv sync                       # creates .venv and installs the project
uv add python-ulid            # if not already in pyproject.toml
uv add --dev pytest

uv run pytest                 # everything should pass
```

Without uv:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e . python-ulid pytest
pytest
```

### Turn on the shell hook

Add this near the **end** of `~/.zshrc` (use the real path to the file), then open a new terminal:

```zsh
source /path/to/devmem/devmem.zsh
```

Use your terminal normally, then check the spool:

```bash
cat ~/.local/state/devmem/spool
```

Defaults (override with the environment variables shown):

| File | Default location | Override |
|---|---|---|
| Spool | `~/.local/state/devmem/spool` | `DEVMEM_SPOOL` (or `XDG_STATE_HOME`) |
| Database | `~/.local/share/devmem/devmem.db` | `XDG_DATA_HOME` |

## Running it today

The `dm` command does not exist yet (it is the next step). Until then, load your spool
into the database with:

```bash
uv run python -c "from devmem.db import connect; from devmem.ingest import ingest_spool; print(ingest_spool('$HOME/.local/state/devmem/spool', connect()), 'new rows')"
```

Run it twice: the second run should print `0 new rows`. To look at the data:

```bash
sqlite3 ~/.local/share/devmem/devmem.db \
  "SELECT datetime(start_ms/1000,'unixepoch'), exit_code, cwd, command FROM events ORDER BY start_ms DESC LIMIT 10;"
```

Once the CLI exists, this becomes:

```bash
uv run dm ingest
uv run dm search "docker compose"
```

## Tests

```bash
uv run pytest            # all tests
uv run pytest -v         # one line per test
uv run pytest -k unicode # only tests whose name contains "unicode"
```

Tests use temporary files and databases; they never touch your real history.

## Privacy

- The spool and database contain **everything you type**, including any secrets you put
  on a command line. Both are created owner-only (directory `700`, spool `600`).
- **Secret redaction does not exist yet (M2).** Until it does, start a command with a
  space to keep it out of the log (e.g. ` export TOKEN=...`).
- Never commit `*.db`, `*.db-wal`, `*.db-shm` or the spool file. They are in `.gitignore`.
- Nothing leaves your machine. Sync (M4) will be opt-in.

## Roadmap

### Done
- [x] Zsh capture hook (exit code, duration, cwd, escaping, fail-silent, private commands)
- [x] SQLite database with WAL mode and numbered migrations
- [x] Ingest with byte-offset tracking, bad-line skipping and transactional saves
- [x] Test suite for unescape, parsing and ingest

### M1: finish capture and keyword search
- [ ] `0003_add_fts.sql`: FTS5 index over `command`, kept in sync with `events`
- [ ] `search(conn, text)` function, newest first, with tests
- [ ] `cli.py` with Typer: `dm ingest`, `dm search`, `dm recent`
- [ ] Register `dm` under `[project.scripts]` in `pyproject.toml`
- [ ] Persist a random `device_id` in a file instead of using the hostname
- [ ] Measure hook latency (target: under about 10 ms) and search speed on ~100k synthetic rows
- [ ] Add `.gitignore` entries and set up ruff, mypy, pre-commit and GitHub Actions
- [ ] Use it daily; this builds the real history M3 needs

### M2: secret redaction
- [ ] Detect common secrets (AWS keys, GitHub/Slack tokens, JWTs, private key blocks, high-entropy strings)
- [ ] Redact before anything is stored in the database
- [ ] Labeled test corpus; report precision, recall and false-positive rate

### M3: semantic search
- [ ] Local embeddings with `fastembed`; vector storage with `sqlite-vec`
- [ ] Chunking and hybrid ranking (keyword + vector, reciprocal rank fusion)
- [ ] Evaluation set from your real history; report recall@k and MRR

### M4: multi-device sync
- [ ] Add `hlc` and `deleted` fields to events (hybrid logical clocks, tombstones)
- [ ] Folder-based sync first; FastAPI relay as a second phase
- [ ] Property-based tests (Hypothesis) simulating offline edits on several devices
- [ ] Multi-device integration tests with Docker Compose
- [ ] Optional: end-to-end encryption with PyNaCl

### M5: polish and release
- [ ] Textual terminal UI
- [ ] Bash support (via `bash-preexec` or a DEBUG trap)
- [ ] Package for PyPI; make sure the `.sql` migration files are included in the build
- [ ] README with a demo GIF and benchmark tables

## Known limitations

- Zsh only for now.
- The hook records the working directory but not the git branch; branch/repo will be
  resolved at ingest time later.
- `device_id` is currently the hostname, which is not guaranteed unique (fix is on the M1 list).
- A command that never returns (such as a long-running `vim`) is logged only when it exits.