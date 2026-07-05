import socket
from typing import Tuple


def check_domain_availability(domain, port=80, timeout=5.0) -> Tuple[bool, str | None]:
    """
    Checks domain availability and retrieves its IP.

    (thanks Gemini ;D)

    :param domain: The domain name (e.g., 'example.com' or 'google.com')
    :param port: 80 for HTTP, 443 for HTTPS
    :param timeout: Seconds to wait before giving up on the connection
    :return: Tuple[bool, str] (available, ip)
    """

    try:
        ip_address = socket.gethostbyname(domain)
    except socket.gaierror:
        # domain does not exist or DNS lookup failed
        return False, None

    # check reachability via raw TCP handshake
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            # connect_ex returns 0 on success instead of raising an exception
            result = s.connect_ex((ip_address, port))

            if result == 0:
                return True, ip_address
            else:
                return False, ip_address  # DNS exists, but server is dead/blocking

        except socket.timeout:
            return False, ip_address
        except Exception:
            return False, ip_address  # other network errors (e.g., connection refused)
