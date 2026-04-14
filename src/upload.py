"""Supabase 업로드 진입점.

사용법:
    cd src
    python upload.py analytics                        # 최근 다운로드 자동 사용
    python upload.py analytics path/to/file.csv       # 특정 파일 지정

환경변수:
    SUPABASE_URL                  필수
    SUPABASE_SERVICE_ROLE_KEY     필수

종료 코드:
    0 = 모든 업로드 성공
    1 = 1개 이상 실패 또는 fatal
"""
import json
import sys
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler

from config import LOGS_DIR

LOGS_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = LOGS_DIR / "upload.log"
_file_handler = RotatingFileHandler(
    _LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_stream_handler, _file_handler])
log = logging.getLogger(__name__)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1

    task = argv[1].lower()
    file_arg = argv[2] if len(argv) > 2 else None

    log.info(f"[UPLOAD] task={task} file={file_arg or '<auto>'}")

    results: dict = {}
    fatal: str | None = None

    try:
        if task == "analytics":
            from loaders import analytics
            results["analytics"] = analytics.load(file_arg)
        elif task == "po_sku":
            from loaders import po_sku
            results["po_sku"] = po_sku.load(file_arg)
        elif task == "sku_info":
            from loaders import sku_info
            results["sku_info"] = sku_info.load(file_arg)
        elif task == "milkrun":
            from loaders import milkrun
            results["milkrun"] = milkrun.load(file_arg)
        elif task == "all":
            from loaders import analytics, po_sku, sku_info, milkrun
            results["milkrun"] = milkrun.load()
            results["sku_info"] = sku_info.load()
            results["po_sku"] = po_sku.load()
            results["analytics"] = analytics.load()
        else:
            fatal = f"unknown task: {task} (지원: analytics, po_sku, sku_info, milkrun, all)"
            log.error(f"[UPLOAD] {fatal}")
    except FileNotFoundError as e:
        fatal = str(e)
        log.error(f"[UPLOAD] {fatal}")
    except Exception as e:
        fatal = f"{type(e).__name__}: {e}"
        log.error(f"[UPLOAD] 실패: {e}", exc_info=True)

    code = 0 if (results and not fatal) else 1
    status = {
        "timestamp": datetime.now().isoformat(),
        "exit_code": code,
        "fatal_error": fatal,
        "results": results,
    }
    print("UPLOAD_STATUS=" + json.dumps(status, ensure_ascii=False, default=str))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
