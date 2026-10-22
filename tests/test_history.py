"""Histórico, snapshots e retry de Redis."""

import json
from threading import Event

from listener.alerts import process_position_message
from listener.stomp import consume_session, save_position
from listener.store import POSITION_HISTORY_KEY
from tests.memory import MemoryStore


class Client:
    def __init__(self):
        self.messages = []

    def send_message(self, text):
        self.messages.append(text)


def test_history_keeps_latest_twenty():
    store = MemoryStore()
    previous = [{"veiculoId": 42, "sequence": index} for index in range(19)]
    store.set_json(POSITION_HISTORY_KEY, previous)
    newest = {"veiculoId": 42, "sequence": 19}
    store.append_history(newest)
    history = store.get_json(POSITION_HISTORY_KEY)
    assert len(history) == 20
    assert history[-1] == newest

    oldest = history[0]
    extra = {"veiculoId": 42, "sequence": 20}
    store.append_history(extra)
    trimmed = store.get_json(POSITION_HISTORY_KEY)
    assert oldest not in trimmed
    assert trimmed[-1] == extra
    assert len(trimmed) == 20
    assert store.ttl.get(POSITION_HISTORY_KEY) is None


def test_alive_is_stored_without_snapshot():
    store = MemoryStore()
    alive = {"tipo": "ALIVE", "veiculoId": 1778506}
    store.append_history(alive)
    process_position_message(alive, store, Client(), __import__("datetime").datetime(2026, 1, 1, 23))
    assert store.get_json(POSITION_HISTORY_KEY) == [alive]
    assert store.get_json("maxgo:position:1778506") is None
    assert store.get_json("maxgo:ignition:1778506") is None


def test_position_snapshot_and_missing_coordinates():
    store = MemoryStore()
    client = Client()
    now = __import__("datetime").datetime(2026, 1, 1, 12)
    position = {
        "tipo": "POSICAO",
        "veiculoId": 7,
        "latitude": -5.1,
        "longitude": -35.2,
        "ignicao": "DESLIGADA",
    }
    process_position_message(position, store, client, now)
    assert store.get_json("maxgo:position:7") == position
    assert store.get_json("maxgo:ignition:7") == "DESLIGADA"

    incomplete = {"tipo": "POSICAO", "veiculoId": 8, "longitude": -35.2}
    process_position_message(incomplete, store, client, now)
    assert store.get_json("maxgo:position:8") is None


def test_alive_on_the_wire_is_appended():
    alive = {"tipo": "ALIVE", "veiculoId": 9}
    connection = __import__("unittest").mock.MagicMock()
    connection.recv.side_effect = [
        "o",
        "a" + json.dumps(["CONNECTED\nversion:1.1\n\n\x00"]),
        "a" + json.dumps(["MESSAGE\ndestination:/user/queue/definido\n\nok\x00"]),
        "a" + json.dumps(["MESSAGE\ndestination:/user/queue/monitorando\n\n[9]\x00"]),
        "a"
        + json.dumps(
            [
                "MESSAGE\ndestination:/user/queue/posicao\n\n"
                + json.dumps(alive)
                + "\x00"
            ]
        ),
    ]
    stop_event = Event()
    store = MemoryStore()

    def save(position, _event):
        store.append_history(position)
        if position.get("tipo") == "ALIVE":
            stop_event.set()

    consume_session(
        "wss://example.test/stomp",
        "https://example.test",
        9,
        "token",
        stop_event,
        save,
        connect=lambda *args, **kwargs: connection,
    )
    assert store.get_json(POSITION_HISTORY_KEY) == [alive]


def test_redis_recovery_processes_once():
    store = MemoryStore()
    store.append_failures = 1
    processed = []
    stop_event = Event()
    stop_event.wait = lambda _delay: False
    position = {"tipo": "POSICAO", "veiculoId": 1}
    save_position(position, stop_event, store, processed.append)
    assert store.get_json(POSITION_HISTORY_KEY) == [position]
    assert processed == [position]


def test_stop_while_redis_is_down_raises_without_processing():
    from listener.stomp import ListenerStopped

    store = MemoryStore()
    store.append_failures = 5
    processed = []
    stop_event = Event()
    stop_event.wait = lambda _delay: True
    position = {"tipo": "POSICAO", "veiculoId": 1}
    with __import__("pytest").raises(ListenerStopped):
        save_position(position, stop_event, store, processed.append)
    assert processed == []
    assert store.get_json(POSITION_HISTORY_KEY) is None
