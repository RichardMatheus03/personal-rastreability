"""Chegada em casa e alerta noturno de ignição, sem Celery."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from listener.geofence import contains_home


logger = logging.getLogger(__name__)

ARRIVAL_TEXT = "Chegando em casa"
HOUR_KEY_TTL_SECONDS = 3600


def alert_text(previous_position: dict | None, current_position: dict) -> str:
    previous = previous_position or {}
    plate = current_position.get("placa") or previous.get("placa") or "sem placa"
    vehicle_id = (
        current_position.get("veiculoId")
        or previous.get("veiculoId")
        or current_position.get("id")
        or previous.get("id")
    )
    event = (
        "Ignição ligada"
        if current_position.get("ignicao") == "LIGADA"
        else "Movimentação detectada"
    )
    if "latitude" in previous and "longitude" in previous:
        previous_coordinates = f"{previous['latitude']}, {previous['longitude']}"
    else:
        previous_coordinates = "indisponível"
    return (
        f"{event} para o veículo {plate} (ID: {vehicle_id}).\n\n"
        f"Posição anterior: {previous_coordinates}\n"
        f"Posição atual: {current_position.get('latitude')}, "
        f"{current_position.get('longitude')}\n"
        f"Última transmissão: {current_position.get('ultimaTransmissao')}\n"
    )


def process_come_home(client, store, now: datetime) -> None:
    """Envia 'Chegando em casa' no máximo uma vez por hora local."""
    hour_key = f"come_home:logged:{now:%Y%m%d%H}"
    if not store.set_nx(hour_key, True, HOUR_KEY_TTL_SECONDS):
        return
    try:
        client.send_message(ARRIVAL_TEXT)
    except Exception:
        store.delete(hour_key)
        logger.warning("Falha ao enviar chegada em casa; a sessão STOMP segue")


def alert_movement(client, previous_position, current_position) -> None:
    """Envia o texto de ignição por WhatsApp. Falha não fecha a sessão."""
    try:
        client.send_message(alert_text(previous_position, current_position))
    except Exception:
        logger.warning("Falha ao enviar alerta de ignição; a sessão STOMP segue")


def process_position_message(position, store, client, now: datetime) -> None:
    if not isinstance(position, dict):
        raise ValueError("Mensagem de posição MaxGo deve ser um objeto JSON")
    if position.get("tipo") not in (None, "POSICAO"):
        return

    vehicle_id = position.get("veiculoId")
    latitude, longitude = position.get("latitude"), position.get("longitude")
    if vehicle_id is None or latitude is None or longitude is None:
        logger.warning("Posição MaxGo sem veículo ou coordenadas; alerta ignorado")
        return

    position_key = f"maxgo:position:{vehicle_id}"
    ignition_key = f"maxgo:ignition:{vehicle_id}"
    previous_position = store.get_json(position_key)
    ignition = position.get("ignicao")
    previous_home = store.get_json("come_home")
    is_home = contains_home(longitude, latitude)
    if previous_home is False and is_home:
        process_come_home(client, store, now)
    store.set_json("come_home", is_home)

    if (now.hour >= 23 or now.hour < 6) and ignition == "LIGADA":
        alert_movement(client, previous_position, position)

    store.set_json(position_key, position)
    store.set_json(ignition_key, ignition)


def local_now(timezone: str) -> datetime:
    return datetime.now(ZoneInfo(timezone))
