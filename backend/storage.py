from __future__ import annotations

import json
import re
import sqlite3
from uuid import uuid4
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from agent_tools import StudentProfile, profile_from_dict
from config import SYSTEM_PROMPT_FILE


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATABASE_FILE = DATA_DIR / "gradmate.sqlite3"
SCHEMA_FILE = BASE_DIR / "schema.sql"


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DATABASE_FILE, timeout=20)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_load(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))


def _replace_collection(connection: sqlite3.Connection, table: str, items: list[dict[str, Any]]) -> None:
    connection.execute(f"DELETE FROM {table}")
    connection.executemany(
        f"INSERT INTO {table}(position, payload) VALUES (?, ?)",
        [(index, _json_dump(item)) for index, item in enumerate(items)],
    )


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _connection() as connection:
        _create_schema(connection)


def load_system_prompt() -> str:
    if not SYSTEM_PROMPT_FILE.exists():
        return "你是 GradMate 导师申请智能体。"
    return SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")


def get_profile() -> StudentProfile:
    ensure_data_dir()
    with _connection() as connection:
        row = connection.execute("SELECT payload FROM student_profile WHERE id = 1").fetchone()
    return profile_from_dict(_json_load(row["payload"] if row else None, {}))


def save_profile(profile: StudentProfile) -> None:
    ensure_data_dir()
    with _connection() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO student_profile(id, payload, updated_at) VALUES (1, ?, ?)",
            (_json_dump(profile.__dict__), datetime.now().isoformat()),
        )


def _save_supervisors_connection(connection: sqlite3.Connection, supervisors: list[dict[str, Any]]) -> None:
    connection.execute("DELETE FROM supervisors")
    now = datetime.now().isoformat()
    rows = []
    for item in supervisors:
        try:
            item_id = int(item.get("id") or 0)
        except (TypeError, ValueError):
            item_id = 0
        if item_id <= 0:
            continue
        rows.append((
            item_id,
            str(item.get("name") or ""),
            str(item.get("school") or ""),
            str(item.get("college") or ""),
            str(item.get("email") or ""),
            str(item.get("source") or ""),
            _json_dump(item),
            now,
        ))
    connection.executemany(
        """INSERT INTO supervisors(id, name, school, college, email, source, payload, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )


def get_supervisors() -> list[dict[str, Any]]:
    ensure_data_dir()
    with _connection() as connection:
        rows = connection.execute("SELECT payload FROM supervisors ORDER BY id").fetchall()
    return [_json_load(row["payload"], {}) for row in rows]


def save_supervisors(supervisors: list[dict[str, Any]]) -> None:
    ensure_data_dir()
    with _connection() as connection:
        _save_supervisors_connection(connection, supervisors)


def _get_collection(table: str) -> list[dict[str, Any]]:
    ensure_data_dir()
    with _connection() as connection:
        rows = connection.execute(f"SELECT payload FROM {table} ORDER BY position").fetchall()
    return [_json_load(row["payload"], {}) for row in rows]


def _save_collection(table: str, items: list[dict[str, Any]]) -> None:
    ensure_data_dir()
    with _connection() as connection:
        _replace_collection(connection, table, items)


def get_knowledge_items() -> list[dict[str, Any]]:
    return _get_collection("knowledge_items")


def save_knowledge_items(items: list[dict[str, Any]]) -> None:
    _save_collection("knowledge_items", items)


def get_rag_history() -> list[dict[str, Any]]:
    return _get_collection("rag_history")


def save_rag_history(items: list[dict[str, Any]]) -> None:
    _save_collection("rag_history", items)


def get_question_history() -> list[dict[str, Any]]:
    return _get_collection("question_history")


def save_question_history(items: list[dict[str, Any]]) -> None:
    _save_collection("question_history", items)


def get_resume_draft() -> dict[str, Any]:
    """Return the latest locally saved AI-resume workspace state."""
    ensure_data_dir()
    with _connection() as connection:
        row = connection.execute(
            "SELECT payload FROM app_cache WHERE key = ?",
            ("resume_draft",),
        ).fetchone()
    return _json_load(row["payload"], {}) if row else {}


def save_resume_draft(value: dict[str, Any]) -> dict[str, Any]:
    """Persist the editable resume workspace without coupling it to a profile update."""
    ensure_data_dir()
    draft = dict(value or {})
    draft["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _connection() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO app_cache(key, payload, updated_at) VALUES (?, ?, ?)",
            ("resume_draft", _json_dump(draft), draft["updated_at"]),
        )
    return draft


def get_assistant_history(limit: int = 30) -> list[dict[str, Any]]:
    ensure_data_dir()
    safe_limit = max(1, min(int(limit or 30), 100))
    with _connection() as connection:
        rows = connection.execute(
            "SELECT payload FROM assistant_history ORDER BY created_at DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
    return [_json_load(row["payload"], {}) for row in rows]


def save_assistant_history(item: dict[str, Any]) -> dict[str, Any]:
    """Persist one completed application-agent task for later restoration."""
    ensure_data_dir()
    record = dict(item or {})
    record["id"] = str(record.get("id") or uuid4())
    record["created_at"] = str(record.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    record["message"] = str(record.get("message") or "")
    with _connection() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO assistant_history(id, task, payload, created_at) VALUES (?, ?, ?, ?)",
            (record["id"], record["message"], _json_dump(record), record["created_at"]),
        )
    return record


def get_baoyan_ddl_cache() -> tuple[dict[str, Any], datetime | None]:
    ensure_data_dir()
    with _connection() as connection:
        row = connection.execute("SELECT payload, updated_at FROM app_cache WHERE key = ?", ("baoyan_ddl",)).fetchone()
    if not row:
        return {}, None
    try:
        updated_at = datetime.fromisoformat(row["updated_at"])
    except (TypeError, ValueError):
        updated_at = None
    return _json_load(row["payload"], {}), updated_at


def save_baoyan_ddl_cache(value: dict[str, Any]) -> None:
    ensure_data_dir()
    with _connection() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO app_cache(key, payload, updated_at) VALUES (?, ?, ?)",
            ("baoyan_ddl", _json_dump(value), datetime.now().isoformat()),
        )


def _norm_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _norm_source(value: Any) -> str:
    return str(value or "").strip().rstrip("/").lower()


def supervisor_dedupe_key(supervisor: dict[str, Any]) -> tuple[str, str] | None:
    email = _norm_text(supervisor.get("email"))
    if email:
        return "email", email
    name = _norm_text(supervisor.get("name"))
    source = _norm_source(supervisor.get("source"))
    if name and source.startswith(("http://", "https://")):
        return "name_source", f"{name}|{source}"
    school = _norm_text(supervisor.get("school"))
    college = _norm_text(supervisor.get("college"))
    if name and school:
        return "name_school_college", f"{name}|{school}|{college}"
    return None


def merge_supervisors(current: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    merged = [dict(item) for item in current]
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for item in merged:
        key = supervisor_dedupe_key(item)
        if key:
            index[key] = item
    next_id = max([int(item.get("id", 0) or 0) for item in merged] + [0]) + 1
    added: list[dict[str, Any]] = []
    for item in incoming:
        candidate = dict(item)
        key = supervisor_dedupe_key(candidate)
        existing = index.get(key) if key else None
        if existing is not None:
            for field, value in candidate.items():
                if field != "id" and value and not existing.get(field):
                    existing[field] = value
            continue
        candidate["id"] = next_id
        next_id += 1
        merged.append(candidate)
        added.append(candidate)
        if key:
            index[key] = candidate
    return merged, added
