import pytest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from eporner_api import api


def test_search_distinct_pages_and_escaped_query():
    client = object.__new__(api.Client)
    client.core = object()
    with patch.object(api, "scrape_stream") as stream:
        client.search_videos("a&b/# 日本", pages=2)
    urls = stream.call_args.kwargs["target_page_urls"]
    queries = [parse_qs(urlsplit(url).query) for url in urls]
    assert [q["page"] for q in queries] == [["1"], ["2"]]
    assert all(q["query"] == ["a&b/# 日本"] for q in queries)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sorting_order": "invalid"},
        {"per_page": 0},
        {"pages": 0},
        {"sorting_gay": "latest"},
    ],
)
def test_search_rejects_invalid_options(kwargs):
    client = object.__new__(api.Client)
    client.core = object()
    with pytest.raises(ValueError):
        client.search_videos("test", **kwargs)


@pytest.mark.parametrize(
    "quality,expected", [("best", "1080"), ("worst", "480"), (720, "480")]
)
def test_quality_selects_available_encoding(quality, expected):
    video = api.Video(
        url="https://www.eporner.com/video-AbC123/",
        core=object(),
        parsed_urls={
            "480p": {"h264": "480"},
            "720p": {"av1": "720"},
            "1080p": {"h264": "1080"},
        },
    )
    assert video.get_url_by_quality(quality, api.Encoding.mp4_h264) == expected


def test_absolute_download_url():
    html = '<script type="application/ld+json">{"@type":"VideoObject","name":"Test"}</script><span class="download-h264"><a href="https://cdn.example/720p.mp4">720p</a></span>'
    assert (
        api.Video._extract_html(html)["parsed_urls"]["720p"]["h264"]
        == "https://cdn.example/720p.mp4"
    )


@pytest.mark.parametrize(
    "metadata",
    [
        '[{"@type":"VideoObject","name":"Test"}]',
        '{"@graph":[{"@type":"VideoObject","name":"Test"}]}',
        '{"@type":["VideoObject"],"name":"Test"}',
    ],
)
def test_structured_metadata_shapes(metadata):
    html = (
        '<script type="application/ld+json">invalid</script><script type="application/ld+json">'
        + metadata
        + "</script>"
    )
    assert api.Video._extract_html(html)["title"] == "Test"


def test_api_listing_metadata_types():
    from eporner_api.modules.consts import extractor_json
    import json

    row = extractor_json(
        json.dumps(
            {
                "videos": [
                    {
                        "id": "AbC123",
                        "url": "https://www.eporner.com/video-AbC123/",
                        "keywords": "one, two",
                        "embed": "https://www.eporner.com/embed/AbC123/",
                        "default_thumb": None,
                        "thumbs": [{"src": "https://cdn.example/1.jpg"}],
                    }
                ]
            }
        )
    )[0]
    assert row["video_id"] == "AbC123"
    assert row["keywords"] == ["one", "two"]
    assert row["thumbnails"] == ["https://cdn.example/1.jpg"]
    assert row["embed_url"].endswith("/AbC123/")


@pytest.mark.asyncio
async def test_cli_closes_session_and_reports_false_download(capsys, tmp_path):
    from unittest.mock import AsyncMock, MagicMock
    from base_api import BaseCore
    from base_api.modules.config import RuntimeConfig

    core = BaseCore(RuntimeConfig())
    video = MagicMock(title="Example", length="10", url="https://example.com/video")
    video.load_fields = AsyncMock()
    video.download = AsyncMock(return_value=False)
    client = MagicMock()
    client.get_video = AsyncMock(return_value=video)
    with (
        patch.object(api, "BaseCore", return_value=core),
        patch.object(api, "Client", return_value=client),
    ):
        await api.run_main(
            ["--download", "https://example.com/video", "--output", str(tmp_path)]
        )
    assert core.session is None
    output = capsys.readouterr().out
    assert "Download complete:" not in output
    assert "Done ->" not in output
    assert "Download did not complete" in output


@pytest.mark.parametrize(
    "path",
    [
        "/video-AbC123/slug/",
        "/hd-porn/AbC123/slug/",
        "/embed/AbC123/",
        "/porno-video/AbC123/",
    ],
)
def test_regional_video_identity(path):
    video = api.Video(
        url="https://de.eporner.com" + path + "?share=1#video", core=object()
    )
    assert video.video_id == "AbC123"
    assert urlsplit(video.url).hostname == "de.eporner.com"


def test_deleted_api_video():
    from base_api.modules.errors import ResourceGone

    video = api.Video(url="https://www.eporner.com/video-AbC123/", core=object())
    with pytest.raises(ResourceGone):
        video._extract_api("[]")


@pytest.mark.asyncio
async def test_channel_soft_404_is_not_success():
    from unittest.mock import AsyncMock

    channel = api.Channel(url="https://www.eporner.com/channel/missing/", core=object())
    with patch.object(
        api,
        "get_html_content",
        AsyncMock(
            return_value='<div id="error">Channel do not exists or is pending verification.</div>'
        ),
    ):
        with pytest.raises(api.NotFound):
            await channel._load_html()


@pytest.mark.asyncio
async def test_authors_retain_native_identity_without_loading():
    video = api.Video(
        url="https://www.eporner.com/video-AbC123/",
        core=object(),
        authors_urls=["https://www.eporner.com/pornstar/example/"],
    )
    authors = [a async for a in video.get_authors(load_html=False)]
    assert len(authors) == 1
    assert isinstance(authors[0], api.Pornstar)
    assert authors[0].url.endswith("/example/")


def test_null_optional_api_thumbnails():
    video = api.Video(url="https://www.eporner.com/video-AbC123/", core=object())
    data = video._extract_api('{"title":"Example","default_thumb":null,"thumbs":null}')
    assert data["thumbnail"] is None
    assert data["thumbnails"] == []

@pytest.mark.parametrize('labels', [
    ['Rang','Profilansichten','Videos','Fotoansichten','Abonnenten'],
    ['Rang','Vues du profil','Vues vidéo','Vues photo','Abonnés'],
])
def test_localized_pornstar_statistics(labels):
    html='<div class="psbio ps3">'+''.join('<div>'+label+':<span>'+str(i)+'</span></div>' for i,label in enumerate(labels,1))+'</div>'
    data=api.Pornstar._extract_html(html)
    assert [data[k] for k in ['pornstar_rank','profile_views','video_views','photo_views','subscribers']] == ['1','2','3','4','5']

@pytest.mark.parametrize('labels', [['Abonnenten','Videos','Ansichten','Rang'],['Abonnés','Vidéos','Des vues','Rang']])
def test_localized_channel_statistics(labels):
    html='<div id="pprofiletopbtn">'+''.join('<div><span>'+str(i)+'</span>'+label+'</div>' for i,label in enumerate(labels,1))+'</div>'
    data=api.Channel._extract_html(html)
    assert [data[k] for k in ['subscribers','video_amount','video_views','channel_rank']] == ['1','2','3','4']
