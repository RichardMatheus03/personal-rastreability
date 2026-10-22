"""Redis em memória para os testes do listener."""

import copy

import redis


class MemoryStore:
    def __init__(self):
        self.data = {}
        self.ttl = {}
        self.append_failures = 0
        self.pings = 0

    def ping(self):
        self.pings += 1

    def get_json(self, key):
        if key not in self.data:
            return None
        return copy.deepcopy(self.data[key])

    def set_json(self, key, value, ttl=None):
        self.data[key] = copy.deepcopy(value)
        if ttl is None:
            self.ttl.pop(key, None)
        else:
            self.ttl[key] = ttl

    def set_nx(self, key, value, ttl):
        if key in self.data:
            return False
        self.set_json(key, value, ttl)
        return True

    def delete(self, key):
        self.data.pop(key, None)
        self.ttl.pop(key, None)

    def append_history(self, position):
        if self.append_failures:
            self.append_failures -= 1
            raise redis.exceptions.ConnectionError("redis down")
        from listener.store import RedisStore

        history = RedisStore.append_history(self, position)
        return history
