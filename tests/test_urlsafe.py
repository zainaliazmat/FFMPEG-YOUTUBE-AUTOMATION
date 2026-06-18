import socket

from pipeline import urlsafe


def _fake_resolver(ip):
    """Return a getaddrinfo-shaped result that resolves any host to ``ip`` (no DNS)."""
    def resolver(host, port, proto=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, proto, "", (ip, port))]
    return resolver


def test_rejects_non_https_schemes():
    for url in ("http://example.com/", "file:///etc/passwd",
                "ftp://example.com/", "data:text/html,x"):
        ok, reason = urlsafe.is_safe_capture_url(url, _resolver=_fake_resolver("93.184.216.34"))
        assert not ok, url
        assert "https" in reason or "scheme" in reason


def test_rejects_loopback_link_local_private_metadata():
    cases = {
        "https://127.0.0.1/": "127.0.0.1",          # loopback
        "https://169.254.169.254/": "169.254.169.254",  # cloud metadata / link-local
        "https://10.0.0.5/": "10.0.0.5",            # private
        "https://192.168.1.1/": "192.168.1.1",      # private
    }
    for url, ip in cases.items():
        ok, reason = urlsafe.is_safe_capture_url(url, _resolver=_fake_resolver(ip))
        assert not ok, url
        assert "non-public" in reason


def test_rejects_public_host_that_redirects_to_internal():
    # The host string is public-looking but DNS resolves it to an internal IP
    # (rebinding / malicious redirect target). Must be rejected on the resolved IP.
    ok, reason = urlsafe.is_safe_capture_url(
        "https://evil.example.com/", _resolver=_fake_resolver("169.254.169.254"))
    assert not ok and "non-public" in reason


def test_accepts_public_https():
    ok, reason = urlsafe.is_safe_capture_url(
        "https://granola.ai/", _resolver=_fake_resolver("93.184.216.34"))
    assert ok and reason == "ok"


def test_dns_failure_is_rejected_not_raised():
    def boom(host, port, proto=0):
        raise socket.gaierror("no such host")
    ok, reason = urlsafe.is_safe_capture_url("https://nope.invalid/", _resolver=boom)
    assert not ok and "dns" in reason.lower()
