"""Processo do listener MaxGo."""

import logging
import sys
from threading import Event

from listener.config import ConfigError, load_settings
from listener.runner import install_signals, run_listener


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        settings = load_settings()
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 1
    stop_event = Event()
    install_signals(stop_event)
    run_listener(stop_event, settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
