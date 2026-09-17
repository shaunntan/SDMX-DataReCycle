import Database from "better-sqlite3";
import fs from "node:fs";
import path from "node:path";

/**
 * SQLite database for the web wireframe ONLY.
 * Deliberately separate from the Python generator's db/main_dataset.sqlite.
 */
const DATA_DIR = path.join(process.cwd(), "data");
const DB_PATH = path.join(DATA_DIR, "app.db");

let _db: Database.Database | null = null;

export function getDb(): Database.Database {
  if (_db) return _db;
  fs.mkdirSync(DATA_DIR, { recursive: true });
  const db = new Database(DB_PATH);
  db.pragma("journal_mode = WAL");
  db.exec(`
    CREATE TABLE IF NOT EXISTS sessions (
      id TEXT PRIMARY KEY,
      created_at TEXT NOT NULL,
      filenames TEXT NOT NULL,
      items_json TEXT NOT NULL,
      identities_json TEXT NOT NULL DEFAULT '[]',
      raw_json TEXT NOT NULL DEFAULT '{}',
      data_conversion_json TEXT NOT NULL DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS active_session (
      k INTEGER PRIMARY KEY CHECK (k = 1),
      session_id TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS saved_artifacts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      artifact_type TEXT NOT NULL,
      artifact_id TEXT NOT NULL,
      version TEXT NOT NULL,
      name TEXT NOT NULL DEFAULT '',
      agency_id TEXT NOT NULL DEFAULT '',
      saved_at TEXT NOT NULL,
      source_session TEXT,
      items_json TEXT NOT NULL,
      structured_json TEXT NOT NULL DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS applied_changes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      saved_artifact_id INTEGER NOT NULL,
      change_id TEXT NOT NULL,
      item_id TEXT NOT NULL,
      field TEXT NOT NULL,
      old_value TEXT,
      new_value TEXT,
      applied_at TEXT NOT NULL
    );
  `);
  // Backfill columns for databases created before identities/name/agency_id existed.
  const sessionCols = db.prepare(`PRAGMA table_info(sessions)`).all() as Array<{ name: string }>;
  if (!sessionCols.some((c) => c.name === "identities_json")) {
    db.exec(`ALTER TABLE sessions ADD COLUMN identities_json TEXT NOT NULL DEFAULT '[]'`);
  }
  if (!sessionCols.some((c) => c.name === "raw_json")) {
    db.exec(`ALTER TABLE sessions ADD COLUMN raw_json TEXT NOT NULL DEFAULT '{}'`);
  }
  if (!sessionCols.some((c) => c.name === "data_conversion_json")) {
    db.exec(`ALTER TABLE sessions ADD COLUMN data_conversion_json TEXT NOT NULL DEFAULT '{}'`);
  }
  const savedCols = db.prepare(`PRAGMA table_info(saved_artifacts)`).all() as Array<{ name: string }>;
  if (!savedCols.some((c) => c.name === "name")) {
    db.exec(`ALTER TABLE saved_artifacts ADD COLUMN name TEXT NOT NULL DEFAULT ''`);
  }
  if (!savedCols.some((c) => c.name === "agency_id")) {
    db.exec(`ALTER TABLE saved_artifacts ADD COLUMN agency_id TEXT NOT NULL DEFAULT ''`);
  }
  if (!savedCols.some((c) => c.name === "structured_json")) {
    db.exec(`ALTER TABLE saved_artifacts ADD COLUMN structured_json TEXT NOT NULL DEFAULT '{}'`);
  }
  _db = db;
  return db;
}
