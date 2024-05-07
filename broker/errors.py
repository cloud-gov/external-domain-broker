import logging
import sys


def handle_exception(exc_type, exc_value, exc_traceback):
    """log exceptions explicitly, so they get json-ified"""
    logger = logging.getLogger(__name__)
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.exception(
        "Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback)
    )
