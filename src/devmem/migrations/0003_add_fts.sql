CREATE VIRTUAL TABLE events_fts USING fts5(
    event_id UNINDEXED, 
    command
);

-- Triggers to keep events and events_fts synced

CREATE TRIGGER events_fts_insert AFTER INSERT ON events
BEGIN
    INSERT INTO events_fts (event_id, command) VALUES (new.id, new.command);
END;

CREATE TRIGGER events_fts_delete AFTER DELETE ON events
BEGIN
    DELETE FROM events_fts WHERE event_id = old.id;
END;

CREATE TRIGGER events_fts_update AFTER UPDATE OF command ON events
BEGIN
    DELETE FROM events_fts WHERE event_id = old.id;
    INSERT INTO events_fts (event_id, command) VALUES (new.id, new.command);
END;

-- Insert everything that is already in events before migration
INSERT INTO events_fts (event_id, command) SELECT id, command FROM events;