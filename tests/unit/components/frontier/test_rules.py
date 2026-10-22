from linksurf.common.models import URL
from linksurf.common.payload import Payload
from linksurf.components.frontier.rules import SchemeRule, URLExtensionRule, URLLimitsRule, BlockedDomainsRule, \
    BLOCKED_EXTENSIONS


class TestSchemeRules:
    async def test_initializes_with_passed_argument(self):
        rule = SchemeRule(allowed=[])

        assert rule.allowed == []

        rule = SchemeRule(allowed=["http", "https"])

        assert rule.allowed == ["http", "https"]

    async def test_blocks_correctly(self):
        payload1 = Payload(url=URL("http://example.com"))
        payload2 = Payload(url=URL("https://example.com"))
        payload3 = Payload(url=URL("ftp://example.com"))
        payload4 = Payload(url=URL("file://example.txt"))

        rule = SchemeRule(allowed=["http", "https"])

        response1 = await rule.execute(payload1)

        assert response1.error is None
        assert response1.data is True

        response2 = await rule.execute(payload2)

        assert response2.error is None
        assert response2.data is True

        response3 = await rule.execute(payload3)

        assert response3.error is None
        assert response3.data is False

        response4 = await rule.execute(payload4)

        assert response4.error is None
        assert response4.data is False


class TestURLExtensionRule:
    async def test_initializes_with_default_arguments(self):
        rule = URLExtensionRule()

        assert rule.blocked == BLOCKED_EXTENSIONS

    async def test_initializes_with_passed_arguments(self):
        rule = URLExtensionRule(blocked=[".webp", ".rar", ".iso"])

        assert rule.blocked == {"webp", "rar", "iso"}

    async def test_uses_custom_blocked_extensions(self):
        payload1 = Payload(url=URL("https://example.com/admin.php"))
        payload2 = Payload(url=URL("https://example.com/image.webp"))

        rule = URLExtensionRule(blocked=[".PHP"])

        response1 = await rule.execute(payload1)

        assert response1.error is None
        assert response1.data is False

        response2 = await rule.execute(payload2)

        assert response2.error is None
        assert response2.data is True

    async def test_blocks_correctly(self):
        payload1 = Payload(url=URL("https://example.com/"))
        payload2 = Payload(url=URL("https://example.com/index.html"))
        payload3 = Payload(url=URL("https://example.com/index.htm"))
        payload4 = Payload(url=URL("https://example.com/admin.php"))
        payload5 = Payload(url=URL("https://example.com/image.webp"))
        payload6 = Payload(url=URL("https://example.com/backup.tar.gz"))

        rule = URLExtensionRule()

        response1 = await rule.execute(payload1)

        assert response1.error is None
        assert response1.data is True

        response2 = await rule.execute(payload2)

        assert response2.error is None
        assert response2.data is True

        response3 = await rule.execute(payload3)

        assert response3.error is None
        assert response3.data is True

        response4 = await rule.execute(payload4)

        assert response4.error is None
        assert response4.data is True

        response5 = await rule.execute(payload5)

        assert response5.error is None
        assert response5.data is False

        response6 = await rule.execute(payload6)

        assert response6.error is None
        assert response6.data is False


class TestURLLimitsRule:
    async def test_initializes_with_passed_arguments(self):
        rule = URLLimitsRule(max_length=100, max_path_depth=3)

        assert rule.max_length == 100
        assert rule.max_path_depth == 3

    async def test_allows_url_at_maximum_length(self):
        payload = Payload(url=URL("https://example.com/a"))

        rule = URLLimitsRule(max_length=len(payload.url.address), max_path_depth=10)

        response = await rule.execute(payload)

        assert response.error is None
        assert response.data is True

    async def test_blocks_correctly(self):
        payload1 = Payload(url=URL("https://example.com/"))
        payload2 = Payload(url=URL("https://example.com/a/b"))
        payload3 = Payload(url=URL("https://example.com/a/b/c"))
        payload4 = Payload(url=URL("https://example.com/this-path-is-too-long"))

        rule = URLLimitsRule(max_length=30, max_path_depth=2)

        response1 = await rule.execute(payload1)

        assert response1.error is None
        assert response1.data is True

        response2 = await rule.execute(payload2)

        assert response2.error is None
        assert response2.data is True

        response3 = await rule.execute(payload3)

        assert response3.error is None
        assert response3.data is False

        response4 = await rule.execute(payload4)

        assert response4.error is None
        assert response4.data is False


class TestBlockedDomainsRule:
    async def test_initializes_with_passed_arguments(self):
        rule = BlockedDomainsRule(blocked=["example.com", "blocked.test", "example.com"])

        assert rule.blocked == {"example.com", "blocked.test"}

    async def test_blocks_correctly(self):
        payload1 = Payload(url=URL("https://example.com/"))
        payload2 = Payload(url=URL("https://example.com:8443/path"))
        payload3 = Payload(url=URL("https://www.example.com/"))
        payload4 = Payload(url=URL("https://allowed.test/"))

        rule = BlockedDomainsRule(blocked=["example.com"])

        response1 = await rule.execute(payload1)

        assert response1.error is None
        assert response1.data is False

        response2 = await rule.execute(payload2)

        assert response2.error is None
        assert response2.data is False

        response3 = await rule.execute(payload3)

        assert response3.error is None
        assert response3.data is True

        response4 = await rule.execute(payload4)

        assert response4.error is None
        assert response4.data is True
