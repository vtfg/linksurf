from linksurf.common.payload import Payload
from linksurf.components.base import Rule, RuleResponse


class SchemeRule(Rule):
    def __init__(self, allowed: list[str]):
        self.allowed = allowed

    async def execute(self, payload: Payload) -> RuleResponse:
        if payload.url.scheme not in self.allowed:
            return RuleResponse(False, None)

        return RuleResponse(True, None)


BLOCKED_EXTENSIONS = {
    # images
    "avif", "bmp", "gif", "ico", "j2c", "j2k", "jfif", "jp2", "jpeg", "jpg",
    "jpx", "mng", "pct", "png", "psd", "svg", "tif", "tiff", "webp", "xbm",

    # audio
    "aac", "flac", "m4a", "mp3", "ogg", "wav", "wma",

    # video
    "avi", "flv", "m4v", "mov", "mp4", "mpeg", "mpg", "ogv", "qt", "webm", "wmv",

    # archives
    "7z", "apk", "bz2", "dmg", "gz", "iso", "jar", "pkg", "rar", "tar", "tgz",
    "whl", "zip",

    # executables / installers
    "bin", "deb", "exe", "msi", "rpm",

    # fonts
    "otf", "ttf", "woff", "woff2",

    # documents
    "pdf", "ps",

    # web assets
    "css", "js", "swf",
}


class URLExtensionRule(Rule):
    def __init__(self, blocked: list[str] | None = None):
        if blocked is None:
            self.blocked = BLOCKED_EXTENSIONS
        else:
            self.blocked = {ext.lstrip(".").lower() for ext in blocked}

    async def execute(self, payload: Payload) -> RuleResponse:
        extension = payload.url.extension

        if extension is not None and extension in self.blocked:
            return RuleResponse(False, None)

        return RuleResponse(True, None)


class URLLimitsRule(Rule):
    def __init__(self, max_length: int, max_path_depth: int):
        self.max_length = max_length
        self.max_path_depth = max_path_depth

    async def execute(self, payload: Payload) -> RuleResponse:
        if len(payload.url.address) > self.max_length:
            return RuleResponse(False, None)

        if payload.url.path_depth > self.max_path_depth:
            return RuleResponse(False, None)

        return RuleResponse(True, None)


class BlockedDomainsRule(Rule):
    def __init__(self, blocked: list[str]):
        self.blocked = set(blocked)

    async def execute(self, payload: Payload) -> RuleResponse:
        if payload.url.domain in self.blocked:
            return RuleResponse(False, None)

        return RuleResponse(True, None)
