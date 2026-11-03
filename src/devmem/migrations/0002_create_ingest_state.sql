CREATE TABLE ingest_state(
    spool_path TEXT PRIMARY KEY,
    byte_offset INTEGER NOT NULL
);