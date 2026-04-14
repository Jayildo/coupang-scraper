"""Supabase 클라이언트 + 공통 헬퍼."""
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

log = logging.getLogger(__name__)


def get_supabase_client():
    """Supabase Python client (service_role). RLS 자동 우회."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 미설정 — .env 확인"
        )
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def stable_hash(d: dict[str, Any]) -> str:
    """dict의 값들을 정렬 후 hash. None과 빈 문자열은 동일하게 취급."""
    norm = {k: ("" if v is None else v) for k, v in d.items()}
    payload = json.dumps(norm, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def new_run_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def start_run(client, task_name: str, source_file: str | Path | None) -> str:
    """scrape_runs에 새 row INSERT, run_id 반환."""
    run_id = new_run_id()
    client.table("scrape_runs").insert({
        "id": run_id,
        "task_name": task_name,
        "source_file": str(source_file) if source_file else None,
        "started_at": now_iso(),
        "status": "running",
    }).execute()
    log.info(f"[LOAD] run 시작: task={task_name} run_id={run_id}")
    return run_id


def finish_run(
    client,
    run_id: str,
    *,
    status: str = "success",
    rows_processed: int = 0,
    rows_inserted: int = 0,
    rows_updated: int = 0,
    rows_unchanged: int = 0,
    rows_removed: int = 0,
    error_message: str | None = None,
    metadata: dict | None = None,
):
    client.table("scrape_runs").update({
        "finished_at": now_iso(),
        "status": status,
        "rows_processed": rows_processed,
        "rows_inserted": rows_inserted,
        "rows_updated": rows_updated,
        "rows_unchanged": rows_unchanged,
        "rows_removed": rows_removed,
        "error_message": error_message,
        "metadata": metadata,
    }).eq("id", run_id).execute()
    log.info(
        f"[LOAD] run 종료: status={status} processed={rows_processed} "
        f"ins={rows_inserted} upd={rows_updated} same={rows_unchanged} rm={rows_removed}"
    )


def latest_download(pattern: str) -> Path | None:
    """data/downloads/ 에서 패턴에 매칭되는 가장 최근 파일 반환."""
    from config import DATA_DIR
    files = sorted((DATA_DIR / "downloads").glob(pattern))
    return files[-1] if files else None


def chunked(seq: list, size: int):
    """리스트를 size 크기 청크로 분할."""
    for i in range(0, len(seq), size):
        yield seq[i:i + size]
