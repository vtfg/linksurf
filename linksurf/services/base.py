from linksurf.common.settings import Settings


class Service:
    NAME: str

    async def on_start(self, settings: Settings) -> None:
        raise NotImplementedError()

    async def on_stop(self):
        raise NotImplementedError()
