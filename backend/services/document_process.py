"""A document attempt has one killable 120-second process within the worker slot."""
import os
import subprocess
import sys
from threading import Thread

DOCUMENT_PARSE_TIMEOUT_SECONDS = 120


def _command(run_id: str, epoch: int) -> list[str]:
    return [sys.executable, '-m', 'backend.services.document_process', run_id, str(epoch)]


def run_document_parse_process(run_id: str, epoch: int) -> None:
    _run_document_process(run_id, epoch, 'document_parse')


def run_document_import_process(run_id: str, epoch: int) -> None:
    _run_document_process(run_id, epoch, 'document_import')


def _run_document_process(run_id: str, epoch: int, kind: str) -> None:
    from backend.db.database import SessionLocal
    from backend.schemas.agent_runs import RunStatus
    from backend.services.agent_runs import finish_run

    failure = None
    try:
        child = subprocess.Popen([*_command(run_id, epoch), kind], stdin=subprocess.PIPE)
    except OSError:
        failure = kind + '_failed'
    else:
        try:
            try:
                code = child.wait(timeout=DOCUMENT_PARSE_TIMEOUT_SECONDS)
                if code != 0:
                    failure = kind + '_failed'
            except subprocess.TimeoutExpired:
                failure = kind + '_timeout'
        finally:
            # Also reap on a normal worker interruption. No SQL finish and no
            # execution-slot release while the old child can still write.
            if child.poll() is None:
                child.kill()
            child.wait()
            child.stdin.close()
    if failure:
        with SessionLocal() as db:
            finish_run(db, run_id, epoch, RunStatus.FAILED, error_code=failure)


def _watch_parent() -> None:
    # Popen owns the sole writer. SIGKILL/worker exit closes it, so the child
    # cannot outlive that executor and later write under its still-current epoch.
    os.read(sys.stdin.fileno(), 1)
    os._exit(70)


def main() -> None:
    Thread(target=_watch_parent, daemon=True).start()
    # Start the parent watcher before importing parsers/model libraries.
    from backend.infrastructure.redis_client import init_sync_redis, close_sync_redis
    init_sync_redis()
    try:
        if len(sys.argv) > 3 and sys.argv[3] == 'document_import':
            from backend.services.document_imports import run_document_import
            run_document_import(sys.argv[1], int(sys.argv[2]))
        else:
            from backend.services.document_tasks import run_document_parse
            run_document_parse(sys.argv[1], int(sys.argv[2]))
    finally:
        close_sync_redis()


if __name__ == '__main__':
    main()
