import sqlite3
import json
import threading
import os
from datetime import datetime
from contextlib import contextmanager
from loguru import logger

class DatabaseManager:
    """
    Thread-safe SQLite manager for the automation framework.
    Handles schema initialization and provides context-managed connections.
    """

    def __init__(self, db_path: str = "data/session_cache.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._ensure_dir()
        self._initialize_schema()
        logger.info(f"Database initialized at {self.db_path}")

    def _ensure_dir(self):
        """Ensure the data directory exists."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _initialize_schema(self):
        """Creates the required tables if they do not exist."""
        queries = [
            """
            CREATE TABLE IF NOT EXISTS site_schemas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_domain TEXT NOT NULL,
                field_id TEXT NOT NULL,
                selector_type TEXT NOT NULL,
                selector_value TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(site_domain, field_id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS active_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_name TEXT NOT NULL,
                cookies_json TEXT NOT NULL,
                user_agent TEXT NOT NULL,
                anti_bot_tokens TEXT, -- JSON field for reese84, cf_clearance, etc.
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS checkout_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_name TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL,
                response_payload TEXT, -- JSON field for debugging
                error_msg TEXT
            );
            """
        ]
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for query in queries:
                cursor.execute(query)
            conn.commit()
            logger.debug("Schema verification complete.")

    @contextmanager
    def get_connection(self):
        """
        Provides a thread-safe connection context manager.
        Uses a threading lock to prevent database corruption during concurrent writes.
        """
        self._lock.acquire()
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        # Return rows as dictionaries for easier mapping to objects
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        except Exception as e:
            logger.error(f"Database transaction error: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()
            self._lock.release()

    # --- CRUD Operations ---

    def update_site_schema(self, domain: str, field_id: str, sel_type: str, sel_val: str):
        """Upsert a site schema mapping."""
        query = """
            INSERT INTO site_schemas (site_domain, field_id, selector_type, selector_value, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(site_domain, field_id) DO UPDATE SET
                selector_type=excluded.selector_type,
                selector_value=excluded.selector_value,
                updated_at=excluded.updated_at;
        """
        with self.get_connection() as conn:
            conn.execute(query, (domain, field_id, sel_type, sel_val, datetime.now()))
            conn.commit()

    def save_session(self, profile: str, cookies: list, ua: str, tokens: dict, expiry: str = None):
        """Persist browser session state for the sniper module."""
        query = """
            INSERT INTO active_sessions (profile_name, cookies_json, user_agent, anti_bot_tokens, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """
        with self.get_connection() as conn:
            conn.execute(query, (
                profile, 
                json.dumps(cookies), 
                ua, 
                json.dumps(tokens), 
                expiry
            ))
            conn.commit()

    def get_latest_session(self, profile: str):
        """Retrieve the freshest session for a specific profile."""
        query = "SELECT * FROM active_sessions WHERE profile_name = ? ORDER BY last_seen DESC LIMIT 1"
        with self.get_connection() as conn:
            row = conn.execute(query, (profile,)).fetchone()
            if row:
                return dict(row)
            return None

    def log_checkout(self, profile: str, status: str, payload: dict = None, error: str = None):
        """Log the outcome of a checkout attempt."""
        query = """
            INSERT INTO checkout_logs (profile_name, status, response_payload, error_msg)
            VALUES (?, ?, ?, ?)
        """
        with self.get_connection() as conn:
            conn.execute(query, (
                profile, 
                status, 
                json.dumps(payload) if payload else None, 
                error
            ))
            conn.commit()

    def get_schema(self, event_id: str) -> Optional[dict]:
    """
    Reconstructs the full selector schema dict for an event_id.
    Reads all per-field rows for the event's domain and assembles them
    into the flat dict that ClickSniper expects.
    """
    # The profiler stores schemas keyed by domain, not event_id.
    # We need to look up the domain associated with this event_id.
    # Strategy: store event_id→domain mapping in a new column, OR
    # use the target_url stored in the schema to derive the domain.
    # Simplest fix: store event_id as the domain value during recon.
    query = """
        SELECT field_id, selector_value FROM site_schemas
        WHERE site_domain = ?
    """
    with self.get_connection() as conn:
        rows = conn.execute(query, (event_id,)).fetchall()
        if not rows:
            return None
        schema = {row["field_id"]: row["selector_value"] for row in rows}
        return schema

if __name__ == "__main__":
    # Self-test block
    db = DatabaseManager("data/test_db.sqlite")
    db.update_site_schema("example.com", "login_btn", "css", ".btn-primary")
    db.save_session("test_profile", [{"name": "session_id", "value": "12345"}], "Mozilla/5.0", {"cf_clearance": "abc"})
    
    session = db.get_latest_session("test_profile")
    print(f"Retrieved Session: {session}")
