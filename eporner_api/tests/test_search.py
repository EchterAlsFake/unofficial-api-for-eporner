import pytest
from ..api import Client, Gay, Order, LowQuality


query = "Mia Khalifa"
pages = 2
per_page = 1

@pytest.fixture
def client():
    return Client()

@pytest.mark.asyncio
async def test_search_1(client):
    videos = client.search_videos(query, pages=pages, per_page=per_page, sorting_gay=Gay.exclude_gay_content, sorting_order=Order.top_rated, sorting_low_quality=LowQuality.exclude_low_quality_content)
    async for result in videos:
        assert len(result.unwrap().title) > 0

@pytest.mark.asyncio
async def test_search_2(client):
    videos = client.search_videos(query, pages=pages, per_page=per_page, sorting_gay=Gay.only_gay_content, sorting_order=Order.latest, sorting_low_quality=LowQuality.only_low_quality_content)
    async for result in videos:
        assert len(result.unwrap().title) > 0

@pytest.mark.asyncio
async def test_search_3(client):
    videos = client.search_videos(query, pages=pages, per_page=per_page, sorting_gay=Gay.include_gay_content, sorting_order=Order.longest, sorting_low_quality=LowQuality.include_low_quality_content)
    async for result in videos:
        assert len(result.unwrap().title) > 0

@pytest.mark.asyncio
async def test_search_4(client):
    videos = client.search_videos(query, pages=pages, per_page=pages, sorting_gay=Gay.exclude_gay_content, sorting_order=Order.shortest, sorting_low_quality=LowQuality.include_low_quality_content)
    async for result in videos:
        assert len(result.unwrap().title) > 0

@pytest.mark.asyncio
async def test_search_5(client):
    videos = client.search_videos(query, pages=pages, per_page=per_page, sorting_order=Gay.include_gay_content, sorting_gay=Order.top_weekly, sorting_low_quality=LowQuality.include_low_quality_content)
    async for result in videos:
        assert len(result.unwrap().title) > 0

@pytest.mark.asyncio
async def test_search_6(client):
    videos = client.search_videos(query, pages=pages, per_page=per_page, sorting_order=Order.most_popular, sorting_low_quality=LowQuality.include_low_quality_content, sorting_gay=Gay.only_gay_content)
    async for result in videos:
        assert len(result.unwrap().title) > 0

@pytest.mark.asyncio
async def test_search_7(client):
    videos = client.search_videos(query, pages=pages, per_page=per_page, sorting_gay=Gay.include_gay_content, sorting_order=Order.top_monthly, sorting_low_quality=LowQuality.include_low_quality_content)
    async for result in videos:
        assert len(result.unwrap().title) > 0
