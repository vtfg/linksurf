from dataclasses import dataclass

from linksurf.common.constants import DEFAULT_IDENTIFIER, DEFAULT_USER_AGENT


@dataclass(frozen=True)
class Settings:
    identifier: str = DEFAULT_IDENTIFIER
    user_agent: str = DEFAULT_USER_AGENT
    proxy: str = None
