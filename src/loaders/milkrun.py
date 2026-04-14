"""milkrun_fee_versions 업로드 (text 버전 관리).

content_hash UNIQUE 제약으로 같은 내용이면 last_seen만 갱신.
"""
import logging
from pathlib import Path

from loaders.base import (
    finish_run, get_supabase_client, latest_download, now_iso, stable_hash, start_run,
)

log = logging.getLogger(__name__)


def load(file_path: Path | None = None) -> dict:
    if file_path is None:
        file_path = latest_download("milkrun_fee_info_*.txt")
    if not file_path or not Path(file_path).exists():
        raise FileNotFoundError(f"milkrun text 파일 없음: {file_path}")

    file_path = Path(file_path)
    log.info(f"[MILKRUN_LOAD] 파일: {file_path}")
    text = file_path.read_text(encoding="utf-8")
    h = stable_hash({"content": text})
    log.info(f"[MILKRUN_LOAD] {len(text)} chars, hash={h[:12]}")

    client = get_supabase_client()
    run_id = start_run(client, "milkrun", file_path)

    try:
        # 기존 hash 확인
        existing = client.table("milkrun_fee_versions") \
            .select("id,content_hash") \
            .eq("content_hash", h) \
            .limit(1).execute()
        is_new = not (existing.data or [])

        now = now_iso()
        if is_new:
            client.table("milkrun_fee_versions").insert({
                "content": text,
                "content_hash": h,
                "char_count": len(text),
                "first_seen_at": now,
                "last_seen_at": now,
                "scrape_run_id": run_id,
            }).execute()
            log.info("[MILKRUN_LOAD] 새 버전 INSERT")
            n_new, n_same = 1, 0
        else:
            client.table("milkrun_fee_versions") \
                .update({"last_seen_at": now}) \
                .eq("content_hash", h) \
                .execute()
            log.info("[MILKRUN_LOAD] 동일 내용 — last_seen_at만 갱신")
            n_new, n_same = 0, 1

        finish_run(
            client, run_id,
            status="success",
            rows_processed=1,
            rows_inserted=n_new,
            rows_unchanged=n_same,
            metadata={"file": str(file_path), "char_count": len(text)},
        )
        return {"run_id": run_id, "new_version": bool(n_new), "char_count": len(text)}

    except Exception as e:
        log.error(f"[MILKRUN_LOAD] 실패: {e}", exc_info=True)
        finish_run(client, run_id, status="failed", error_message=str(e))
        raise
