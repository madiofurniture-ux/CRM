"""Fetching a file from a link someone pasted (a vendor's product picture)
without letting the link reach the server's own network.

Only http(s) to public addresses: the host is resolved once, every address it
resolves to must be public, and the connection goes to that checked address
(so a second DNS answer can't point it somewhere else). Redirects are followed
a few times, each one checked the same way. A size cap, a timeout and a
content-type check finish it. No third-party packages.
"""
from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import time
from urllib.parse import urljoin, urlsplit

MAX_REDIRECTS = 3


class FetchError(ValueError):
    """Why the link wasn't fetched; the message is shown to the user as is."""


def _public_ip(host: str, port: int) -> str:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        raise FetchError("That web address couldn't be found.")
    ips = sorted({info[4][0] for info in infos})
    if not ips:
        raise FetchError("That web address couldn't be found.")
    for ip in ips:
        addr = ipaddress.ip_address(ip.split("%")[0])
        if not addr.is_global or addr.is_multicast:
            raise FetchError("That link points into a private network; use a public link or upload the file.")
    return ips[0]


class _PinnedHTTP(http.client.HTTPConnection):
    """Connects to the address already checked, whatever DNS says now."""

    def __init__(self, host: str, ip: str, port: int, timeout: float):
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host: str, ip: str, port: int, timeout: float):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def fetch(url: str, max_bytes: int, timeout: float = 10.0, accept: str = "image/") -> tuple[bytes, str]:
    """(body, content type) of a public http(s) link; FetchError otherwise."""
    url = str(url or "").strip()
    for _ in range(MAX_REDIRECTS + 1):
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise FetchError("Paste a link that starts with http:// or https://")
        if parts.username or parts.password:
            raise FetchError("Links with a user name or password in them aren't fetched.")
        try:
            port = parts.port or (443 if parts.scheme == "https" else 80)
        except ValueError:
            raise FetchError("That link's port isn't valid.")
        ip = _public_ip(parts.hostname, port)
        conn = (_PinnedHTTPS if parts.scheme == "https" else _PinnedHTTP)(parts.hostname, ip, port, timeout)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        try:
            conn.request("GET", path, headers={"User-Agent": "MADIO-CRM/1.0", "Accept": f"{accept}*" if accept else "*/*"})
            res = conn.getresponse()
            if res.status in (301, 302, 303, 307, 308) and res.getheader("Location"):
                url = urljoin(url, res.getheader("Location"))
                continue
            if res.status != 200:
                raise FetchError(f"The link answered with an error ({res.status}).")
            ctype = (res.getheader("Content-Type") or "").split(";")[0].strip().lower()
            if accept and not ctype.startswith(accept):
                raise FetchError("That link isn't a picture. Open the picture itself and copy its address.")
            length = res.getheader("Content-Length") or ""
            if length.isdigit() and int(length) > max_bytes:
                raise FetchError("That picture is too large.")
            deadline, body = time.monotonic() + timeout * 3, bytearray()
            while True:
                chunk = res.read(65536)
                if not chunk:
                    break
                body += chunk
                if len(body) > max_bytes:
                    raise FetchError("That picture is too large.")
                if time.monotonic() > deadline:
                    raise FetchError("That link is too slow; download the picture and upload it instead.")
            return bytes(body), ctype
        except (OSError, http.client.HTTPException) as e:
            raise FetchError("Couldn't fetch that link.") from e
        finally:
            conn.close()
    raise FetchError("That link redirects too many times.")
