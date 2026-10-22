"""Sessão STOMP, token em cache e reconexão."""

import json
import signal
from threading import Event
from unittest.mock import MagicMock, patch

from listener.config import load_settings
from listener.maxgo import MaxGoClient
from listener.runner import install_signals, run_listener
from listener.stomp import consume_session
from tests.memory import MemoryStore
from tests.test_config import valid_env


def sockjs_message(frame):
    return "a" + json.dumps([frame])


def test_cached_session_skips_login_form():
    store = MemoryStore()
    settings = load_settings(valid_env())
    account_key = MaxGoClient(settings, store).token_cache_key
    store.set_json(account_key, "cached-session")
    requests = []

    class Opener:
        def open(self, request, timeout=None):
            url = getattr(request, "full_url", request)
            requests.append((getattr(request, "data", None), url))
            if str(url).endswith("/front/getProps"):
                payload = json.dumps(
                    {"ok": True, "userInfo": {"stompToken": "stomp-1"}}
                ).encode()

                class Response:
                    def read(self):
                        return payload

                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        return False

                return Response()
            raise AssertionError(f"HTTP inesperado: {url}")

    client = MaxGoClient(settings, store, opener=Opener())
    assert client.stomp_token() == "stomp-1"
    assert all(data is None or b"username=" not in data for data, _url in requests)
    assert any(str(url).endswith("/front/getProps") for _data, url in requests)


def test_vehicle_confirmed_accepts_later_position():
    first = {"veiculoId": 42, "latitude": -5.1, "longitude": -35.2}
    connection = MagicMock()
    connection.recv.side_effect = [
        "o",
        sockjs_message("CONNECTED\nversion:1.1\n\n\x00"),
        sockjs_message("MESSAGE\ndestination:/user/queue/definido\n\nok\x00"),
        sockjs_message(
            "MESSAGE\ndestination:/user/queue/monitorando\n\n" + json.dumps([42]) + "\x00"
        ),
        sockjs_message(
            "MESSAGE\ndestination:/user/queue/posicao\n\n" + json.dumps(first) + "\x00"
        ),
    ]
    stop_event = Event()
    saved = []

    def save(position, _stop_event):
        saved.append(position)
        stop_event.set()

    consume_session(
        "wss://example.test/stomp",
        "https://example.test",
        42,
        "test-token",
        stop_event,
        save,
        connect=lambda *args, **kwargs: connection,
    )
    assert saved == [first]
    connection.close.assert_called_once_with()


def test_vehicle_rejected_schedules_reconnect():
    settings = load_settings(valid_env(MAXGO_VEHICLE_ID="42"))
    stop_event = Event()
    attempts = []

    def open_session(_token):
        attempts.append(1)
        if len(attempts) == 1:
            raise ValueError("A MaxGo não confirmou o veículo monitorado")
        stop_event.set()

    with patch.object(stop_event, "wait", return_value=False):
        run_listener(
            stop_event,
            settings,
            store=MemoryStore(),
            open_session=open_session,
            fetch_token=lambda: "token",
        )
    assert len(attempts) == 2


def test_socket_close_opens_another_session():
    settings = load_settings(valid_env())
    stop_event = Event()
    attempts = []

    def open_session(_token):
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError("conexão interrompida")
        stop_event.set()

    with patch.object(stop_event, "wait", return_value=False):
        run_listener(
            stop_event,
            settings,
            store=MemoryStore(),
            open_session=open_session,
            fetch_token=lambda: "token",
        )
    assert len(attempts) == 2


def test_long_session_resets_delay(monkeypatch):
    settings = load_settings(valid_env())
    stop_event = Event()
    clock = {"now": 0.0}

    def monotonic():
        return clock["now"]

    def open_session(_token):
        clock["now"] = 61.0
        raise ConnectionError("caiu")

    waits = []

    def wait(delay):
        waits.append(delay)
        stop_event.set()
        return True

    monkeypatch.setattr("listener.runner.time.monotonic", monotonic)
    with patch.object(stop_event, "wait", side_effect=wait):
        run_listener(
            stop_event,
            settings,
            store=MemoryStore(),
            open_session=open_session,
            fetch_token=lambda: "token",
        )
    assert waits == [1]


def test_sigterm_exits_without_another_session():
    settings = load_settings(valid_env())
    stop_event = Event()
    attempts = []
    previous_term = signal.getsignal(signal.SIGTERM)
    previous_int = signal.getsignal(signal.SIGINT)

    def open_session(_token):
        attempts.append(1)
        raise ConnectionError("caiu")

    def wait(_delay):
        install_signals(stop_event)
        signal.raise_signal(signal.SIGTERM)
        return stop_event.is_set()

    try:
        with patch.object(stop_event, "wait", side_effect=wait):
            run_listener(
                stop_event,
                settings,
                store=MemoryStore(),
                open_session=open_session,
                fetch_token=lambda: "token",
            )
    finally:
        signal.signal(signal.SIGTERM, previous_term)
        signal.signal(signal.SIGINT, previous_int)
    assert attempts == [1]
