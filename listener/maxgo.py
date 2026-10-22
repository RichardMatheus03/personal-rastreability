"""Login MaxGo e leitura do stompToken, com sessão em Redis."""

import hashlib
import http.cookiejar
import json
import logging
import urllib.error
import urllib.parse
import urllib.request


logger = logging.getLogger(__name__)

TOKEN_TTL_SECONDS = 5 * 60 * 60


class SameHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = urllib.parse.urlsplit(req.full_url)
        new = urllib.parse.urlsplit(newurl)
        if new.scheme != "https" or new.hostname != old.hostname:
            raise ValueError("Redirecionamento inesperado; operação interrompida.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class MaxGoClient:
    def __init__(self, settings, store, opener=None):
        self.settings = settings
        self.store = store
        account = (
            f"{settings.web_url}\0{settings.api_url}\0{settings.username}"
        ).encode()
        self.token_cache_key = (
            f"maxgo:session:{hashlib.sha256(account).hexdigest()}"
        )
        self.token = None
        self.jar = http.cookiejar.CookieJar()
        self.web = opener or urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            SameHostRedirect(),
        )
        self.api = opener or urllib.request.build_opener(SameHostRedirect())

    def login(self, force=False):
        if not force:
            cached = self.store.get_json(self.token_cache_key)
            if cached:
                self.token = cached
                return
        self.jar.clear()
        self.token = None
        web = self.settings.web_url
        with self.web.open(web + "/login/login", timeout=30) as response:
            response.read()
        data = urllib.parse.urlencode(
            {
                "username": self.settings.username,
                "password": self.settings.password,
            }
        ).encode()
        request = urllib.request.Request(
            web + "/login/login",
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": web,
                "Referer": web + "/login/login",
            },
        )
        with self.web.open(request, timeout=30) as response:
            response.read()
            if "/login/" in urllib.parse.urlsplit(response.url).path:
                raise ValueError("Login não concluído. Verifique as credenciais.")
        self.token = next(
            (cookie.value for cookie in self.jar if cookie.name == "LGSESSIONID"),
            None,
        )
        if not self.token:
            raise ValueError("O login não forneceu LGSESSIONID.")
        self.store.set_json(self.token_cache_key, self.token, TOKEN_TTL_SECONDS)

    def get(self, path, retry=True):
        if not self.token:
            self.token = self.store.get_json(self.token_cache_key)
        if not self.token:
            if not retry:
                raise ValueError("Sessão ausente ou expirada.")
            self.login()
        request = urllib.request.Request(
            self.settings.api_url + path,
            headers={"LGSESSIONID": self.token, "Accept": "application/json"},
        )
        try:
            with self.api.open(request, timeout=30) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 401 and retry:
                cached = self.store.get_json(self.token_cache_key)
                if cached and cached != self.token:
                    self.token = cached
                else:
                    self.store.delete(self.token_cache_key)
                    self.login(force=True)
                return self.get(path, retry=False)
            raise
        if not isinstance(result, dict) or result.get("ok") is False:
            raise ValueError("A API não confirmou sucesso.")
        info = result.get("userInfo") or {}
        new_token = info.get("LGSESSIONID") or result.get("LGSESSIONID")
        if new_token and new_token != self.token:
            self.token = new_token
            self.store.set_json(self.token_cache_key, self.token, TOKEN_TTL_SECONDS)
        return result

    def stomp_token(self) -> str:
        self.login()
        props = self.get("/front/getProps")
        token = (props.get("userInfo") or {}).get("stompToken")
        if not token:
            raise ValueError("A MaxGo não retornou userInfo.stompToken")
        logger.info("stompToken MaxGo obtido")
        return token
