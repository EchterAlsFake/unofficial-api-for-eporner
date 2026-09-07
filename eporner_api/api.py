from __future__ import annotations

import re
import os
import copy
import json
import logging
import asyncio
import argparse

from dataclasses import dataclass
from urllib.parse import urljoin
from typing import AsyncGenerator, ClassVar, Any
from curl_cffi import AsyncSession
from selectolax.lexbor import LexborHTMLParser
from base_api.modules.config import IteratorConfig, RuntimeConfig
from base_api import (
    BaseCore,
    BaseMedia,
    DownloadConfigRAW,
    ErrorAction,
    ErrorMode,
    Helper,
    MediaLoadError,
    MediaLoadErrors,
    RetryPolicy,
    ScrapeErrorContext,
    ScrapeResult,
    media_field,
    is_resource_gone,
    default_on_error,
    scrape_stream,
    make_iterator_config as _base_make_iterator_config,
)
from base_api.modules.static_functions import normalize_quality_value, choose_quality_from_list, str_to_bool, get_text_safe
from base_api.modules.errors import (
    BotProtectionDetected,
    HTTPStatusError,
    InvalidProxy,
    NetworkRequestError,
    RequestRetriesExhausted,
    ResourceGone,
    UnknownError,
)

from eporner_api.modules.errors import (ProxyError, BotDetection, NotFound, NetworkError, UnknownNetworkError,
                                        DownloadFailed)

from eporner_api.modules.consts import (extractor, ROOT_URL, API_SEARCH,
                                        API_VIDEO_ID, headers, extractor_json)
from eporner_api.modules.locals import Encoding, Category
from eporner_api.modules.sorting import Order, LowQuality, Gay

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

SCRAPE_RETRY_POLICY = RetryPolicy(max_attempts=3)


def make_iterator_config(
    load_specific_sources: tuple[str, ...] = ("api", "html"),
    *,
    max_item_concurrency: int | None = None,
    max_page_concurrency: int | None = None,
    item_retry: RetryPolicy | None = None,
    page_retry: RetryPolicy | None = None,
    page_error_mode: ErrorMode = ErrorMode.SKIP,
    item_error_handler: Any = default_on_error,
    page_error_handler: Any = default_on_error,
    **kwargs,
) -> IteratorConfig:
    return _base_make_iterator_config(
        load_specific_sources=load_specific_sources,
        max_item_concurrency=max_item_concurrency,
        max_page_concurrency=max_page_concurrency,
        item_retry=item_retry,
        page_retry=page_retry,
        page_error_mode=page_error_mode,
        item_error_handler=item_error_handler,
        page_error_handler=page_error_handler,
        **kwargs,
    )


_is_resource_gone = is_resource_gone
on_error = default_on_error


async def get_html_content(core: BaseCore, url: str, get_json: bool = False) -> str | dict:
    try:
        content = await core.fetch_text(url)
        if get_json:
            return json.loads(content, strict=False)

        return content

    except HTTPStatusError as e:
        if e.status_code == 404:
            raise NotFound(f"Server returned 404 for: {url}") from e
        raise NetworkError(str(e)) from e

    except (NetworkRequestError, RequestRetriesExhausted) as e:
        raise NetworkError(str(e)) from e

    except InvalidProxy as e:
        raise ProxyError(str(e)) from e

    except BotProtectionDetected as e:
        raise BotDetection(str(e)) from e

    except UnknownError as e:
        raise UnknownNetworkError(str(e)) from e


@dataclass(slots=True, kw_only=True)
class Video(BaseMedia):
    url: str
    core: BaseCore
    video_id: str | None = None
    keywords: list | None = media_field("api")
    title: str | None = media_field("api")
    views: int | None = media_field("api")
    rate: str | None = media_field("api")
    publish_date: str | None = media_field("api")
    length_seconds: str | None = media_field("api")
    length_minutes: str | None = media_field("api")
    embed_url: str | None = media_field("api")
    thumbnail: str | None = media_field("api")
    rating_value: str | None = media_field("html")
    rating_count: str | None = media_field("html")
    parsed_urls: dict | None = media_field("html")
    description: str | None = media_field("html")
    encoding_format: str | None = media_field("html")
    is_family_friendly: str | None = media_field("html")
    thumbnails: list[str] | None = media_field("api")
    content_url: str | None = media_field("html")
    best_rating: str | None = media_field("html")
    worst_rating: str | None = media_field("html")
    authors_urls: list[str] | None = media_field("html")
    tags: list[str] | None = media_field("html")
    categories: list[str] | None = media_field("html")
    uploader: str | None = media_field("html")

    loader_methods: ClassVar[dict[str, str]] = {
        "api": "_load_api",
        "html": "_load_html",
    }

    def __post_init__(self) -> None:
        if self.video_id is not None:
            return

        match = re.search(r"video-([^/]+)", self.url)
        if match:
            self.video_id = match.group(1)

        match = re.search(r"hd-porn/(.*?)/", self.url)
        if match:
            self.video_id = match.group(1)

    async def _load_api(self) -> dict[str, object]:
        url = f"https://eporner.com/api/v2/video/id/?id={self.video_id}&thumbsize=medium&format=json"
        json_content = await get_html_content(core=self.core, url=url)
        assert isinstance(json_content, str)
        return await asyncio.to_thread(self._extract_api, json_content)

    async def _load_html(self) -> dict[str, object]:
        html_content = await get_html_content(core=self.core, url=self.url)
        assert isinstance(html_content, str)
        return await asyncio.to_thread(self._extract_html, html_content)

    @staticmethod
    def _extract_api(json_content: str) -> dict:
        json_data = json.loads(json_content, strict=False)
        
        if isinstance(json_data, list):
            if not json_data:
                raise ResourceGone("Video not found via API")
            json_data = json_data[0]

        title = json_data.get("title", "")
        keywords = json_data.get("keywords", "").split(",")
        views = json_data.get("views", None)
        rate = json_data.get("rate", "")
        publish_date = json_data.get("added", "")
        length_seconds = json_data.get("length_sec", "")
        length_minutes = json_data.get("length_min", "")
        embed_url = json_data.get("embed", "")
        thumbnail = json_data.get("default_thumb", {}).get("src", "")
        thumbnails = json_data.get("thumbs", [])

        return {
            "title": title,
            "keywords": keywords,
            "views": views,
            "rate": rate,
            "publish_date": publish_date,
            "length_seconds": length_seconds,
            "length_minutes": length_minutes,
            "embed_url": embed_url,
            "thumbnail": thumbnail,
            "thumbnails": thumbnails
        }

    @staticmethod
    def _extract_html(html_content: str) -> dict:
        lexbor = LexborHTMLParser(html_content)

        script = lexbor.css_first("script[type='application/ld+json']")
        json_html = json.loads(script.text(), strict=False)

        encoding_format = json_html.get("encodingFormat", "")
        is_family_friendly = json_html.get("isFamilyFriendly", "")
        description = json_html.get("description", "")
        rating_value = json_html.get("aggregateRating", {}).get("ratingValue", "")
        rating_count = json_html.get("aggregateRating", {}).get("ratingCount", "")
        best_rating = json_html.get("aggregateRating", {}).get("bestRating", "")
        worst_rating = json_html.get("aggregateRating", {}).get("worstRating", "")
        content_url = json_html.get("contentUrl", "")
        uploader = get_text_safe(lexbor.css_first("li.vit-uploader"))

        categories = [category.text(strip=True) for category in lexbor.css("li.vit-category")]
        tags = [tag.text(strip=True) for tag in lexbor.css("li.vit-tag")]

        authors_urls = []
        actors = json_html.get("actor", {})
        for actor in actors:
            authors_urls.append(actor.get("url"))

        # Temporary storage to hold raw integer qualities and their corresponding URLs
        raw_data = {}

        # 1. Parse AV1 URLs
        for node in lexbor.css('span.download-av1 a'):
            href = node.attributes.get('href')
            if href:
                # Extract the resolution number (e.g., '240' from '240p' or '/240/')
                match = re.search(r'(\d+)p', href)
                if match:
                    quality = int(match.group(1))
                    if quality not in raw_data:
                        raw_data[quality] = {}
                    raw_data[quality]['av1'] = f"https://www.eporner.com{href}"

        # 2. Parse H.264 URLs
        for node in lexbor.css('span.download-h264 a'):
            href = node.attributes.get('href')
            if href:
                match = re.search(r'(\d+)p', href)
                if match:
                    quality = int(match.group(1))
                    if quality not in raw_data:
                        raw_data[quality] = {}
                    raw_data[quality]['h264'] = f"https://www.eporner.com{href}"

        # 3. Sort by quality (worst to best / ascending order) and build the final dict
        sorted_qualities = sorted(raw_data.keys())

        parsed_urls = {}
        for q in sorted_qualities:
            parsed_urls[f"{q}p"] = {
                "av1": raw_data[q].get("av1"),
                "h264": raw_data[q].get("h264")
            }

        return {
            "encoding_format": encoding_format,
            "is_family_friendly": is_family_friendly,
            "description": description,
            "rating_value": rating_value,
            "best_rating": best_rating,
            "worst_rating": worst_rating,
            "rating_count": rating_count,
            "content_url": content_url,
            "parsed_urls": parsed_urls,
            "authors_urls": authors_urls,
            "categories": categories,
            "tags": tags,
            "uploader": uploader
        }

    def video_qualities(self) -> list[str]:
        # I assume here that the available qualities aren't different per mdoe (hopefully)
        return [k for k, v in self.parsed_urls.items()]

    def get_url_by_quality(self, quality: str | int, mode: Encoding | str) -> str:
        available_qualities = self.video_qualities()
        qn = normalize_quality_value(quality)
        quality_to_choose = choose_quality_from_list(available=available_qualities, target=qn)

        for stuff, key in self.parsed_urls.items():
            stuff = stuff.lower().strip("p")
            if str(quality_to_choose) == stuff:
                return key.get(mode)

        raise ValueError("Couldn't find a URL to match, please report this!")

    async def download(self, configuration: DownloadConfigRAW, mode: Encoding | str, use_workaround: bool = True):
        await self.load_fields("parsed_urls", "title")
        config = copy.deepcopy(configuration)
        quality = config.quality
        url = self.get_url_by_quality(quality=quality, mode=mode)

        if not config.no_title:
            config.path = os.path.join(config.path, f"{self.title}.mp4")

        try:
            await self.core.legacy_download(url=url, configuration=config)
            return True

        except Exception as e:
            raise DownloadFailed(str(e))

    async def get_authors(self, load_html: bool = True) -> AsyncGenerator[Pornstar, None]:
        actors = await self.get_field("authors_urls")
        for url in actors:
            star = Pornstar(url=url, core=self.core)
            if load_html:
                await star.load_sources("html")
            yield star


@dataclass(kw_only=True, slots=True)
class Pornstar(BaseMedia):
    url: str
    core: BaseCore
    subscribers: str | None = media_field("html")
    picture: str | None = media_field("html")
    name: str | None = media_field("html")
    photos_amount: str | None = media_field("html")
    video_amount: str | None = media_field("html")
    pornstar_rank: str | None = media_field("html")
    profile_views: str | None = media_field("html")
    video_views: str | None = media_field("html")
    photo_views: str | None = media_field("html")
    country: str | None = media_field("html")
    age: str | None = media_field("html")
    ethnicity: str | None = media_field("html")
    eye_color: str | None = media_field("html")
    hair_color: str | None = media_field("html")
    height: str | None = media_field("html")
    weight: str | None = media_field("html")
    cup: str | None = media_field("html")
    measurements: str | None = media_field("html")
    biography: str | None = media_field("html")
    aliases: list | None = media_field("html")

    loader_methods: ClassVar[dict[str, str]] = {"html": "_load_html"}

    async def _load_html(self) -> dict[str, object]:
        html_content = await get_html_content(url=self.url, core=self.core)
        assert isinstance(html_content, str)
        return await asyncio.to_thread(self._extract_html, html_content)

    @staticmethod
    def _extract_html(html_content: str) -> dict:
        lexbor = LexborHTMLParser(html_content)

        name = lexbor.css_first("h1").text(strip=True)
        subscribers = lexbor.css_first("div#resppssubcnt").text(strip=True)
        picture = lexbor.css_first("div.psImgOuter").css_first("img").attributes.get("src")
        photos_amount = lexbor.css_first("div.ps1a").css_first("a").css_first("span").text(strip=True)
        video_amount = lexbor.css_first("div.ps1a").css("a")[1].css_first("span").text(strip=True)
        pornstar_rank = lexbor.css_first("div.psbio.ps3").css_first("div").css_first("span").text(strip=True)
        profile_views = lexbor.css_first("div.psbio.ps3 > div:nth-child(2) > span").text(strip=True)
        video_views = lexbor.css_first("div.psbio.ps3").css("div")[2].css_first("span").text(strip=True)
        photo_views = lexbor.css_first("div.psbio.ps3").css("div")[3].css_first("span").text(strip=True)
        country = lexbor.css_first("div.psbio.ps2").css_first("div.cllnumber").text(strip=True)
        age = lexbor.css_first("div.psbio.ps2").css("div.cllnumber")[1].text(strip=True)
        ethnicity = lexbor.css_first("div.psbio.ps2").css("div.cllnumber")[2].text(strip=True)
        try: eye_color = lexbor.css_first("div.psbio.ps2").css("div.cllnumber")[3].text(strip=True)
        except (AttributeError, IndexError): eye_color = None

        try: hair_color = lexbor.css_first("div.psbio.ps2").css("div.cllnumber")[4].text(strip=True)
        except (AttributeError, IndexError): hair_color = None

        try: height = lexbor.css_first("div.psbio.ps2").css("div.cllnumber")[5].text(strip=True)
        except(AttributeError, IndexError): height = None

        try: weight = lexbor.css_first("div.psbio.ps2").css("div.cllnumber")[6].text(strip=True)
        except(AttributeError, IndexError): weight = None
        try: cup = lexbor.css_first("div.psbio.ps2").css("div.cllnumber")[7].text(strip=True)
        except (AttributeError, IndexError): cup = None

        try: measurements = lexbor.css_first("div.psbio.ps2").css("div.cllnumber")[8].text(strip=True)
        except (AttributeError, IndexError): measurements = None

        try: biography = lexbor.css_first("div.psscrol > p").text(strip=True)
        except AttributeError: biography = None

        try:
            stuff = lexbor.css_first("div.psbio.ps4")
            aliases = [tag.text(strip=True) for tag in stuff.css("li")]
        except AttributeError:
            aliases = []

        return {
            "name": name,
            "subscribers": subscribers,
            "picture": picture,
            "photos_amount": photos_amount,
            "video_amount": video_amount,
            "pornstar_rank": pornstar_rank,
            "profile_views": profile_views,
            "video_views": video_views,
            "photo_views": photo_views,
            "country": country,
            "age": age,
            "ethnicity": ethnicity,
            "eye_color": eye_color,
            "hair_color": hair_color,
            "height": height,
            "weight": weight,
            "cup": cup,
            "measurements": measurements,
            "biography": biography,
            "aliases": aliases,
        }

    async def videos(
        self,
        pages: int = 0,
        iterator_config: IteratorConfig | None = None,
    ) -> AsyncGenerator[ScrapeResult[Video], None]:
        if pages == 0:
            video_amount = str(await self.get_field("video_amount")).replace(",", "")
            pages = round(int(video_amount)) / 37 # One page contains 37 videos

        helper = Helper(core=self.core, constructor=Video)
        pages = round(pages) # Dont ask
        url = self.url
        page_urls = [urljoin(f"{url}/", str(page)) for page in range(1, pages + 1)]

        if iterator_config is None:
            iterator_config = make_iterator_config()

        stream = helper.iterator(
            target_page_urls=page_urls,
            item_extractor=extractor,
            iterator_config=iterator_config,
        )
        async with stream:
            async for scrape_result in stream:
                yield scrape_result


class Client:
    def __init__(self, core: BaseCore | None = None):
        if core is None:
            core = BaseCore(RuntimeConfig())
        self.core = core
        self.core.initialize_session()
        assert isinstance(self.core.session, AsyncSession)
        self.core.session.headers.update(headers)

    async def get_video(self, url: str, load_html: bool = False, load_api: bool = True) -> Video:
        """Returns the Video object for a given URL"""
        logger.info(f"Returning video object for: {url} HTML Scraping -> {load_html}")
        video = Video(url=url, core=self.core)
        load_sources = tuple(
            source
            for source, enabled in (("api", load_api), ("html", load_html))
            if enabled
        )
        await video.load_sources(*load_sources)
        return video

    def search_videos(
        self,
        query: str,
        sorting_gay: str | Gay,
        sorting_order: str | Order,
        sorting_low_quality: str | LowQuality,
        per_page: int,
        pages: int = 2,
        iterator_config: IteratorConfig | None = None,
    ) -> AsyncGenerator[ScrapeResult[Video], None]:
        page_urls = [f"{ROOT_URL}{API_SEARCH}?query={query}&per_page={per_page}&%page={page}&thumbsize=medium&order={sorting_order}&gay={sorting_gay}&lq={sorting_low_quality}&format=json" for page in range(pages)]

        if iterator_config is None:
            iterator_config = make_iterator_config()

        return scrape_stream(
            core=self.core,
            constructor=Video,
            target_page_urls=page_urls,
            item_extractor=extractor_json,
            iterator_config=iterator_config,
        )


    def get_videos_by_category(
        self,
        category: str | Category,
        iterator_config: IteratorConfig | None = None,
    ) -> AsyncGenerator[ScrapeResult[Video], None]:
        page_urls = [f"{ROOT_URL}cat/{category}/{page}" for page in range(1, 100)]

        if iterator_config is None:
            iterator_config = make_iterator_config()

        return scrape_stream(
            core=self.core,
            constructor=Video,
            target_page_urls=page_urls,
            item_extractor=extractor,
            iterator_config=iterator_config,
        )


    async def get_pornstar(self, url: str, load_html: bool = True) -> Pornstar:
        logger.info(f"Returning Pornstar object for: {url} HTML Scraping -> {load_html}")
        pornstar = Pornstar(url=url, core=self.core)
        if load_html:
            await pornstar.load_sources("html")
        return pornstar


def create_parser(formatter_class=None) -> argparse.ArgumentParser:
    kwargs = {}
    if formatter_class:
        kwargs["formatter_class"] = formatter_class
    parser = argparse.ArgumentParser(
        description="EPorner API Command Line Interface",
        **kwargs
    )
    parser.add_argument("--download", metavar="URL", type=str, help="URL to download from")
    parser.add_argument("--quality", metavar="best|half|worst", type=str, default="best",
                        help="The video quality (best, half, worst)")
    parser.add_argument("--file", metavar="FILE", type=str,
                        help="(Optional) Specify a file with URLs (separated with new lines)")
    parser.add_argument("--output", metavar="DIR", type=str, help="The output path (with filename or directory)",
                        required=True)
    parser.add_argument("--no-title", metavar="True,False", type=str, nargs="?", const="True", default="False",
                        help="Whether to apply video title automatically to output path or not")
    return parser


async def run_main(args_list: list[str] | None = None):
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich_argparse import RichHelpFormatter
        console = Console()
        console.print(Panel.fit("[bold magenta]EPorner API CLI[/bold magenta]", border_style="cyan"))
        formatter_class = RichHelpFormatter
    except ImportError:
        console = None
        formatter_class = None

    parser = create_parser(formatter_class=formatter_class)
    args = parser.parse_args(args_list)
    no_title = str_to_bool(args.no_title) if isinstance(args.no_title, str) else bool(args.no_title)
    config = DownloadConfigRAW(quality=args.quality, path=args.output, no_title=no_title)

    urls: list[str] = []
    if args.download:
        urls.append(args.download)
    if args.file:
        with open(args.file, "r") as file:
            urls.extend([line.strip() for line in file.readlines() if line.strip()])

    if not urls:
        parser.print_help()
        return

    client = Client()
    for url in urls:
        if console:
            console.print(f"[cyan]Fetching video information for:[/cyan] [yellow]{url}[/yellow]")
        else:
            print(f"Fetching video information for: {url}")
        try:
            video = await client.get_video(url, load_html=True)
            title = getattr(video, "title", None) or url
            if console:
                console.print(f"[green]Starting download for:[/green] [bold]{title}[/bold]")
            else:
                print(f"Starting download for: {title}")
            await video.download(config, mode=Encoding.mp4_h264)
            if console:
                console.print(f"[bold green]Download complete: {title}![/bold green]")
            else:
                print(f"Download complete: {title}")
        except Exception as e:
            if console:
                console.print(f"[bold red]Error downloading {url}:[/bold red] {e}")
            else:
                print(f"Error downloading {url}: {e}")


def main():
    try:
        asyncio.run(run_main())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")


if __name__ == "__main__":
    main()

