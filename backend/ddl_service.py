from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from config import get_baoyan_ddl_settings
from storage import ensure_data_dir, get_baoyan_ddl_cache, save_baoyan_ddl_cache


SOURCE_LABELS = {
    "camp2026": "2026 夏令营",
    "camp2025": "2025 夏令营",
    "camp2024": "2024 夏令营",
    "yutuimian2024": "2024 预推免",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_deadline(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _days_left(deadline: datetime | None, now: datetime) -> int | None:
    if not deadline:
        return None
    return (deadline.date() - now.date()).days


def _status_from_days(days: int | None) -> str:
    if days is None:
        return "unknown"
    if days < 0:
        return "closed"
    if days <= 7:
        return "urgent"
    return "upcoming"


def _fetch_remote_json(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "GradMate-DDL/0.1",
        },
    )
    with urlopen(request, timeout=12) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset))


def _cache_age_seconds(updated_at: datetime | None) -> float | None:
    if not updated_at:
        return None
    return max(0.0, (datetime.now() - updated_at).total_seconds())


def _load_dataset(refresh: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    ensure_data_dir()
    settings = get_baoyan_ddl_settings()
    cached, cached_at = get_baoyan_ddl_cache()
    cache_age = _cache_age_seconds(cached_at)
    cache_is_fresh = cache_age is not None and cache_age <= settings.cache_ttl_seconds

    if cache_is_fresh and not refresh:
        if cached.get("payload"):
            return cached["payload"], {
                "source_url": settings.source_url,
                "fetched_at": cached.get("fetched_at"),
                "from_cache": True,
                "cache_age_seconds": int(cache_age or 0),
            }

    try:
        payload = _fetch_remote_json(settings.source_url)
        fetched_at = _now().isoformat()
        save_baoyan_ddl_cache({"source_url": settings.source_url, "fetched_at": fetched_at, "payload": payload})
        return payload, {
            "source_url": settings.source_url,
            "fetched_at": fetched_at,
            "from_cache": False,
            "cache_age_seconds": 0,
        }
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as error:
        if cached.get("payload"):
            return cached["payload"], {
                "source_url": settings.source_url,
                "fetched_at": cached.get("fetched_at"),
                "from_cache": True,
                "cache_age_seconds": int(_cache_age_seconds(cached_at) or 0),
                "warning": f"远程数据暂时不可用，已使用本地缓存：{error}",
            }
        raise RuntimeError(f"无法获取保研 DDL 数据：{error}") from error


def _normalize_item(raw: dict[str, Any], now: datetime) -> dict[str, Any]:
    deadline = _parse_deadline(str(raw.get("deadline") or ""))
    days = _days_left(deadline, now)
    tags = raw.get("tags") if isinstance(raw.get("tags"), list) else []
    return {
        "name": str(raw.get("name") or "").strip(),
        "institute": str(raw.get("institute") or "").strip(),
        "description": str(raw.get("description") or "").strip(),
        "deadline": raw.get("deadline") or "",
        "deadline_date": deadline.date().isoformat() if deadline else "",
        "days_left": days,
        "status": _status_from_days(days),
        "website": str(raw.get("website") or "").strip(),
        "tags": [str(item).strip() for item in tags if str(item).strip()],
        "province": str(raw.get("province") or "").strip(),
    }


def _matches_query(item: dict[str, Any], query: str) -> bool:
    if not query:
        return True
    haystack = " ".join(
        [
            item.get("name", ""),
            item.get("institute", ""),
            item.get("description", ""),
            item.get("province", ""),
            " ".join(item.get("tags", [])),
        ]
    ).lower()
    return query.lower() in haystack


def get_baoyan_ddl(source: str = "camp2026", query: str = "", limit: int = 40, refresh: bool = False) -> dict[str, Any]:
    payload, meta = _load_dataset(refresh=refresh)
    source_key = source if source in payload else "camp2026"
    raw_items = payload.get(source_key, [])
    if not isinstance(raw_items, list):
        raw_items = []

    now = _now()
    items = [_normalize_item(item, now) for item in raw_items if isinstance(item, dict)]
    items = [item for item in items if _matches_query(item, query.strip())]
    items.sort(
        key=lambda item: (
            item["status"] == "closed",
            item["days_left"] is None,
            item["days_left"] if item["days_left"] is not None else 99999,
            item["name"],
        )
    )

    safe_limit = max(1, min(int(limit or 40), 200))
    stats = {
        "total": len(items),
        "upcoming": sum(1 for item in items if item["status"] == "upcoming"),
        "urgent": sum(1 for item in items if item["status"] == "urgent"),
        "closed": sum(1 for item in items if item["status"] == "closed"),
        "unknown": sum(1 for item in items if item["status"] == "unknown"),
    }
    return {
        "source": source_key,
        "source_label": SOURCE_LABELS.get(source_key, source_key),
        "sources": [{"id": key, "label": label} for key, label in SOURCE_LABELS.items()],
        "items": items[:safe_limit],
        "stats": stats,
        "meta": meta,
    }
