from linksurf.common.models import Country, URL
from linksurf.common.payload import Payload
from linksurf.components.frontier.filters import CountryFilter, RobotsExclusionFilter, URLExtensionFilter
from linksurf.components.frontier.middlewares import CountryMiddleware, RobotsExclusionMiddleware


class TestCountryFilter:
    def test_initializes_with_passed_arguments(self):
        filter = CountryFilter(allowed=[Country.BRAZIL, Country.USA])

        assert filter.allowed == [Country.BRAZIL, Country.USA]
        assert filter.DEPENDS_ON == [CountryMiddleware]

    async def test_filters_correctly(self):
        payload1 = Payload(url=URL("https://example.com/"), metadata={"country": "BR"})
        payload2 = Payload(url=URL("https://example.com/"), metadata={"country": "US"})
        payload3 = Payload(url=URL("https://example.com/"), metadata={"country": "ZZ"})
        payload4 = Payload(url=URL("https://example.com/"))

        filter = CountryFilter(allowed=[Country.BRAZIL])

        response1 = await filter.execute(payload1)

        assert response1.error is None
        assert response1.data is True

        response2 = await filter.execute(payload2)

        assert response2.error is None
        assert response2.data is False

        response3 = await filter.execute(payload3)

        assert response3.error is None
        assert response3.data is False

        response4 = await filter.execute(payload4)

        assert response4.error is None
        assert response4.data is False


class TestURLExtensionFilter:
    def test_initializes_with_passed_arguments(self):
        filter = URLExtensionFilter(allowed=["html", "htm"])

        assert filter.allowed == ["html", "htm"]

    async def test_filters_correctly(self):
        payload1 = Payload(url=URL("https://example.com/"), metadata={"extension": "html"})
        payload2 = Payload(url=URL("https://example.com/"), metadata={"extension": "htm"})
        payload3 = Payload(url=URL("https://example.com/"), metadata={"extension": "php"})
        payload4 = Payload(url=URL("https://example.com/"))

        filter = URLExtensionFilter(allowed=["html", "htm"])

        response1 = await filter.execute(payload1)

        assert response1.error is None
        assert response1.data is True

        response2 = await filter.execute(payload2)

        assert response2.error is None
        assert response2.data is True

        response3 = await filter.execute(payload3)

        assert response3.error is None
        assert response3.data is False

        response4 = await filter.execute(payload4)

        assert response4.error is None
        assert response4.data is False


class TestRobotsExclusionFilter:
    def test_defines_dependency(self):
        filter = RobotsExclusionFilter()

        assert filter.DEPENDS_ON == [RobotsExclusionMiddleware]

    async def test_filters_correctly(self):
        payload1 = Payload(url=URL("https://example.com/"), metadata={"robots": {"can_fetch": True}})
        payload2 = Payload(url=URL("https://example.com/"), metadata={"robots": {"can_fetch": False}})
        payload3 = Payload(url=URL("https://example.com/"), metadata={"robots": {}})

        filter = RobotsExclusionFilter()

        response1 = await filter.execute(payload1)

        assert response1.error is None
        assert response1.data is True

        response2 = await filter.execute(payload2)

        assert response2.error is None
        assert response2.data is False

        response3 = await filter.execute(payload3)

        assert response3.error is None
        assert response3.data is False
