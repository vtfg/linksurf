from tests.fakes.broker import FakeBroker


class TestFakeBroker:
    async def test_records_messages_by_topic_with_priority(self):
        broker = FakeBroker()

        assert broker.messages.get("topic") is None

        await broker.publish("topic", "message1", 1)

        assert broker.messages.get("topic") == [("message1", 1)]

        await broker.publish("topic", "message2", 2)
        await broker.publish("topic", "message3", 3)

        assert broker.messages.get("topic") == [("message1", 1), ("message2", 2), ("message3", 3)]
