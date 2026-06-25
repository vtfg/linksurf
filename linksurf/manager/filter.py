from ipaddress import ip_address
from pathlib import PurePosixPath
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from linksurf.helpers import get_domain_name

_BLOCKED_EXTENSIONS = {
    # Executables & installers
    "exe", "dmg", "pkg", "deb", "rpm", "msi", "apk", "ipa", "appimage",
    # Archives
    "zip", "tar", "gz", "xz", "bz2", "7z", "rar", "zst", "lz4", "cab",
    # Disk images
    "iso", "img", "bin",
    # Documents
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp",
    # Images
    "png", "jpg", "jpeg", "gif", "webp", "svg", "ico", "bmp", "tiff", "avif",
    # Media
    "mp3", "mp4", "avi", "mkv", "mov", "wmv", "flv", "webm", "ogg", "wav",
    "m4a", "m4v", "aac", "flac",
    # Fonts
    "woff", "woff2", "ttf", "eot", "otf",
    # Code & data
    "css", "js", "json", "xml", "csv", "tsv", "yaml", "yml", "toml",
    # Other
    "torrent", "map", "wasm",
}

_TRACKING_PARAMS = {
    # UTMs
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    # Google
    "gclid", "dclid", "_ga", "_gl",
    # Meta
    "fbclid",
    # Microsoft
    "msclkid",
    # Session IDs
    "sessionid", "session_id", "sid", "phpsessid",
}

_BLOCKED_DOMAINS = {
    # Google
    "google.com", "googleapis.com", "googletagmanager.com", "gstatic.com",
    "googleusercontent.com", "youtube.com", "youtu.be", "gmail.com",
    # Meta
    "facebook.com", "instagram.com", "whatsapp.com", "threads.com", "meta.com", "fb.com", "fbcdn.net",
    # Apple
    "apple.com", "icloud.com",
    # Amazon
    "amazon.com", "amazonaws.com", "aws.amazon.com",
    # Microsoft
    "microsoft.com", "live.com", "outlook.com", "hotmail.com", "bing.com", "msn.com",
    # Netflix
    "netflix.com",
    # X / Twitter
    "twitter.com", "x.com", "t.co",
    # LinkedIn
    "linkedin.com",
    # TikTok
    "tiktok.com",
    # Snapchat
    "snapchat.com",
    # Pinterest
    "pinterest.com",
    # Reddit
    "reddit.com",
    # Spotify
    "spotify.com",
    # Adobe
    "adobe.com",
    # Salesforce
    "salesforce.com",
    # PayPal
    "paypal.com",
    # Cloudflare
    "cloudflare.com",
    # Shopify
    "shopify.com",
    # WordPress
    "wordpress.com", "wp.com",
    # Tracking / analytics
    "doubleclick.net", "googlesyndication.com", "adservice.google.com",
}

_MAX_URL_LENGTH = 2048
_MAX_PATH_DEPTH = 10


def is_brazilian_tld(url: str) -> bool:
    hostname = urlsplit(url).hostname

    return hostname is not None and hostname.endswith(".br")


def normalize_url(url: str) -> str:
    parsed = urlsplit(url)

    params = []

    for k, v in parse_qsl(parsed.query):
        if k.lower() not in _TRACKING_PARAMS:
            params.append((k, v))

    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(params), ""))


_BR_GOVERNMENT_SLDS = {
    "gov",  # executive / general government
    "leg",  # legislative
    "jus",  # judiciary
    "mp",   # Ministério Público
    "def",  # Defensoria Pública
    "tc",   # Tribunais de Contas
    "mil",  # military
}


def is_br_government_domain(url: str) -> bool:
    hostname = urlsplit(url).hostname

    if hostname is None:
        return False

    parts = hostname.rstrip(".").split(".")

    return (
        len(parts) >= 2
        and parts[-1] == "br"
        and parts[-2] in _BR_GOVERNMENT_SLDS
    )


def is_domain_blocked(url: str) -> bool:
    netloc = get_domain_name(url)

    return any(netloc == d or netloc.endswith(f".{d}") for d in _BLOCKED_DOMAINS)


def is_url_allowed(url: str) -> bool:
    if urlsplit(url).scheme not in ("http", "https"):
        return False

    if is_domain_blocked(url):
        return False

    if is_br_government_domain(url):
        return False

    if len(url) > _MAX_URL_LENGTH:
        return False

    parsed = urlsplit(url)
    hostname = parsed.hostname

    if hostname:
        if hostname == "localhost":
            return False

        try:
            ip = ip_address(hostname)

            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
        except ValueError:
            pass

    path = PurePosixPath(parsed.path)

    if len(path.parts[1:]) > _MAX_PATH_DEPTH:
        return False

    suffix = path.suffix.lstrip(".").lower()

    return suffix not in _BLOCKED_EXTENSIONS
