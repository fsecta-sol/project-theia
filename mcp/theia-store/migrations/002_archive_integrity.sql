-- Paper-ledger archive integrity migration 002.
-- Apply to a backed-up database only. Existing archives are preserved and
-- marked degraded when their entry/exit evidence is absent; no fills are made.
ALTER TABLE archives ADD COLUMN reconstructable INTEGER NOT NULL DEFAULT 0;
ALTER TABLE archives ADD COLUMN integrity_error TEXT;

UPDATE archives
SET reconstructable = 0,
    integrity_error = COALESCE(integrity_error, 'missing_trade_fills')
WHERE NOT EXISTS (
    SELECT 1 FROM trade_fills f
    WHERE f.trade_id = archives.trade_id AND f.kind = 'entry'
)
OR NOT EXISTS (
    SELECT 1 FROM trade_fills f
    WHERE f.trade_id = archives.trade_id AND f.kind <> 'entry'
);

CREATE TRIGGER IF NOT EXISTS archives_immutable_update
BEFORE UPDATE ON archives
BEGIN
  SELECT RAISE(ABORT, 'archives are immutable');
END;

CREATE TRIGGER IF NOT EXISTS archives_immutable_delete
BEFORE DELETE ON archives
BEGIN
  SELECT RAISE(ABORT, 'archives are append-only');
END;
