"""Offline regressions for URL identity, pagination and listing contracts."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from eporner_api import api as api


class EmptyStream:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class UrlHandlingTests(unittest.IsolatedAsyncioTestCase):
    async def test_filtered_profile_fetches_two_distinct_pages(self):
        media = api.Pornstar(url="https://de.eporner.com/pornstar/Example/4/?quality=hd&page=9#videos", core=object())
        capture = Mock(return_value=EmptyStream())
        from contextlib import ExitStack

        with ExitStack() as stack:
            for name in ("scrape_stream", "_scrape_stream"):
                if hasattr(api, name):
                    stack.enter_context(patch.object(api, name, capture))
            if hasattr(api, "Helper"):
                stack.enter_context(patch.object(api, "Helper", lambda **kwargs: SimpleNamespace(iterator=capture)))
            stack.enter_context(patch.object(api.Pornstar, "get_field", AsyncMock(return_value=2)))
            async for _ in media.videos(pages=2):
                pass
        urls = capture.call_args.kwargs["target_page_urls"]
        self.assertEqual(
            urls,
            [
                "https://de.eporner.com/pornstar/Example/1?quality=hd",
                "https://de.eporner.com/pornstar/Example/2?quality=hd",
            ],
        )

    def test_listing_resolves_relative_links_once(self):
        html = '<div class="mb" data-id="AbC123"><p class="mbtit"><a href="/video-AbC123/title/">Example</a></p></div>'
        rows = api.extractor(html, base_url="https://de.eporner.com")
        self.assertEqual(rows[0]["url"], "https://de.eporner.com/video-AbC123/title/")

    def test_embed_id_does_not_include_query(self):
        video = api.Video(url="https://de.eporner.com/embed/AbC123/?utm_source=share", core=object())
        self.assertEqual(video.video_id, "AbC123")
        self.assertEqual(video.url, "https://de.eporner.com/video-AbC123/?utm_source=share")


if __name__ == "__main__":
    unittest.main()
