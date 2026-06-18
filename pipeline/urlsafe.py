"""SSRF guard for capture URLs.

The human URL-confirmation gate in yt-capture is a CORRECTNESS gate (is this the
right product?), NOT a security boundary. A human pasting ``https://granola.ai/``
does not vet redirects or internal addresses. Without this check, Playwright (or a
plain image download) would happily load ``file:///etc/passwd``,
``http://169.254.169.254/`` (cloud metadata), ``http://localhost:.../`` or a public
URL that 30x-redirects to an internal host, and bake the result into the video
(autoplan eng F13).

``is_safe_capture_url`` enforces: https only, and the host must resolve exclusively
to public addresses. Call it on the confirmed URL AND re-check every redirect hop.
"""
import ipaddress
import socket
from urllib.parse import urlparse


def _ip_is_public(ip_str):
    ip = ipaddress.ip_address(ip_str)
    blocked = (ip.is_private or ip.is_loopback or ip.is_link_local
               or ip.is_reserved or ip.is_multicast or ip.is_unspecified)
    return not blocked, ip


def is_safe_capture_url(url, _resolver=socket.getaddrinfo):
    """Return ``(ok: bool, reason: str)``.

    Rejects non-https schemes and any host that resolves to a private, loopback,
    link-local, reserved, multicast or unspecified address. ``_resolver`` is
    injectable for tests; defaults to real DNS.
    """
    try:
        p = urlparse(url)
    except Exception as exc:  # noqa: BLE001 - defensive: never raise to caller
        return False, f"unparseable url: {exc}"

    if p.scheme != "https":
        return False, f"scheme must be https (got {p.scheme or 'none'!r})"
    host = p.hostname
    if not host:
        return False, "url has no host"

    try:
        infos = _resolver(host, 443, proto=socket.IPPROTO_TCP)
    except Exception as exc:  # noqa: BLE001
        return False, f"dns resolution failed for {host!r}: {exc}"
    if not infos:
        return False, f"{host!r} did not resolve"

    for info in infos:
        addr = info[4][0]
        public, ip = _ip_is_public(addr)
        if not public:
            return False, f"{host!r} resolves to non-public address {ip}"
    return True, "ok"
