"""WhatsApp de chegada e de ignição noturna."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from listener.alerts import (
    alert_movement,
    process_come_home,
    process_position_message,
)
from listener.config import load_settings
from listener.whatsapp import WhatsappEvolutionClient
from tests.memory import MemoryStore
from tests.test_config import valid_env


BAHIA = ZoneInfo("America/Bahia")
OUTSIDE = {
    "tipo": "POSICAO",
    "veiculoId": 1778506,
    "latitude": -5.9,
    "longitude": -35.3,
    "ignicao": "DESLIGADA",
    "ultimaTransmissao": "28/09/2026 20:36:57",
}
INSIDE = {
    **OUTSIDE,
    "latitude": -5.8314,
    "longitude": -35.2073937,
    "ignicao": "LIGADA",
}


class Client:
    def __init__(self, fail=False):
        self.messages = []
        self.fail = fail

    def send_message(self, text):
        if self.fail:
            raise ConnectionError("evolution down")
        self.messages.append(text)


def at(hour):
    return datetime(2026, 10, 22, hour, 15, tzinfo=BAHIA)


def test_send_message_posts_to_emergency_contact():
    settings = load_settings(
        valid_env(
            EVOLUTION_SERVER_URL="http://evolution-api:8080/",
            EVOLUTION_PERSONAL_INSTANCE_NAME="RichardPessoal",
            EMERGENCY_CONTACT="5584888888888",
            EVOLUTION_API_KEY="secret-key",
        )
    )
    captured = {}

    class Response:
        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Opener:
        def open(self, request, timeout=None):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode())
            captured["timeout"] = timeout
            return Response()

    client = WhatsappEvolutionClient.from_settings(settings, opener=Opener())
    assert client.BASE_URL == "http://evolution-api:8080"
    client.send_message("Chegando em casa")
    assert captured["url"] == (
        "http://evolution-api:8080/message/sendText/RichardPessoal"
    )
    assert captured["body"] == {
        "number": "5584888888888",
        "text": "Chegando em casa",
    }
    headers = {name.lower(): value for name, value in captured["headers"].items()}
    assert headers["apikey"] == "secret-key"
    assert captured["timeout"] == 10


def test_enter_home_sends_once_and_records_hour():
    store = MemoryStore()
    client = Client()
    now = at(15)
    store.set_json("come_home", False)
    process_position_message(INSIDE, store, client, now)
    assert client.messages == ["Chegando em casa"]
    assert store.get_json("come_home") is True
    assert store.get_json(f"come_home:logged:{now:%Y%m%d%H}") is True
    assert store.ttl[f"come_home:logged:{now:%Y%m%d%H}"] == 3600


def test_already_home_and_first_point_do_not_send():
    store = MemoryStore()
    client = Client()
    process_position_message(INSIDE, store, client, at(15))
    assert client.messages == []
    assert store.get_json("come_home") is True

    process_position_message(INSIDE, store, client, at(15))
    assert client.messages == []


def test_leaving_home_does_not_send():
    store = MemoryStore()
    client = Client()
    store.set_json("come_home", True)
    process_position_message(OUTSIDE, store, client, at(15))
    assert client.messages == []
    assert store.get_json("come_home") is False


def test_second_entry_in_the_same_hour_does_not_send():
    store = MemoryStore()
    client = Client()
    now = at(18)
    store.set_json("come_home", False)
    process_position_message(INSIDE, store, client, now)
    process_position_message(OUTSIDE, store, client, now)
    store.set_json("come_home", False)
    process_position_message(INSIDE, store, client, now)
    assert client.messages == ["Chegando em casa"]


def test_evolution_failure_on_arrival_releases_hour_key_and_keeps_going():
    store = MemoryStore()
    client = Client(fail=True)
    now = at(18)
    store.set_json("come_home", False)
    process_position_message(INSIDE, store, client, now)
    assert store.get_json(f"come_home:logged:{now:%Y%m%d%H}") is None
    assert store.get_json("come_home") is True


def test_each_critical_ignition_alerts_and_daytime_does_not():
    store = MemoryStore()
    client = Client()
    process_position_message(OUTSIDE, store, client, at(22))
    assert client.messages == []
    process_position_message({**OUTSIDE, "ignicao": "LIGADA"}, store, client, at(23))
    process_position_message(INSIDE, store, client, at(23))
    alerts = [message for message in client.messages if message != "Chegando em casa"]
    assert len(alerts) == 2
    assert client.messages.count("Chegando em casa") == 1
    process_position_message(INSIDE, store, client, at(6))
    alerts = [message for message in client.messages if message != "Chegando em casa"]
    assert len(alerts) == 2


def test_first_critical_position_without_previous_marks_coordinates_unavailable():
    store = MemoryStore()
    client = Client()
    position = {
        "veiculoId": 1778506,
        "latitude": -5.9,
        "longitude": -35.3,
        "ignicao": "LIGADA",
        "ultimaTransmissao": "01/01/2026 00:10:00",
    }
    process_position_message(position, store, client, at(0))
    assert len(client.messages) == 1
    assert "indisponível" in client.messages[0]
    assert "-5.9, -35.3" in client.messages[0]


def test_ignition_off_at_night_does_not_alert():
    store = MemoryStore()
    client = Client()
    process_position_message(OUTSIDE, store, client, at(1))
    assert client.messages == []


def test_alert_text_without_plate_uses_whatsapp():
    client = Client()
    position = {
        "veiculoId": 1778506,
        "latitude": -5.9,
        "longitude": -35.3,
        "ignicao": "LIGADA",
        "ultimaTransmissao": "01/01/2026 00:10:00",
    }
    alert_movement(client, None, position)
    text = client.messages[0]
    assert "Ignição ligada" in text
    assert "sem placa" in text
    assert "-5.9, -35.3" in text
    assert "01/01/2026 00:10:00" in text


def test_night_alert_failure_does_not_raise():
    client = Client(fail=True)
    alert_movement(client, None, {**INSIDE, "placa": None})


def test_process_come_home_and_alert_are_plain_functions():
    assert process_come_home.__name__ == "process_come_home"
    assert not hasattr(process_come_home, "delay")
    assert not hasattr(alert_movement, "delay")


def test_arrival_and_movement_share_the_contact(monkeypatch):
    posted = []

    class Response:
        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Opener:
        def open(self, request, timeout=None):
            posted.append(json.loads(request.data.decode()))
            return Response()

    settings = load_settings(valid_env(EMERGENCY_CONTACT="5584777777777"))
    client = WhatsappEvolutionClient.from_settings(settings, opener=Opener())
    store = MemoryStore()
    store.set_json("come_home", False)
    process_come_home(client, store, at(20))
    alert_movement(client, None, INSIDE)
    assert {item["number"] for item in posted} == {"5584777777777"}
    assert posted[0]["text"] == "Chegando em casa"
    assert "Ignição ligada" in posted[1]["text"]
