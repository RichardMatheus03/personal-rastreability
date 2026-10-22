"""Cliente HTTP da Evolution API para as mensagens do listener."""

import json
import urllib.error
import urllib.request


class WhatsappEvolutionClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        instance_name: str,
        emergency_contact: str,
        timeout: int = 10,
        opener=None,
    ):
        self.BASE_URL = base_url.rstrip("/")
        self.api_key = api_key
        self.instance_name = instance_name
        self.emergency_contact = emergency_contact
        self.timeout = timeout
        self.opener = opener or urllib.request.build_opener()

    @classmethod
    def from_settings(cls, settings, opener=None):
        return cls(
            base_url=settings.evolution_base_url,
            api_key=settings.evolution_api_key,
            instance_name=settings.evolution_instance,
            emergency_contact=settings.emergency_contact,
            opener=opener,
        )

    def send_message(self, text: str) -> None:
        url = f"{self.BASE_URL}/message/sendText/{self.instance_name}"
        body = json.dumps(
            {"number": self.emergency_contact, "text": text},
            separators=(",", ":"),
        ).encode()
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "apikey": self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                response.read()
        except urllib.error.HTTPError as error:
            raise ConnectionError(
                f"Evolution recusou a mensagem ({error.code})"
            ) from error
