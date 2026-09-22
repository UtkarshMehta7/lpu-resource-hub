"""Development-friendly console logging."""

from __future__ import annotations

import logging
import sys

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_HANDLER_NAME = "lpu-research-hub-console"


def configure_logging(level: str) -> None:
    """Send application and uvicorn logs to stdout in one readable format.

    Safe to call more than once: the handler installed by a previous call is
    replaced, and handlers installed by other tools (e.g. pytest) are kept.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        if handler.get_name() == _HANDLER_NAME:
            root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root.addHandler(handler)
    root.setLevel(level)

    # Route uvicorn's loggers through the root handler instead of their own.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
