import hashlib
from urllib.parse import urlsplit, parse_qsl, urlencode, urlunsplit


def hash_url(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


# Query parameters that carry no crawl-relevant information.
# Based on common tracking parameters from Google, Facebook, HubSpot, Mailchimp, etc.
_TRACKING_PARAMS = {
    # Shared
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_source_platform", "utm_creative_format", "utm_marketing_tactic",

    # Google Analytics / Ads
    "gclid", "gclsrc", "gbraid", "wbraid", "dclid",

    # Facebook / Meta
    "fbclid", "fb_action_ids", "fb_action_types", "fb_source",

    # Microsoft
    "msclkid",

    # HubSpot
    "hsa_acc", "hsa_cam", "hsa_grp", "hsa_ad", "hsa_src", "hsa_tgt",
    "hsa_kw", "hsa_mt", "hsa_net", "hsa_ver",

    # Mailchimp
    "mc_cid", "mc_eid",

    # Other common trackers
    "yclid", "igshid", "twclid", "_hsenc", "_hsmi",
    "ref", "referrer",
}


def normalize_url(url: str) -> str:
    split = urlsplit(url)

    scheme = split.scheme.lower()
    domain = split.netloc.lower()

    # remove default ports (80 for http, 443 for https)
    if ":" in domain:
        hostname, port = domain.rsplit(":", 1)
        if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
            domain = hostname

    path = split.path or "/"

    # remove trailing slash on non-root paths
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    # strip tracking query parameters and sort the rest
    params = [
        (k, v) for k, v in parse_qsl(split.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(sorted(params))

    # fragments are client-side
    fragment = ""

    normalized = urlunsplit((scheme, domain, path, query, fragment))

    return normalized
