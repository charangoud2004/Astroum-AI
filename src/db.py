"""Database management and migration runner for BRAHMO Clinical AI.

Connects to SQLite, enforces foreign keys and WAL mode, and applies numbered
migrations with SHA-256 checksum tracking in schema_migrations.
"""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
from typing import List, Optional, Union

from src.config_loader import get_config


def compute_file_sha256(file_path: Union[str, Path]) -> str:
    """Compute SHA-256 checksum of a file's raw bytes."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_db_connection(db_path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    """Open and configure a SQLite database connection with foreign keys and WAL mode."""
    config = get_config()
    target_path = Path(db_path) if db_path else config.resolve_path(config.paths.db_path)

    # Ensure parent directory exists
    target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(target_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def apply_migrations(
    db_path: Optional[Union[str, Path]] = None,
    migrations_dir: Optional[Union[str, Path]] = None,
) -> List[str]:
    """Discover and apply all pending numbered SQL migrations in transactional order.

    Records applied migration filename, ISO-8601 timestamp, and SHA-256 checksum
    in schema_migrations table.

    Args:
        db_path: Optional explicit database path.
        migrations_dir: Optional explicit migrations directory.

    Returns:
        List of applied migration filenames.
    """
    config = get_config()
    resolved_db_path = Path(db_path) if db_path else config.resolve_path(config.paths.db_path)
    resolved_mig_dir = (
        Path(migrations_dir) if migrations_dir else config.resolve_path(config.paths.migrations_dir)
    )

    if not resolved_mig_dir.is_dir():
        raise FileNotFoundError(f"Migrations directory not found: {resolved_mig_dir}")

    conn = get_db_connection(resolved_db_path)
    applied_now: List[str] = []

    try:
        # 1. Ensure migrations ledger exists
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL,
                    checksum TEXT NOT NULL
                );
                """
            )

        # 2. Query already applied migrations
        cursor = conn.cursor()
        cursor.execute("SELECT version, checksum FROM schema_migrations ORDER BY version ASC;")
        applied_records = {row["version"]: row["checksum"] for row in cursor.fetchall()}

        # 3. Discover and sort migration files
        migration_files = sorted(resolved_mig_dir.glob("*.sql"), key=lambda p: p.name)

        for sql_file in migration_files:
            version_id = sql_file.name
            current_checksum = compute_file_sha256(sql_file)

            if version_id in applied_records:
                recorded_checksum = applied_records[version_id]
                if recorded_checksum != current_checksum:
                    raise ValueError(
                        f"Checksum mismatch for already applied migration '{version_id}'. "
                        f"Expected {recorded_checksum}, found {current_checksum}. "
                        "Migration files must never be modified once applied."
                    )
                continue

            # Read SQL script
            with open(sql_file, "r", encoding="utf-8") as f:
                sql_content = f.read()

            now_iso = datetime.now(timezone.utc).isoformat()

            # Apply migration inside an isolated transaction
            with conn:
                conn.executescript(sql_content)
                conn.execute(
                    """
                    INSERT INTO schema_migrations (version, applied_at, checksum)
                    VALUES (?, ?, ?);
                    """,
                    (version_id, now_iso, current_checksum),
                )

            applied_now.append(version_id)
            print(f"[MIGRATION] Successfully applied: {version_id} (checksum: {current_checksum[:12]}...)")

    finally:
        conn.close()

    return applied_now


if __name__ == "__main__":
    config = get_config()
    db_target = config.resolve_path(config.paths.db_path)
    print(f"Connecting to SQLite database at: {db_target}")
    applied = apply_migrations()
    if applied:
        print(f"Migration completed cleanly. Applied {len(applied)} migration(s): {', '.join(applied)}")
    else:
        print("Database schema is already up to date. No pending migrations.")
