import pytest
from base_api import BaseCore
from ..api import Client, Category

@pytest.mark.asyncio
async def test_category():
    core = BaseCore()
    core.configuration.pages_concurrency = 1
    core.configuration.videos_concurrency = 1
    client = Client(core)

    videos_1 = client.get_videos_by_category(category=Category.JAPANESE)
    videos_2 = client.get_videos_by_category(category=Category.HD)
    videos_3 = client.get_videos_by_category(category=Category.BLONDE)

    idx = 0
    async for result in videos_1:
        if idx == 3:
            break
        video = result.unwrap()
        assert isinstance(video.title, str) and len(video.title) > 0
        idx += 1

    idx = 0
    async for result in videos_2:
        if idx == 3:
            break
        video = result.unwrap()
        assert isinstance(video.title, str) and len(video.title) > 0
        idx += 1

    idx = 0
    async for result in videos_3:
        if idx == 3:
            break
        video = result.unwrap()
        assert isinstance(video.title, str) and len(video.title) > 0
        idx += 1
