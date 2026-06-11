from linksurf.common.settings import Settings


class Service:
    NAME: str

    def on_start(self, settings: Settings) -> None:
        pass

    def on_stop(self):
        pass
