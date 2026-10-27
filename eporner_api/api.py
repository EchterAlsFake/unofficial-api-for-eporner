from __future__ import annotations

import re
from functools import partial
import json
import logging
import asyncio
import argparse

from eporner_api.modules import errors as provider_errors
from base_api import append_url_path, profile_base_url, replace_url_path
from urllib.parse import urlsplit, urlencode
from base_api.modules.provider import fetch_content, download_errors, prepare_download_config
from base_api.modules.logger import configure_app_logging, get_logger

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
from base_api.modules.errors import ResourceGone

from eporner_api.modules.errors import (ProxyError, BotDetection, NotFound, NetworkError, UnknownNetworkError,
                                        DownloadFailed)

from eporner_api.modules.consts import (extractor, ROOT_URL, API_SEARCH,
                                        API_VIDEO_ID, headers, extractor_json)
from eporner_api.modules.locals import Encoding, Category
from eporner_api.modules.sorting import Order, LowQuality, Gay

logger = get_logger(__name__)

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


async def get_html_content(core: BaseCore, url: str, get_json: bool = False, *, owner=None) -> str | dict:
    return await fetch_content(core, url, logger=logger, owner=owner,
                               error_types=provider_errors, get_json=get_json)

@dataclass(slots=True, kw_only=True)
class Video(BaseMedia):
    url: str
    core: BaseCore
    video_id: str | None = None

    keywords: list[str] | None = media_field("api")
    title: str | None = media_field("api", "html")
    views: int | None = media_field("api", "html")
    rate: str | None = media_field("api")
    publish_date: str | None = media_field("api")
    length_seconds: int | None = media_field("api")
    length_minutes: str | None = media_field("api")
    embed_url: str | None = media_field("api", "html")
    thumbnail: str | None = media_field("api", "html")
    thumbnails: list[str] | None = media_field("api", "html")

    rating_value: str | None = media_field("html")
    rating_count: str | None = media_field("html")
    parsed_urls: dict | None = media_field("html")
    description: str | None = media_field("html")
    encoding_format: str | None = media_field("html")
    is_family_friendly: str | None = media_field("html")
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

        path = urlsplit(self.url).path
        match = re.match(r"/(?:video-|hd-porn/|embed/|porno-video/)([A-Za-z0-9]+)(?:/|$)", path)
        if match:
            self.video_id = match.group(1)
        if path.startswith(("/embed/", "/porno-video/")) and self.video_id:
            self.url = replace_url_path(self.url, f"/video-{self.video_id}/")

    async def _load_api(self) -> dict[str, object]:
        url = (
            "https://eporner.com/api/v2/video/id/"
            f"?id={self.video_id}&thumbsize=medium&format=json"
        )
        json_content = await get_html_content(core=self.core, url=url, owner=self)
        assert isinstance(json_content, str)
        return await asyncio.to_thread(self._extract_api, json_content)

    async def _load_html(self) -> dict[str, object]:
        html_content = await get_html_content(core=self.core, url=self.url, owner=self)
        assert isinstance(html_content, str)
        return await asyncio.to_thread(self._extract_html, html_content)

    def _extract_api(self, json_content: str) -> dict[str, object]:
        json_data = json.loads(json_content, strict=False)

        if isinstance(json_data, list):
            if not json_data:
                raise ResourceGone(f"Video not found via API: {self.url}")
            json_data = json_data[0]

        keywords = json_data.get("keywords")

        return {
            "title": json_data.get("title"),
            "keywords": (
                [keyword.strip() for keyword in keywords.split(",")]
                if keywords else []
            ),
            "views": json_data.get("views"),
            "rate": json_data.get("rate"),
            "publish_date": json_data.get("added"),
            "length_seconds": json_data.get("length_sec"),
            "length_minutes": json_data.get("length_min"),
            "embed_url": json_data.get("embed"),
            "thumbnail": (json_data.get("default_thumb") or {}).get("src"),
            "thumbnails": [
                thumb["src"]
                for thumb in (json_data.get("thumbs") or [])
                if thumb.get("src")
            ],
        }

    @staticmethod
    def _extract_html(html_content: str) -> dict[str, object]:
        lexbor = LexborHTMLParser(html_content)

        if (
            lexbor.css_first("#deletedfile") is not None
            or lexbor.css_first(".hdpnotfound") is not None
        ):
            raise ResourceGone("Video is no longer available")

        json_html = None

        for script in lexbor.css("script[type='application/ld+json']"):
            try:
                data = json.loads(script.text(), strict=False)
            except (ValueError, TypeError):
                continue
            candidates = data if isinstance(data, list) else [data]
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                for candidate in [item, *item.get("@graph", [])]:
                    if isinstance(candidate, dict) and "VideoObject" in (
                        candidate.get("@type") if isinstance(candidate.get("@type"), list)
                        else [candidate.get("@type")]
                    ):
                        json_html = candidate
                        break
                if json_html is not None:
                    break
            if json_html is not None:
                break

        if json_html is None:
            raise ValueError("Video metadata was not found in the page")

        rating = json_html.get("aggregateRating") or {}

        categories = [
            node.text(strip=True)
            for node in lexbor.css("li.vit-category")
        ]
        tags = [
            node.text(strip=True)
            for node in lexbor.css("li.vit-tag")
        ]

        actors = json_html.get("actor") or []
        if isinstance(actors, dict):
            actors = [actors]
        authors_urls = [
            actor["url"]
            for actor in actors
            if isinstance(actor, dict) and actor.get("url")
        ]

        raw_data = {}

        for mode in ("av1", "h264"):
            for node in lexbor.css(f"span.download-{mode} a"):
                href = node.attributes.get("href")
                if not href:
                    continue

                match = re.search(r"(\d+)p", href)
                if not match:
                    continue

                quality = int(match.group(1))
                raw_data.setdefault(quality, {})[mode] = urljoin(ROOT_URL, href)

        parsed_urls = {
            f"{quality}p": {
                "av1": urls.get("av1"),
                "h264": urls.get("h264"),
            }
            for quality, urls in sorted(raw_data.items())
        }

        thumbnails = json_html.get("thumbnailUrl") or []
        if isinstance(thumbnails, str):
            thumbnails = [thumbnails]

        return {
            "title": json_html.get("name"),
            "views": json_html.get(
                "interactionStatistic", {}
            ).get("userInteractionCount"),
            "embed_url": json_html.get("embedUrl"),
            "thumbnail": json_html.get("image"),
            "thumbnails": thumbnails,
            "encoding_format": json_html.get("encodingFormat"),
            "is_family_friendly": json_html.get("isFamilyFriendly"),
            "description": json_html.get("description"),
            "rating_value": rating.get("ratingValue"),
            "rating_count": rating.get("ratingCount"),
            "best_rating": rating.get("bestRating"),
            "worst_rating": rating.get("worstRating"),
            "content_url": json_html.get("contentUrl"),
            "parsed_urls": parsed_urls,
            "authors_urls": authors_urls,
            "categories": categories,
            "tags": tags,
            "uploader": get_text_safe(
                lexbor.css_first("li.vit-uploader")
            ),
        }

    def video_qualities(self) -> list[str]:
        return list(self.parsed_urls)

    def get_url_by_quality(
        self,
        quality: str | int,
        mode: Encoding | str,
    ) -> str:
        if isinstance(mode, Encoding):
            mode = mode.value
        available = [quality for quality, urls in (self.parsed_urls or {}).items() if urls.get(mode)]
        if not available:
            raise ValueError(f"No download URLs for encoding={mode!r}: {self.url}")
        quality = choose_quality_from_list(
            available=available,
            target=normalize_quality_value(quality),
        )

        url = self.parsed_urls[f"{quality}p"].get(mode)
        if url:
            return url

        raise ValueError(
            f"No download URL for {self.url}: "
            f"quality={quality!r}, encoding={mode!r}, "
            f"available={available}"
        )

    @download_errors(DownloadFailed)
    async def download(
        self,
        configuration: DownloadConfigRAW,
        mode: Encoding | str,
    ):
        await self.load_fields("parsed_urls", "title")

        config = prepare_download_config(configuration, self.title)
        url = self.get_url_by_quality(
            quality=config.quality,
            mode=mode,
        )


        return await self.core.legacy_download(
            url=url,
            configuration=config,
        )

    async def get_authors(
        self,
        load_html: bool = True,
    ) -> AsyncGenerator[Pornstar, None]:
        actors = await self.get_field("authors_urls")

        for url in actors:
            star = Pornstar(url=url, core=self.core)

            if load_html:
                await star.load_sources("html")

            yield star


@dataclass(kw_only=True, slots=True)
class BaseProfile(BaseMedia):

    def __post_init__(self):
        profile_base_url(self.url, depth=2)

    core: BaseCore
    name: str | None = media_field("html")
    subscribers: str | None = media_field("html")
    video_amount: str | None = media_field("html")
    video_views: str | None = media_field("html")
    picture: str | None = media_field("html")
    websites: dict[str, str] | None = media_field("html")
    total_pages: int | None = media_field("html")

    loader_methods: ClassVar[dict[str, str]] = {"html": "_load_html"}

    async def _load_html(self) -> dict[str, object]:
        html_content = await get_html_content(url=self.url, core=self.core, owner=self)
        assert isinstance(html_content, str)
        data = await asyncio.to_thread(self._extract_html, html_content)
        error = LexborHTMLParser(html_content).css_first("#error")
        if error and error.text(strip=True):
            raise NotFound(error.text(strip=True))
        base_path = urlsplit(profile_base_url(self.resolved_url or self.url)).path
        parser = LexborHTMLParser(html_content)
        numbers = [int(match.group(1)) for node in parser.css("a[href]")
                   if (match := re.fullmatch(re.escape(base_path) + r"/(\d+)/?", urlsplit(node.attributes["href"]).path))]
        data["total_pages"] = max(numbers, default=1)
        return data

    @staticmethod
    def _extract_html(html_content: str) -> dict[str, object]:
        raise NotImplementedError

    async def videos(
        self,
        pages: int = 0,
        iterator_config: IteratorConfig | None = None,
    ) -> AsyncGenerator[ScrapeResult[Video], None]:
        if pages == 0:
            pages = await self.get_field("total_pages") or 1

        helper = Helper(core=self.core, constructor=Video)
        pages = round(pages)
        url = profile_base_url(self.resolved_url or self.url)
        page_urls = [append_url_path(url, page) for page in range(1, pages + 1)]

        if iterator_config is None:
            iterator_config = make_iterator_config()

        stream = helper.iterator(
            target_page_urls=page_urls,
            item_extractor=partial(extractor, base_url=url),
            iterator_config=iterator_config,
        )
        async with stream:
            async for scrape_result in stream:
                yield scrape_result


@dataclass(kw_only=True, slots=True)
class Pornstar(BaseProfile):
    pornstar_id: str | None = media_field("html")
    photos_amount: str | None = media_field("html")
    pornstar_rank: str | None = media_field("html")
    profile_views: str | None = media_field("html")
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
    aliases: list[str] | None = media_field("html")

    @staticmethod
    def _extract_html(html_content: str) -> dict[str, object]:
        lexbor = LexborHTMLParser(html_content)

        h1 = lexbor.css_first("h1")
        name = h1.text(strip=True) if h1 else None

        img = lexbor.css_first("div.psImgOuter img")
        picture = img.attributes.get("src") if img else None

        sub_btn = lexbor.css_first("div.subscribebutton")
        onclick = sub_btn.attributes.get("onclick", "") if sub_btn else ""
        match_id = re.search(r"EP\.subscribe\.sub\(this,\s*(\d+)", onclick)
        if not match_id:
            match_id = re.search(r"EP\.subscribe\.sub\(this,\s*(\d+)", html_content)
        pornstar_id = match_id.group(1) if match_id else None

        video_amount = None
        photos_amount = None
        for a in lexbor.css("div.ps1a a"):
            span = a.css_first("span")
            val = span.text(strip=True) if span else None
            text = a.text(strip=True).lower()
            href = a.attributes.get("href", "").lower()
            if "video" in text or ("#toptopbel" in href and "photo" not in href):
                video_amount = val
            elif "photo" in text or "photo" in href:
                photos_amount = val

        pornstar_rank = None
        profile_views = None
        video_views = None
        photo_views = None
        subscribers = None

        ps3 = lexbor.css_first("div.psbio.ps3")
        if ps3:
            for d in ps3.css("div"):
                text = d.text(strip=True).lower()
                span = d.css_first("span")
                val = span.text(strip=True) if span else None
                if any(label in text for label in ("rank:", "rang:")):
                    pornstar_rank = val
                elif any(label in text for label in ("profile views:", "profilansichten:", "vues du profil:")):
                    profile_views = val
                elif any(label in text for label in ("video views:", "videos:", "vues vidéo:")):
                    video_views = val
                elif any(label in text for label in ("photo views:", "fotoansichten:", "vues photo:")):
                    photo_views = val
                elif any(label in text for label in ("subscribers:", "abonnenten:", "abonnés:")):
                    subscribers = val

        if subscribers is None:
            sub_cnt = lexbor.css_first("div#resppssubcnt span")
            if sub_cnt:
                subscribers = sub_cnt.text(strip=True)
            elif sub_btn:
                small = sub_btn.css_first("small")
                if small:
                    subscribers = small.text(strip=True).strip("()")

        ps2_map = {}
        ps2 = lexbor.css_first("div.psbio.ps2")
        if ps2:
            for li in ps2.css("li"):
                label_node = li.css_first("span")
                val_node = li.css_first("div.cllnumber")
                if label_node and val_node:
                    ps2_map[label_node.text(strip=True).rstrip(":").lower()] = val_node.text(strip=True)

        aliases = {
            "land": "country", "pays": "country", "alter": "age", "âge": "age",
            "ethnische erscheinung": "ethnicity", "ethnicité": "ethnicity",
            "auge": "eye", "œil": "eye", "haare": "hair", "cheveux": "hair",
            "höhe": "height", "la taille": "height", "gewicht": "weight", "poids": "weight",
            "die tasse": "cup", "maße": "measurements", "des mesures": "measurements",
        }
        for label, canonical in aliases.items():
            if label in ps2_map:
                ps2_map.setdefault(canonical, ps2_map[label])

        country = ps2_map.get("country")
        age = ps2_map.get("age")
        ethnicity = ps2_map.get("ethnicity")
        eye_color = ps2_map.get("eye")
        hair_color = ps2_map.get("hair")
        height = ps2_map.get("height")
        weight = ps2_map.get("weight")
        cup = ps2_map.get("cup")
        measurements = ps2_map.get("measurements")

        ps4 = lexbor.css_first("div.psbio.ps4")
        aliases = [tag.text(strip=True) for tag in ps4.css("li")] if ps4 else []

        websites = {}
        ps5 = lexbor.css_first("div.psbio.ps5")
        if ps5:
            for a in ps5.css("a"):
                href = a.attributes.get("href")
                if href:
                    label = a.text(strip=True) or "Website"
                    websites[label] = href

        ps6 = lexbor.css_first("div.psbio.ps6")
        p_node = ps6.css_first("p") if ps6 else None
        biography = p_node.text(strip=True) if p_node else None

        return {
            "name": name,
            "pornstar_id": pornstar_id,
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
            "websites": websites,
        }


@dataclass(kw_only=True, slots=True)
class Channel(BaseProfile):
    channel_id: str | None = media_field("html")
    channel_rank: str | None = media_field("html")
    logo: str | None = media_field("html")
    banner: str | None = media_field("html")

    @staticmethod
    def _extract_html(html_content: str) -> dict[str, object]:
        lexbor = LexborHTMLParser(html_content)

        h1 = lexbor.css_first("div#pprofiletopinfo h1")
        if not h1:
            h1 = lexbor.css_first("h1")
        name = h1.text(strip=True) if h1 else None

        img = lexbor.css_first("img.chlogo")
        if not img:
            img = lexbor.css_first("div#pprofiletophead img")
        logo = img.attributes.get("src") if img else None
        picture = logo

        banner = None
        top = lexbor.css_first("div#pprofiletop")
        if top:
            style = top.attributes.get("style", "")
            match_banner = re.search(r"url\(['\"]?(.*?)['\"]?\)", style)
            if match_banner:
                banner = match_banner.group(1)

        sub_btn = lexbor.css_first("div.subscribebutton")
        onclick = sub_btn.attributes.get("onclick", "") if sub_btn else ""
        match_id = re.search(r"EP\.subscribe\.sub\(this,\s*(\d+)", onclick)
        if not match_id:
            match_id = re.search(r"EP\.subscribe\.sub\(this,\s*(\d+)", html_content)
        channel_id = match_id.group(1) if match_id else None

        subscribers = None
        video_amount = None
        video_views = None
        channel_rank = None

        topbtn = lexbor.css_first("div#pprofiletopbtn")
        if topbtn:
            for d in topbtn.css("div"):
                span = d.css_first("span")
                val = span.text(strip=True) if span else None
                text = d.text(strip=True).lower()
                if any(label in text for label in ("subscriber", "abonnenten", "abonnés")):
                    subscribers = val
                elif any(label in text for label in ("video", "vidéo")) and "view" not in text:
                    video_amount = val
                elif any(label in text for label in ("view", "ansichten", "vues")):
                    video_views = val
                elif "rank" in text or "rang" in text:
                    channel_rank = val

        if subscribers is None and sub_btn:
            span = sub_btn.css_first("span.sbview1")
            if span:
                subscribers = span.text(strip=True)
            else:
                small = sub_btn.css_first("small")
                if small:
                    subscribers = small.text(strip=True).strip("()")

        websites: dict[str, str] = {}
        for a in lexbor.css("div.channelsoc a"):
            href = a.attributes.get("href")
            if not href:
                continue
            label = a.text(strip=True)
            if not label:
                i_tag = a.css_first("i")
                if i_tag:
                    classes = i_tag.attributes.get("class", "").split()
                    for cls in classes:
                        if cls.startswith("fa-"):
                            label = cls.replace("fa-", "").replace("-square", "").capitalize()
                            break
            if not label:
                label = "Website"
            if label not in websites:
                websites[label] = href
            elif websites[label] != href:
                counter = 2
                while f"{label} {counter}" in websites:
                    counter += 1
                websites[f"{label} {counter}"] = href

        return {
            "name": name,
            "channel_id": channel_id,
            "subscribers": subscribers,
            "picture": picture,
            "logo": logo,
            "banner": banner,
            "video_amount": video_amount,
            "video_views": video_views,
            "channel_rank": channel_rank,
            "websites": websites,
        }


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
        sorting_gay: str | Gay = Gay.include_gay_content,
        sorting_order: str | Order = Order.latest,
        sorting_low_quality: str | LowQuality = LowQuality.include_low_quality_content,
        per_page: int = 30,
        pages: int = 2,
        iterator_config: IteratorConfig | None = None,
    ) -> AsyncGenerator[ScrapeResult[Video], None]:
        sorting_gay = Gay(sorting_gay)
        sorting_order = Order(sorting_order)
        sorting_low_quality = LowQuality(sorting_low_quality)
        if not 1 <= per_page <= 1000:
            raise ValueError("per_page must be between 1 and 1000")
        if pages < 1:
            raise ValueError("pages must be positive")
        page_urls = [f"{ROOT_URL}{API_SEARCH}?" + urlencode({
            "query": query, "per_page": per_page, "page": page, "thumbsize": "medium",
            "order": sorting_order, "gay": sorting_gay, "lq": sorting_low_quality, "format": "json",
        }) for page in range(1, pages + 1)]

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

    async def get_channel(self, url: str, load_html: bool = True) -> Channel:
        logger.info(f"Returning Channel object for: {url} HTML Scraping -> {load_html}")
        channel = Channel(url=url, core=self.core)
        if load_html:
            await channel.load_sources("html")
        return channel


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

    async with BaseCore(RuntimeConfig()) as core:
        client = Client(core=core)
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
                result = await video.download(config, mode=Encoding.mp4_h264)
                if result is False or getattr(result, "status", None) == "failed":
                    raise DownloadFailed("Download did not complete")
                if console:
                    console.print(f"[bold green]Download complete: {title}![/bold green]")
                else:
                    print(f"Download complete: {title}")
            except Exception as e:
                logger.exception("CLI failed while processing %s", url)
                if console:
                    console.print(f"[bold red]Error downloading {url}:[/bold red] {e}")
                else:
                    print(f"Error downloading {url}: {e}")


def main():
    configure_app_logging(level=logging.INFO)
    try:
        asyncio.run(run_main())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")


if __name__ == "__main__":
    main()
