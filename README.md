# devmem

**A local-first memory for your terminal.** devmem quietly records your shell commands, git history, and notes, strips out secrets, and lets you search it by meaning: *"how did I fix that Docker networking issue last month?"*

Everything lives in a local SQLite database, works offline, and syncs between your own machines without a central server owning your data.

> **Status:** early development. The checklist under [Roadmap](#roadmap) shows what works today. Numbers marked *TBD* will be filled in as milestones land.

<!-- Add a demo GIF here once the TUI exists: ![demo](docs/demo.gif) -->

---

## Why

Developers solve the same problems repeatedly, and the fix usually lives in a terminal session from three weeks ago. Shell history is too limited (exact-match only, one machine, no context), and existing tools that go further tend to send your data to a server.

devmem is built around three ideas:

- **Local-first.** Your history stays on your machines, readable and queryable offline.
- **Safe by default.** Secrets are detected and redacted *before* anything is written to disk.
- **Search by meaning.** Keyword and semantic search are combined, and retrieval quality is measured rather than assumed.

## Features

- **Capture** shell commands (with working directory, exit code, duration, and git context) via lightweight zsh and bash hooks
- **Git indexing** of commit messages and diff summaries
- **Quick notes** with `dm note`
- **Secret redaction** before storage, with a documented test corpus and measured detection rates
- **Hybrid search** combining SQLite FTS5 keyword search with local embeddings, merged using reciprocal rank fusion
- **Multi-device sync** over an append-only event log, with no central authority
- **Terminal UI** for browsing and filtering your history

## Install

> Not yet published. Planned install:

```bash
uv tool install devmem
dm init            # installs the shell hook for zsh or bash
```

From source:

```bash
git clone https://github.com/<your-username>/devmem.git
cd devmem
uv sync
uv run dm --help
```

## Usage

```bash
dm search "docker networking fix"     # hybrid keyword + semantic search
dm recent                             # latest commands and notes
dm note "bridge network needed --internal=false for the db container"
dm sync                               # merge history with your other devices
dm tui                                # interactive search browser
```

## How it works

```
  shell hook ──► spool file ──► ingest + redact ──► SQLite event log
  git indexer ─────────────────────────┘                  │
  dm note ─────────────────────────────┘                  │
                                                           ▼
                                      derived locally: sessions, chunks,
                                      FTS5 index, vector index
                                                           │
                                                           ▼
                                           hybrid search (RRF ranking)

  sync: only the event log travels between devices; indexes are rebuilt locally
```

**Design principle: sync events, not indexes.** The source of truth is an append-only event log. Sessions, chunks, the keyword index, and embeddings are all derived and can be rebuilt on any device. This keeps the sync problem small and makes new devices easy to bring up.

### Data model

| Table | Purpose |
|---|---|
| `events` | Append-only log: `id` (ULID), `device_id`, `hlc` (hybrid logical clock), `type` (command, commit, note), `payload`, `deleted` (tombstone) |
| `sessions` | Events grouped by time gap and working directory (derived) |
| `chunks` | Text units that get embedded and indexed (derived) |
| FTS5 and vector tables | Keyword and semantic indexes over chunks (derived) |

### Capture

The shell hook only appends one line to a spool file, so it adds no noticeable delay to your prompt. A separate ingest step reads the spool, redacts secrets, and writes events to SQLite. If the hook ever fails, it fails silently rather than breaking your shell.

### Sync

Devices exchange events and merge them by union, ordered by hybrid logical clock. Deletes are tombstones, and merges are idempotent, so duplicate delivery is harmless. Transport starts as a shared folder or git remote, with an optional small relay server planned later. The relay would only ever hold encrypted blobs.

## Privacy and security

Shell history often contains secrets, so devmem treats this as a core feature rather than an afterthought.

- Redaction runs **before** anything is written to disk: known token formats, `--password=` style flags, `Authorization` headers, private key blocks, and high-entropy strings
- Commands starting with a space are ignored, and you can configure a deny list
- The spool file is owner-readable only and cleared after ingest
- Nothing leaves your machine unless you configure sync
- Redaction is not perfect. See [docs/redaction.md](docs/redaction.md) *(planned)* for what it catches, what it misses, and measured rates

## Evaluation

Retrieval quality is measured against a hand-built set of queries written from real history, each with a known correct result.

| Method | Recall@5 | MRR |
|---|---|---|
| Keyword only (FTS5) | TBD | TBD |
| Semantic only | TBD | TBD |
| Hybrid (RRF) | TBD | TBD |

Other measured numbers (to be filled in):

| Metric | Result |
|---|---|
| Shell hook overhead per prompt | TBD |
| Search latency over 100k events | TBD |
| Secret detection recall / false-positive rate | TBD |
| Sync convergence tests (randomized schedules) | TBD |

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.12 |
| Packaging | uv |
| CLI / TUI | Typer, Textual |
| Storage | SQLite (WAL) with FTS5 |
| Vector search | sqlite-vec |
| Embeddings | fastembed (ONNX), small local model, CPU only |
| Sync transport | Shared folder or git remote; optional FastAPI relay |
| Testing | pytest, Hypothesis, Docker Compose |
| CI | GitHub Actions (ruff, mypy, pytest, build) |

## Roadmap

- [ ] **M0: Foundations.** Repo, CI, design doc, threat model
- [ ] **M1: Capture and keyword search.** Shell hooks, SQLite storage, FTS5 search, git indexer, `dm note`
- [ ] **M2: Secret redaction.** Redaction pipeline, ignore rules, test corpus, measured detection rates
- [ ] **M3: Semantic search.** Local embeddings, session chunking, hybrid ranking, evaluation harness
- [ ] **M4: Sync.** Event-log merge, hybrid logical clocks, tombstones, property-based and multi-container tests
- [ ] **M5: TUI and release.** Terminal UI, PyPI release, docs, demo

**Possible later additions**

- `dm why`: pipe in a failed command or stack trace and retrieve similar past failures and fixes from your own history
- An MCP server so AI coding assistants can query your history
- End-to-end encrypted relay sync
- fish shell support

**Out of scope for v1:** Windows, web or mobile UI, hosted accounts, team sharing.

## Testing

Sync correctness is the riskiest part of the project, so it gets the most thorough testing:

- **Property-based tests (Hypothesis)** simulate multiple devices making random offline edits and merging in random orders, asserting that all devices converge to identical state
- **Docker Compose tests** run separate containers as real devices
- Targeted cases for deletes, duplicate delivery, and clock skew

```bash
uv run pytest                 # unit and property tests
docker compose -f tests/docker-compose.yml up --abort-on-container-exit   # multi-device tests
```

## Contributing

Issues and pull requests are welcome once the core milestones land. Please open an issue first to discuss larger changes.

## License

TBD (MIT is a common choice for tools like this).
