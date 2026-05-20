from linksurf.broker.base import Broker
from linksurf.common.models import URL
from linksurf.components.downloader import Downloader
from linksurf.components.frontier import Frontier
from linksurf.components.parser import Parser
from linksurf.components.storage import Storage
from linksurf.services import Services


class Linksurf:
    def __init__(self, services: Services, broker: Broker):
        self.services = services
        self.broker = broker

        self.frontier = Frontier()
        self.downloader = Downloader()
        self.parser = Parser()
        self.storage = Storage()

    def run(self, seed: list[URL]) -> None:
        self.services.connect()

        self.broker.connect()

        for component in [self.frontier, self.downloader, self.parser, self.storage]:
            component.on_start(self.services)

        # self.broker.pipeline([
        #     ("urls", self.downloader.download),
        #     ("files", self.parser.parse),
        #     ("contents", self.storage.store),
        #     ("links", self.manager.enqueue),
        # ])

        # Order shouldn't matter. What matters is the component's CONSUMES_FROM and PRODUCES_TO.
        self.broker.pipeline([
            self.frontier,
            self.downloader,
            self.parser,
            self.storage
        ])

        for url in seed:
            self.broker.seed("links", url)

        self.broker.loop()
