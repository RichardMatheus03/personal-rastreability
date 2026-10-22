"""Validação de ambiente e escolha do database Redis."""

import pytest

from listener.config import DEFAULT_STOMP_URL, ConfigError, load_settings
from listener.__main__ import main


def valid_env(**overrides):
    env = {
        "MAXGO_WEB_URL": "https://maxgo.example.test",
        "MAXGO_API_URL": "https://api.example.test",
        "MAXGO_USERNAME": "user",
        "MAXGO_PASSWORD": "secret",
        "MAXGO_VEHICLE_ID": "42",
        "REDIS_URL": "redis://redis:6379/1",
        "EVOLUTION_API_KEY": "key",
        "EVOLUTION_PERSONAL_INSTANCE_NAME": "pessoal",
        "EMERGENCY_CONTACT": "5584999999999",
    }
    env.update(overrides)
    return env


def test_missing_username_names_the_variable_and_main_does_not_connect(monkeypatch):
    monkeypatch.delenv("MAXGO_WEB_URL", raising=False)
    env = valid_env(MAXGO_USERNAME="")
    with pytest.raises(ConfigError, match="MAXGO_USERNAME"):
        load_settings(env)

    def fail():
        raise ConfigError("Configuração MaxGo ausente: MAXGO_USERNAME")

    monkeypatch.setattr("listener.__main__.load_settings", fail)
    called = {}
    monkeypatch.setattr(
        "listener.__main__.run_listener",
        lambda *_args, **_kwargs: called.setdefault("ran", True),
    )
    assert main() == 1
    assert "ran" not in called


def test_invalid_vehicle_id():
    with pytest.raises(ConfigError, match="MAXGO_VEHICLE_ID"):
        load_settings(valid_env(MAXGO_VEHICLE_ID="placa"))
    with pytest.raises(ConfigError, match="positivo"):
        load_settings(valid_env(MAXGO_VEHICLE_ID="0"))


def test_default_stomp_url_and_evolution_base():
    settings = load_settings(valid_env())
    assert settings.stomp_url == DEFAULT_STOMP_URL
    assert settings.evolution_base_url == "http://evolution-api:8080"


def test_missing_evolution_key():
    with pytest.raises(ConfigError, match="EVOLUTION_API_KEY"):
        load_settings(valid_env(EVOLUTION_API_KEY=""))


def test_redis_url_is_used_as_written():
    settings = load_settings(valid_env(REDIS_URL="redis://redis:6379/1"))
    assert settings.redis_url == "redis://redis:6379/1"


def test_missing_redis_url():
    with pytest.raises(ConfigError, match="REDIS_URL"):
        load_settings(valid_env(REDIS_URL=""))


def test_https_and_wss_are_required():
    with pytest.raises(ConfigError, match="HTTPS"):
        load_settings(valid_env(MAXGO_WEB_URL="http://maxgo.example.test"))
    with pytest.raises(ConfigError, match="WSS"):
        load_settings(valid_env(MAXGO_STOMP_URL="ws://stomp.example.test/stomp"))
