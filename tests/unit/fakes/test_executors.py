import pytest

from linksurf.common.models import URL
from linksurf.common.payload import Payload
from linksurf.components.base import FilterResponse
from tests.fakes.executors import FakeExecutor, FakeFilter


class TestFakeExecutor:
    async def test_records_executions_and_function_call_counts(self):
        payload = Payload(URL("https://example.com"))
        response = FilterResponse(True, None)
        executor = FakeFilter()

        executor.mock(response)

        result = await executor.execute(payload)
        await executor.on_start(object(), object())
        await executor.on_stop()

        assert result is response
        assert executor.executions == [payload]
        assert executor.calls == {
            "execute": 1,
            "on_start": 1,
            "on_stop": 1,
        }

    async def test_mock_replaces_existing_behavior(self):
        payload = Payload(URL("https://example.com"))
        executor = FakeFilter()

        executor.mock(FilterResponse(True, None))
        first = await executor.execute(payload)

        executor.mock(FilterResponse(False, None))
        second = await executor.execute(payload)

        assert first.data == True
        assert second.data == False
        assert executor.executions == [payload, payload]
        assert executor.calls["execute"] == 2

    async def test_mock_can_raise_an_exception(self):
        payload = Payload(URL("https://example.com"))
        executor = FakeFilter()
        executor.mock(RuntimeError("filter failed"))

        with pytest.raises(RuntimeError, match="filter failed"):
            await executor.execute(payload)

        assert executor.executions == [payload]
        assert executor.calls["execute"] == 1

    async def test_mock_accepts_async_callable_behavior(self):
        payload = Payload(URL("https://example.com"))
        executor = FakeFilter()

        async def behavior(executed_payload):
            assert executed_payload is payload

            return FilterResponse(False, None)

        executor.mock(behavior)

        response = await executor.execute(payload)

        assert response.data == False

    async def test_counts_private_function_calls(self):
        payload = Payload(URL("https://example.com"))

        class ExecutorWithPrivateFunction(FakeExecutor):
            async def execute(self, executed_payload):
                return self._prepare(executed_payload)

            def _prepare(self, executed_payload):
                return executed_payload

        executor = ExecutorWithPrivateFunction()

        result = await executor.execute(payload)

        assert result is payload
        assert executor.executions == [payload]
        assert executor.calls == {
            "execute": 1,
            "_prepare": 1,
        }

    async def test_can_track_an_existing_executor_implementation(self):
        payload = Payload(URL("https://example.com"))

        class ExistingExecutor:
            async def execute(self, executed_payload):
                return self._prepare(executed_payload)

            def _prepare(self, executed_payload):
                return executed_payload

        class TrackedExecutor(ExistingExecutor, FakeExecutor):
            pass

        executor = TrackedExecutor()

        result = await executor.execute(payload)

        assert result is payload
        assert executor.calls == {
            "execute": 1,
            "_prepare": 1,
        }
