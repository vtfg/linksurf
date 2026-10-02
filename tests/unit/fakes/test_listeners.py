from linksurf.events import ComponentLoopEvent, ComponentSubscribeEvent
from linksurf.events.bus import EventBus


class TestFakeListener:
    async def test_counts_all_events_by_name(self, listener):
        bus = EventBus()

        await bus.emit(ComponentSubscribeEvent(component="Frontier", topic="process"))
        await bus.emit(ComponentLoopEvent(component="Downloader", function="download"))
        await bus.emit(ComponentSubscribeEvent(component="Parser", topic="parse"))
        await bus.emit(ComponentSubscribeEvent(component="Storage", topic="store"))

        assert listener.calls == {
            "component.subscribe": 3,
            "component.loop": 1,
        }

    def test_starts_empty_for_each_test(self, listener):
        assert listener.calls == {}
