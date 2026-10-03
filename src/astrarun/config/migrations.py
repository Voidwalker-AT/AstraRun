"""Config and Database Schema Migrations for AstraRun 1.0.

Provides resilient, versioned upgrades with rollback protection for:
- JSON configuration files (schema_versioning)
- SQLite persistent databases (history, memory, telemetry)
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.config.migrations")

CURRENT_CONFIG_VERSION = 2
CURRENT_DB_VERSION = 2


def migrate_config_dict(raw_config: Dict[str, Any]) -> Tuple[Dict[str, Any], int, List[str]]:
    """
    Migrate a configuration dictionary to the latest schema version.
    Returns: (migrated_config, final_version, applied_migrations_log)
    """
    cfg = dict(raw_config)
    applied: List[str] = []
    ver = cfg.get("schema_version", 0)

    # v0 -> v1: add sandbox and network blocks
    if ver < 1:
        logger.info("Migrating config from v%d to v1", ver)
        if "sandbox" not in cfg:
            cfg["sandbox"] = {
                "default_profile": "EPHEMERAL_TOOL",
                "timeout_sec": 30.0,
                "memory_limit_mb": 512,
                "stdout_max_kb": 512,
            }
        if "network" not in cfg:
            cfg["network"] = {
                "default_policy": "DENY",
                "allow_public_get": True,
                "quarantine_dir": "data/quarantine",
            }
        cfg["schema_version"] = 1
        applied.append("v0 -> v1: Added sandbox and network governance blocks.")
        ver = 1

    # v1 -> v2: add dynamic_tools and trust_kernel governance blocks
    if ver < 2:
        logger.info("Migrating config from v%d to v2", ver)
        if "dynamic_tools" not in cfg:
            cfg["dynamic_tools"] = {
                "enabled": True,
                "max_repair_attempts": 2,
                "ast_inspection_strict": True,
            }
        if "trust_kernel" not in cfg:
            cfg["trust_kernel"] = {
                "enforce_immutable_boundary": True,
                "audit_violations": True,
            }
        cfg["schema_version"] = 2
        applied.append("v1 -> v2: Added dynamic_tools and trust_kernel blocks.")
        ver = 2

    return cfg, ver, applied


def migrate_config_file(config_path: Path | str) -> Tuple[bool, List[str]]:
    """Migrate on-disk JSON configuration file with backup."""
    p = Path(config_path).resolve()
    if not p.exists():
        return False, [f"Config file not found: {p}"]

    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return False, [f"JSON parse error in {p}: {e}"]

    migrated, final_ver, applied = migrate_config_dict(raw)
    if applied:
        backup = p.with_suffix(".json.bak")
        shutil.copy2(p, backup)
        p.write_text(json.dumps(migrated, indent=2), encoding="utf-8")
        logger.info("Config migrated to v%d. Backup at %s", final_ver, backup)

    return True, applied


def migrate_database(db_path: Path | str) -> Tuple[int, List[str]]:
    """
    Migrate SQLite database to CURRENT_DB_VERSION with transactional rollback.
    """
    p = Path(db_path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    applied: List[str] = []

    # If DB exists, create safety backup
    backup_path = p.with_suffix(".db.bak")
    if p.exists() and p.stat().st_size > 0:
        try:
            shutil.copy2(p, backup_path)
        except Exception as e:
            logger.warning("Could not create DB backup %s: %s", backup_path, e)

    conn = sqlite3.connect(str(p))
    try:
        with conn:
            # 1. Ensure migrations tracking table exists
            conn.execute("""
                CREATE TABLE IF NOT EXISTS _schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at REAL NOT NULL,
                    description TEXT NOT NULL
                )
            """)

            cur = conn.cursor()
            cur.execute("SELECT MAX(version) FROM _schema_migrations")
            row = cur.fetchone()
            current_ver = row[0] if (row and row[0] is not None) else 0

            # Step 1: Baseline schema (v1)
            if current_ver < 1:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS task_history (
                        task_id TEXT PRIMARY KEY,
                        goal TEXT NOT NULL,
                        status TEXT NOT NULL,
                        started_at REAL NOT NULL,
                        completed_at REAL,
                        exit_code INTEGER,
                        duration_ms REAL
                    )
                """)
                conn.execute(
                    "INSERT INTO _schema_migrations (version, applied_at, description) VALUES (1, ?, ?)",
                    (time.time(), "v1: Initial task_history schema"),
                )
                applied.append("v1: Initial task_history schema")
                current_ver = 1

            # Step 2: v2 schema - Add continuity, artifacts, and risk telemetry
            if current_ver < 2:
                # Add columns if not already existing
                cur.execute("PRAGMA table_info(task_history)")
                cols = {c[1] for c in cur.fetchall()}
                if "artifacts" not in cols:
                    conn.execute("ALTER TABLE task_history ADD COLUMN artifacts TEXT DEFAULT ''")
                if "risk_level" not in cols:
                    conn.execute("ALTER TABLE task_history ADD COLUMN risk_level TEXT DEFAULT 'LOW'")
                if "tool_id" not in cols:
                    conn.execute("ALTER TABLE task_history ADD COLUMN tool_id TEXT DEFAULT ''")

                # Create index for fast continuity lookup
                conn.execute("CREATE INDEX IF NOT EXISTS idx_task_started ON task_history(started_at DESC)")

                conn.execute(
                    "INSERT INTO _schema_migrations (version, applied_at, description) VALUES (2, ?, ?)",
                    (time.time(), "v2: Added continuity, artifacts, and tool tracking columns"),
                )
                applied.append("v2: Added continuity, artifacts, and tool tracking columns")
                current_ver = 2

            return current_ver, applied

    except Exception as e:
        logger.error("DB migration failed on %s: %s. Rolling back.", p, e)
        conn.close()
        if backup_path.exists():
            shutil.copy2(backup_path, p)
        raise RuntimeError(f"Database migration failure: {e}") from e
    finally:
        try:
            conn.close()
        except Exception:
            pass
