import socket
from typing import Tuple
from urllib.parse import urlsplit

import socks


def check_domain_availability(domain, port=80, timeout=5.0, proxy: str | None = None) -> Tuple[bool, str | None]:
    """
    Checks domain availability and retrieves its IP.

    When `proxy` is set (a `socks5://[user:pass@]host:port` URL), the connection is routed through it via SOCKS5's remote-DNS support,
    so both the reachability, result and the resolved IP reflect the proxy's vantage point.

    :param domain: The domain name (e.g., 'example.com' or 'google.com')
    :param port: 80 for HTTP, 443 for HTTPS
    :param timeout: Seconds to wait before giving up on the connection
    :param proxy: socks5://[user:pass@]host:port, or None to connect directly
    :return: Tuple[bool, str] (available, ip)
    """

    sock = _build_socket(proxy)
    sock.settimeout(timeout)

    try:
        with sock:
            sock.connect((domain, port))

            ip = sock.getproxysockname()[0] if proxy else sock.getpeername()[0]

            return True, ip
    except Exception:
        # covers unresolved domains, refused/timed-out connections, and SOCKS-specific
        # failures (proxy auth, proxy-side resolution failure, etc.) alike
        return False, None


def _build_socket(proxy: str | None) -> socket.socket:
    if proxy is None:
        return socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    parsed = urlsplit(proxy)

    sock = socks.socksocket()
    sock.set_proxy(
        socks.SOCKS5,
        addr=parsed.hostname,
        port=parsed.port,
        username=parsed.username,
        password=parsed.password,
        rdns=True,  # resolve on the proxy's side, not locally
    )

    return sock
