"""Estado do listener em Redis, com valores JSON e sem prefixo do Django."""

import json

import redis


POSITION_HISTORY_KEY = "position_history"
POSITION_HISTORY_LIMIT = 20


class RedisStore:
    def __init__(self, url: str):
        self.url = url
        self.client = redis.Redis.from_url(
            url,
            socket_connect_timeout=5,
            socket_timeout=5,
            decode_responses=True,
        )

    def ping(self) -> None:
        self.client.ping()

    def get_json(self, key: str):
        raw = self.client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    def set_json(self, key: str, value, ttl: int | None = None) -> None:
        payload = json.dumps(value, separators=(",", ":"))
        if ttl is None:
            self.client.set(key, payload)
        else:
            self.client.set(key, payload, ex=ttl)

    def set_nx(self, key: str, value, ttl: int) -> bool:
        payload = json.dumps(value, separators=(",", ":"))
        return bool(self.client.set(key, payload, nx=True, ex=ttl))

    def delete(self, key: str) -> None:
        self.client.delete(key)

    def append_history(self, position: dict) -> list:
        if not isinstance(position, dict):
            raise ValueError("Mensagem de posição não é um objeto JSON")
        history = self.get_json(POSITION_HISTORY_KEY)
        if not isinstance(history, list):
            history = []
        if len(history) >= POSITION_HISTORY_LIMIT:
            history = history[-(POSITION_HISTORY_LIMIT - 1) :]
        history.append(position)
        self.set_json(POSITION_HISTORY_KEY, history)
        return history
