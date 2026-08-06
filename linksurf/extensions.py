from __future__ import annotations

from typing import TYPE_CHECKING

from linksurf.common.settings import Settings
from linksurf.services import Services

if TYPE_CHECKING:
    from linksurf.application import Linksurf


class Extension:
    """
    Increment the application's behavior by implementing new components, services and listeners,
    and also define new elements (rules, middlewares, filters, etc.) for the existing components.

    They serve as a quick behavior change that allows grouping related modifications in a single file.

    Extensions can be HTTP servers, like an Admin Panel that shows metrics about the crawler,
    or implement lifecycle events/scheduled events (e.g. to check proxies periodically).
    """

    # TODO: Create application callbacks so extensions can inject data into payloads or requests objects.
    # ^ Useful for user-agent rotation or proxy pool extensions.

    def __init__(self, application: Linksurf, settings: Settings, services: Services):
        """
        Function used to inject all components needed for the extension inside the application.
        """

        self.application = application

    async def on_start(self):
        """
        Function used to start the extension and its required components (which were not injected).

        "Start" in this context means creating any database connection or requesting required data asynchronously.
        """

        raise NotImplementedError()

    async def on_stop(self):
        """
        Function used to gracefully stop the extension and its required components (which were not injected).
        """

        raise NotImplementedError()
