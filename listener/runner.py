"""Loop que mantém a sessão MaxGo e se reconecta após falhas."""

import logging
import signal
import time
import urllib.error
from threading import Event

import redis
import websocket

from listener.alerts import local_now, process_position_message
from listener.maxgo import MaxGoClient
from listener.stomp import ListenerStopped, consume_session, save_position
from listener.store import RedisStore
from listener.whatsapp import WhatsappEvolutionClient


logger = logging.getLogger(__name__)
MAX_RECONNECT_DELAY_SECONDS = 60


def install_signals(stop_event: Event) -> None:
    def handle(_signum, _frame):
        stop_event.set()

    signal.signal(signal.SIGINT, handle)
    signal.signal(signal.SIGTERM, handle)


def run_listener(stop_event, settings, *, store=None, open_session=None, fetch_token=None, client=None):
    """Mantém a sessão aberta e se reconecta após falhas de rede."""
    store = store or RedisStore(settings.redis_url)
    whatsapp = client or WhatsappEvolutionClient.from_settings(settings)

    def process(position):
        process_position_message(position, store, whatsapp, local_now(settings.timezone))

    def save(position, event):
        save_position(position, event, store, process)

    def default_session(token):
        consume_session(
            settings.stomp_url,
            settings.web_url,
            settings.vehicle_id,
            token,
            stop_event,
            save,
        )

    def default_token():
        return MaxGoClient(settings, store).stomp_token()

    open_session = open_session or default_session
    fetch_token = fetch_token or default_token
    reconnect_delay = 1
    while not stop_event.is_set():
        started = time.monotonic()
        try:
            store.ping()
            token = fetch_token()
            open_session(token)
        except ListenerStopped:
            break
        except (
            ConnectionError,
            OSError,
            TimeoutError,
            ValueError,
            urllib.error.URLError,
            redis.exceptions.ConnectionError,
            redis.exceptions.TimeoutError,
            websocket.WebSocketException,
        ) as error:
            logger.warning("Conexão MaxGo interrompida (%s)", type(error).__name__)
        if stop_event.is_set():
            break
        if time.monotonic() - started >= MAX_RECONNECT_DELAY_SECONDS:
            reconnect_delay = 1
        logger.info("Nova conexão MaxGo em %s s", reconnect_delay)
        if stop_event.wait(reconnect_delay):
            break
        reconnect_delay = min(reconnect_delay * 2, MAX_RECONNECT_DELAY_SECONDS)
