"""Leitura e validação do ambiente do listener."""

from dataclasses import dataclass
from urllib.parse import urlsplit


DEFAULT_STOMP_URL = "wss://srvskr.logicasolucoes.com.br/stomp"
DEFAULT_EVOLUTION_URL = "http://evolution-api:8080"
DEFAULT_TIMEZONE = "America/Bahia"


class ConfigError(ValueError):
    """Ambiente insuficiente para abrir a sessão."""


@dataclass(frozen=True)
class Settings:
    web_url: str
    api_url: str
    stomp_url: str
    username: str
    password: str
    vehicle_id: int
    redis_url: str
    evolution_base_url: str
    evolution_api_key: str
    evolution_instance: str
    emergency_contact: str
    timezone: str


def _missing(env, names):
    return [name for name in names if not env.get(name, "").strip()]


def load_settings(env=None) -> Settings:
    """Valida o ambiente e devolve a configuração. Não abre socket."""
    source = env if env is not None else __import__("os").environ
    missing = _missing(
        source,
        (
            "MAXGO_WEB_URL",
            "MAXGO_API_URL",
            "MAXGO_USERNAME",
            "MAXGO_PASSWORD",
            "MAXGO_VEHICLE_ID",
        ),
    )
    if missing:
        raise ConfigError(f"Configuração MaxGo ausente: {', '.join(missing)}")

    web_url = source["MAXGO_WEB_URL"].strip().rstrip("/")
    api_url = source["MAXGO_API_URL"].strip().rstrip("/")
    stomp_raw = source.get("MAXGO_STOMP_URL", "").strip() or DEFAULT_STOMP_URL
    stomp_url = stomp_raw.rstrip("/")
    if any(
        urlsplit(url).scheme != "https" or not urlsplit(url).hostname
        for url in (web_url, api_url)
    ):
        raise ConfigError("MAXGO_WEB_URL e MAXGO_API_URL devem usar HTTPS")
    if urlsplit(stomp_url).scheme != "wss" or not urlsplit(stomp_url).hostname:
        raise ConfigError("MAXGO_STOMP_URL deve usar WSS")
    try:
        vehicle_id = int(source["MAXGO_VEHICLE_ID"].strip())
    except ValueError as error:
        raise ConfigError("MAXGO_VEHICLE_ID deve ser um inteiro") from error
    if vehicle_id <= 0:
        raise ConfigError("MAXGO_VEHICLE_ID deve ser positivo")

    missing_alerts = _missing(
        source,
        (
            "EVOLUTION_API_KEY",
            "EVOLUTION_PERSONAL_INSTANCE_NAME",
            "EMERGENCY_CONTACT",
        ),
    )
    if missing_alerts:
        raise ConfigError(f"Configuração de aviso ausente: {', '.join(missing_alerts)}")
    redis_url = source.get("REDIS_URL", "").strip()
    if not redis_url:
        raise ConfigError("Configuração ausente: REDIS_URL")

    evolution_url = (
        source.get("EVOLUTION_SERVER_URL", "").strip() or DEFAULT_EVOLUTION_URL
    ).rstrip("/")
    timezone = source.get("TZ", "").strip() or DEFAULT_TIMEZONE
    return Settings(
        web_url=web_url,
        api_url=api_url,
        stomp_url=stomp_url,
        username=source["MAXGO_USERNAME"].strip(),
        password=source["MAXGO_PASSWORD"],
        vehicle_id=vehicle_id,
        redis_url=redis_url,
        evolution_base_url=evolution_url,
        evolution_api_key=source["EVOLUTION_API_KEY"].strip(),
        evolution_instance=source["EVOLUTION_PERSONAL_INSTANCE_NAME"].strip(),
        emergency_contact=source["EMERGENCY_CONTACT"].strip(),
        timezone=timezone,
    )
