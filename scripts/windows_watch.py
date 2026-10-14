"""Private Windows scheduled-task entrypoint with single-instance locking.

Launches the installed read-only watcher; it never logs tokens or credentials.
The per-user lock prevents duplicate watchers even if launched manually.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import msvcrt
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / ".state"
LOG_DIR = ROOT / "logs"


class LineLogger:
    """Turn CLI print output into line-buffered, size-limited local log entries."""

    def __init__(self, logger: logging.Logger, level: int):
        self.logger = logger
        self.level = level
        self.pending = ""

    def write(self, value: str) -> int:
        self.pending += str(value)
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            if line.strip():
                self.logger.log(self.level, line.rstrip("\r"))
        return len(value)

    def flush(self) -> None:
        if self.pending.strip():
            self.logger.log(self.level, self.pending.rstrip("\r"))
            self.pending = ""

    def isatty(self) -> bool:
        return False


def _logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("bupt-activity-watch")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = RotatingFileHandler(
            LOG_DIR / "watch.log",
            maxBytes=1_000_000,
            backupCount=2,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def main() -> int:
    os.chdir(ROOT)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    logger = _logger()

    # Windows holds the one-byte lock until the process exits, even after a crash.
    # Keep this lock file rather than deleting it (deletion creates a race).
    lock_path = STATE_DIR / "watch.lock"
    lock_file = lock_path.open("a+b")
    if lock_file.tell() == 0:
        lock_file.write(b"\0")
        lock_file.flush()
    lock_file.seek(0)
    try:
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        logger.warning("Another local watcher is already active; exiting.")
        lock_file.close()
        return 0

    sys.path.insert(0, str(ROOT / "src"))
    from bupt_activity_notifier.cli import main as watch_main

    sys.stdout = LineLogger(logger, logging.INFO)
    sys.stderr = LineLogger(logger, logging.ERROR)
    logger.info("Watcher started (pid=%s, foreground account task).", os.getpid())

    try:
        while True:
            try:
                result = watch_main(["--watch", "--state", str(STATE_DIR / "seen.json")])
                if result == 0:
                    logger.info("Watcher exited normally.")
                    return 0
                logger.error("Watcher returned nonzero status %s; retrying.", result)
            except Exception as exc:
                # Avoid exception messages which could contain HTTP query parameters.
                logger.error("Watcher crashed: %s; retrying.", type(exc).__name__)
            time.sleep(60)
    finally:
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        lock_file.close()


if __name__ == "__main__":
    raise SystemExit(main())
