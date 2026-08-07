import re
import json
from selectolax.lexbor import LexborHTMLParser

# ROOT URLs
ROOT_URL = "https://www.eporner.com/"
PORNSTAR = "https://www.eporner.com/pornstar/"

# API Calls
API_SEARCH = "api/v2/video/search/"
API_VIDEO_ID = "api/v2/video/id/"

headers = {
    "Referer": "https://www.eporner.com/"
}


def extractor(content: str) -> list[dict]:
    videos_data = []
    lexbor = LexborHTMLParser(content)
    # Target individual video block containers
    video_nodes = lexbor.css("div.mb")

    for node in video_nodes:
        video_id = node.attributes.get("data-id")

        # 1. URL and Title
        title_node = node.css_first("p.mbtit a")
        url = title_node.attributes.get("href") if title_node else None
        title = title_node.text(strip=True) if title_node else None
        if not isinstance(url, str) or not url:
            continue

        # 2. Thumbnail Processing (Handles lazy-loaded images safely)
        img_node = node.css_first("div.mbimg img")
        thumbnail = None
        if img_node:
            # Check data-src first (used on lazy-loaded items), fall back to standard src
            thumbnail = img_node.attributes.get("data-src") or img_node.attributes.get("src")

        thumbnails = [thumbnail] if thumbnail else []

        # 3. Stats & Duration Parsing
        length_minutes = None
        length_seconds = None
        rate = None
        views = None

        # Parse Duration strings (Format is usually MM:SS or HH:MM:SS)
        time_node = node.css_first("span.mbtim")
        if time_node:
            time_str = time_node.text(strip=True)
            time_parts = time_str.split(":")
            try:
                if len(time_parts) == 2:  # MM:SS
                    length_minutes = time_parts[0]
                    length_seconds = str(int(time_parts[0]) * 60 + int(time_parts[1]))
                elif len(time_parts) == 3:  # HH:MM:SS
                    length_minutes = str(int(time_parts[0]) * 60 + int(time_parts[1]))
                    length_seconds = str(int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + int(time_parts[2]))
            except ValueError:
                pass  # Keep as None if parsing fails due to bad strings

        # Rating (e.g., "85%")
        rate_node = node.css_first("span.mbrate")
        if rate_node:
            rate = rate_node.text(strip=True)

        # Views count conversion (Strips localized commas)
        views_node = node.css_first("span.mbvie")
        if views_node:
            views_str = views_node.text(strip=True).replace(",", "")
            try:
                views = int(views_str)
            except ValueError:
                pass

        # 4. Author/Uploader Profile Link
        authors_urls = None
        uploader_node = node.css_first("span.mb-uploader a")
        if uploader_node:
            author_href = uploader_node.attributes.get("href")
            if author_href:
                authors_urls = [author_href]

        # Unknown author data stays omitted so BaseMedia can load it from HTML.
        video_data = {
            "url": url,
            "video_id": video_id,
            "title": title,
            "views": views,
            "rate": rate,
            "length_seconds": length_seconds,
            "length_minutes": length_minutes,
            "thumbnail": thumbnail,
            "thumbnails": thumbnails,
        }
        if authors_urls is not None:
            video_data["authors_urls"] = authors_urls
        videos_data.append(video_data)

    return videos_data


def extractor_json(content: str) -> list[dict]:
    videos = []
    stuff = json.loads(content)

    for video in stuff.get("videos", []):  # Don't know why this works lmao
        url = video.get("url")
        if not isinstance(url, str) or not url:
            continue
        video_id = video.get("video_id")
        title = video.get("title")
        keywords = video.get("keywords")
        views = video.get("views")
        rate = video.get("rate")
        publish_date = video.get("added")
        length_seconds = video.get("length_sec")
        length_minutes = video.get("length_min")
        embed_url = video.get("embed_url")
        thumbnail = video.get("default_thumb").get("src")
        thumbnails = video.get("thumbs")

        videos.append({
            "url": url,
            "title": title,
            "keywords": keywords,
            "views": views,
            "rate": rate,
            "publish_date": publish_date,
            "length_seconds": length_seconds,
            "length_minutes": length_minutes,
            "embed_url": embed_url,
            "thumbnail": thumbnail,
            "thumbnails": thumbnails,
            "video_id": video_id

        })

    return videos
