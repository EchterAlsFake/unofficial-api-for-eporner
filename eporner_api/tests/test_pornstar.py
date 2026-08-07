import pytest
from ..api import Client
from base_api import BaseCore

@pytest.mark.asyncio
async def test_pornstar():
    url = "https://www.eporner.com/pornstar/riley-reid/"
    core = BaseCore()
    core.configuration.pages_concurrency = 1
    core.configuration.videos_concurrency = 1
    client = Client(core)
    pornstar = await client.get_pornstar(url, load_html=True)

    videos = pornstar.videos(pages=1)
    
    idx = 0
    async for result in videos:
        video = result.unwrap()
        assert isinstance(video.title, str) and len(video.title) > 3
        idx += 1
        if idx == 5:
            break


    assert isinstance(pornstar.pornstar_rank, str) and len(pornstar.pornstar_rank) >= 1
    assert isinstance(pornstar.aliases, list) and len(pornstar.aliases) > 1
    assert isinstance(pornstar.biography, str) and len(pornstar.biography) > 10
    assert isinstance(pornstar.age, str) and len(pornstar.age) >= 2
    assert isinstance(pornstar.cup, str) and len(pornstar.cup) >= 1
    assert isinstance(pornstar.country, str) and len(pornstar.country) >= 2
    assert isinstance(pornstar.weight, str) and len(pornstar.weight) >= 2
    assert isinstance(pornstar.name, str) and len(pornstar.name) >= 2
    assert isinstance(pornstar.eye_color, str) and len(pornstar.eye_color) >= 2
    assert isinstance(pornstar.measurements, str) and len(pornstar.measurements) >= 2
    assert isinstance(pornstar.profile_views, str) and len(pornstar.profile_views) >= 2
    assert isinstance(pornstar.video_views, str) and len(pornstar.video_views) >= 2
    assert isinstance(pornstar.photo_views, str) and len(pornstar.photo_views) >= 2
    assert isinstance(pornstar.subscribers, str) and len(pornstar.subscribers) >= 2
    assert isinstance(pornstar.photos_amount, str) and len(pornstar.photos_amount) >= 2
    assert isinstance(pornstar.video_amount, str) and len(pornstar.video_amount) >= 2
    assert isinstance(pornstar.picture, str) and len(pornstar.picture) >= 2
