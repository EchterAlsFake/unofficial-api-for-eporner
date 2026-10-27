import pytest
from base_api import DownloadConfigRAW

from ..api import Client, Encoding

@pytest.mark.asyncio
async def test_video():
    url = "https://www.eporner.com/video-2MWhVhhsAfM/zz-olenade/"
    video = await Client().get_video(url, load_html=True, load_api=True)
    assert isinstance(video.title, str) and len(video.title) > 0
    assert isinstance(video.video_id, str) and len(video.video_id) > 0
    assert isinstance(video.keywords, list) and len(video.keywords) > 0
    assert isinstance(video.views, int)
    assert isinstance(video.rate, str) and len(video.rate) > 0
    assert isinstance(video.publish_date, str) and len(video.publish_date) > 0
    assert isinstance(video.length_seconds, int) and video.length_seconds > 0
    assert isinstance(video.length_minutes, str) and len(video.length_minutes) > 0
    assert isinstance(video.embed_url, str) and len(video.embed_url) > 0
    assert isinstance(video.thumbnail, str) and len(video.thumbnail) > 0
    assert isinstance(video.content_url, str) and len(video.content_url) > 0
    assert isinstance(video.rating_value, str) and len(video.rating_value) > 0
    assert isinstance(video.rating_count, str) and len(video.rating_count) > 0

    async for author in video.get_authors():
        assert isinstance(author.name, str)

    config = DownloadConfigRAW(quality="worst", path="./")

    assert await video.download(config, mode=Encoding.mp4_h264) is True
