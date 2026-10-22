"""Sessão SockJS/STOMP com a MaxGo e gravação das posições."""

from collections import deque
from contextlib import closing
import json
import logging
import secrets
import time

import redis
import websocket

from listener.store import POSITION_HISTORY_LIMIT


logger = logging.getLogger(__name__)

POSITION_DESTINATION = "/user/queue/posicao"
DEFINED_DESTINATION = "/user/queue/definido"
MONITORING_DESTINATION = "/user/queue/monitorando"
SOCKET_TIMEOUT_SECONDS = 15
SOCKJS_IDLE_TIMEOUT_SECONDS = 90
MAX_RECONNECT_DELAY_SECONDS = 60


class ListenerStopped(Exception):
    """O processo recebeu uma solicitação de parada."""


def send_frame(connection, frame):
    connection.send(json.dumps([frame], separators=(",", ":")))


def receive_frame(connection, pending, stop_event, deadline=None):
    last_wire_message = time.monotonic()
    while True:
        if stop_event.is_set():
            raise ListenerStopped()
        if pending:
            raw = pending.popleft()
            if raw in ("\n", "\r\n"):
                continue
            header, separator, body = raw.partition("\n\n")
            if not separator:
                raise ValueError("Frame STOMP sem separador de cabeçalhos")
            lines = header.split("\n")
            command = lines[0].strip("\r")
            headers = dict(
                line.rstrip("\r").split(":", 1) for line in lines[1:] if ":" in line
            )
            if command == "ERROR":
                raise ValueError("A MaxGo enviou um frame STOMP ERROR")
            if command == "MESSAGE":
                logger.info(
                    "Mensagem MaxGo recebida via websocket: destino=%s",
                    headers.get("destination"),
                )
            return command, headers, body.rstrip("\x00")

        now = time.monotonic()
        if deadline is not None and now >= deadline:
            raise TimeoutError("A resposta STOMP não chegou no prazo")
        if now - last_wire_message >= SOCKJS_IDLE_TIMEOUT_SECONDS:
            raise TimeoutError("Sessão SockJS sem mensagens ou heartbeat")
        wait_seconds = min(
            SOCKET_TIMEOUT_SECONDS,
            SOCKJS_IDLE_TIMEOUT_SECONDS - (now - last_wire_message),
        )
        if deadline is not None:
            wait_seconds = min(wait_seconds, deadline - now)
        connection.settimeout(wait_seconds)
        try:
            message = connection.recv()
        except websocket.WebSocketTimeoutException:
            continue
        last_wire_message = time.monotonic()
        if message == "h":
            continue
        if message.startswith("c"):
            raise ConnectionError("A MaxGo fechou a sessão SockJS")
        if not message.startswith("a"):
            raise ValueError("Mensagem SockJS inesperada")
        frames = json.loads(message[1:])
        if not isinstance(frames, list) or not all(
            isinstance(frame, str) for frame in frames
        ):
            raise ValueError("Array SockJS inválido")
        pending.extend(frames)


def save_position(position, stop_event, store, process) -> None:
    delay = 1
    while not stop_event.is_set():
        try:
            history = store.append_history(position)
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError):
            logger.warning("Redis indisponível; nova tentativa em %s s", delay)
            if stop_event.wait(delay):
                break
            delay = min(delay * 2, MAX_RECONNECT_DELAY_SECONDS)
            continue
        logger.info(
            "Posição MaxGo armazenada: veículo=%s tipo=%s latitude=%s longitude=%s "
            "ignição=%s transmissão=%s; histórico=%s/%s",
            position.get("veiculoId"),
            position.get("tipo"),
            position.get("latitude"),
            position.get("longitude"),
            position.get("ignicao"),
            position.get("ultimaTransmissao"),
            len(history),
            POSITION_HISTORY_LIMIT,
        )
        process(position)
        return
    raise ListenerStopped()


def next_message(connection, pending, stop_event, destination, save):
    deadline = time.monotonic() + SOCKET_TIMEOUT_SECONDS
    while True:
        command, headers, body = receive_frame(
            connection, pending, stop_event, deadline
        )
        if command != "MESSAGE":
            continue
        if headers.get("destination") == POSITION_DESTINATION:
            save(json.loads(body), stop_event)
        if headers.get("destination") == destination:
            return body


def consume_session(
    stomp_url,
    web_url,
    vehicle_id,
    token,
    stop_event,
    save,
    connect=None,
):
    server = f"{secrets.randbelow(1000):03d}"
    session = secrets.token_hex(4)
    url = f"{stomp_url}/{server}/{session}/websocket"
    connect = connect or websocket.create_connection
    with closing(
        connect(url, origin=web_url, timeout=SOCKET_TIMEOUT_SECONDS)
    ) as connection:
        if connection.recv() != "o":
            raise ValueError("A MaxGo não abriu a sessão SockJS")

        pending = deque()
        send_frame(
            connection,
            f"CONNECT\ntoken:{token}\naccept-version:1.1,1.0\n"
            "heart-beat:0,10000\n\n\x00",
        )
        command, _, _ = receive_frame(
            connection, pending, stop_event, time.monotonic() + SOCKET_TIMEOUT_SECONDS
        )
        if command != "CONNECTED":
            raise ValueError("A MaxGo não confirmou CONNECTED")

        for index, destination in enumerate(
            (POSITION_DESTINATION, DEFINED_DESTINATION, MONITORING_DESTINATION)
        ):
            send_frame(
                connection,
                f"SUBSCRIBE\nid:sub-{index}\ndestination:{destination}\n\n\x00",
            )
        send_frame(
            connection,
            f"SEND\ndestination:/app/defineMonitoramento\n\n{token}:mapaReact\x00",
        )
        next_message(connection, pending, stop_event, DEFINED_DESTINATION, save)

        body = json.dumps({"veiculoId": vehicle_id}, separators=(",", ":"))
        send_frame(connection, f"SEND\ndestination:/app/monitoramento\n\n{body}\x00")
        monitored = json.loads(
            next_message(
                connection, pending, stop_event, MONITORING_DESTINATION, save
            )
        )
        if not isinstance(monitored, list) or str(vehicle_id) not in {
            str(item) for item in monitored
        }:
            raise ValueError("A MaxGo não confirmou o veículo monitorado")
        logger.info("Monitoramento STOMP ativo para veículo %s", vehicle_id)

        while not stop_event.is_set():
            command, headers, body = receive_frame(connection, pending, stop_event)
            if (
                command == "MESSAGE"
                and headers.get("destination") == POSITION_DESTINATION
            ):
                save(json.loads(body), stop_event)
