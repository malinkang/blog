#!/usr/bin/env python3
"""Sync a Notion database into Hugo Markdown posts.

Media uploaded to Notion is rewritten to Notion's proxy endpoints instead of the
short-lived S3 URLs returned by the API. This keeps generated Markdown stable
without storing large binaries in the Git repository.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import quote

from notion_client import Client

DEFAULT_NOTION_HOST = "https://www.notion.so"


def yaml_quote(value: Any) -> str:
    text = "" if value is None else str(value)
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip().lower()
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"[^\w\-\u4e00-\u9fff]+", "", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "untitled"


def normalize_id(value: str) -> str:
    return value.replace("-", "")


class NotionToMarkdown:
    def __init__(self, token: str, notion_host: str = DEFAULT_NOTION_HOST):
        self.client = Client(auth=token)
        self.notion_host = notion_host.rstrip("/")

    def query_database(self, database_id: str) -> list[dict[str, Any]]:
        pages: list[dict[str, Any]] = []
        cursor = None
        while True:
            payload: dict[str, Any] = {"database_id": database_id}
            if cursor:
                payload["start_cursor"] = cursor
            response = self.client.databases.query(**payload)
            pages.extend(response.get("results", []))
            if not response.get("has_more"):
                return pages
            cursor = response.get("next_cursor")

    def block_children(self, block_id: str) -> list[dict[str, Any]]:
        children: list[dict[str, Any]] = []
        cursor = None
        while True:
            payload: dict[str, Any] = {"block_id": block_id}
            if cursor:
                payload["start_cursor"] = cursor
            response = self.client.blocks.children.list(**payload)
            children.extend(response.get("results", []))
            if not response.get("has_more"):
                return children
            cursor = response.get("next_cursor")

    def convert_database(self, database_id: str, content_dir: Path, dry_run: bool = False) -> list[Path]:
        content_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for page in self.query_database(database_id):
            if page.get("archived") or page.get("in_trash"):
                continue
            markdown, destination = self.page_to_markdown(page, content_dir)
            written.append(destination)
            if dry_run:
                print(f"[dry-run] would write {destination}")
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(markdown, encoding="utf-8")
            print(f"wrote {destination}")
        return written

    def page_to_markdown(self, page: dict[str, Any], content_dir: Path) -> tuple[str, Path]:
        props = page.get("properties", {})
        title = self.get_title(props) or "Untitled"
        description = self.get_text_property(props, "Description", "摘要", "Summary")
        date = (
            self.get_date_property(props, "Date", "Published", "Publish Date", "日期")
            or page.get("created_time")
        )
        draft = self.get_checkbox_property(props, "Draft", "草稿")
        tags = self.get_multi_select_property(props, "Tags", "标签")
        categories = self.get_multi_select_property(props, "Categories", "Category", "分类")
        image = self.get_cover_url(page, props)
        destination = self.get_destination(page, props, content_dir, title)

        front_matter: list[str] = ["---"]
        front_matter.append(f"title: {yaml_quote(title)}")
        if description:
            front_matter.append(f"description: {yaml_quote(description)}")
        if date:
            front_matter.append(f"date: {date}")
        if image:
            front_matter.append(f"image: {yaml_quote(image)}")
        front_matter.append(f"draft: {'true' if draft else 'false'}")
        front_matter.append("comments: true")
        if tags:
            front_matter.append("tags:")
            front_matter.extend(f"  - {yaml_quote(tag)}" for tag in tags)
        if categories:
            front_matter.append("categories:")
            front_matter.extend(f"  - {yaml_quote(category)}" for category in categories)
        front_matter.append("---")

        blocks = self.block_children(page["id"])
        body = self.convert_blocks(blocks).strip()
        markdown = "\n".join(front_matter) + "\n\n" + body + "\n"
        return markdown, destination

    def get_destination(self, page: dict[str, Any], props: dict[str, Any], content_dir: Path, title: str) -> Path:
        file_value = self.get_text_property(props, "File", "Filename", "文件")
        if file_value:
            rel = file_value.strip().lstrip("/")
            if not rel.endswith(".md"):
                rel = f"{rel}.md"
            return content_dir / rel

        slug = self.get_text_property(props, "Slug", "slug", "路径") or slugify(title)
        slug = slug.strip().strip("/")
        if slug.endswith(".md"):
            return content_dir / slug
        return content_dir / slug / "index.md"

    def get_cover_url(self, page: dict[str, Any], props: dict[str, Any]) -> str:
        prop_file = self.get_file_property(props, "Image", "Cover", "封面")
        if prop_file:
            return self.media_url(prop_file, page["id"], "image")
        cover = page.get("cover")
        if cover:
            return self.media_url(cover, page["id"], "image")
        return ""

    def get_prop(self, props: dict[str, Any], *names: str) -> dict[str, Any] | None:
        lower = {key.lower(): value for key, value in props.items()}
        for name in names:
            if name in props:
                return props[name]
            found = lower.get(name.lower())
            if found is not None:
                return found
        return None

    def get_title(self, props: dict[str, Any]) -> str:
        for value in props.values():
            if value.get("type") == "title":
                return self.rich_text_to_plain(value.get("title", []))
        return ""

    def get_text_property(self, props: dict[str, Any], *names: str) -> str:
        prop = self.get_prop(props, *names)
        if not prop:
            return ""
        prop_type = prop.get("type")
        if prop_type in {"title", "rich_text"}:
            return self.rich_text_to_plain(prop.get(prop_type, []))
        if prop_type == "url":
            return prop.get("url") or ""
        if prop_type == "select":
            return (prop.get("select") or {}).get("name", "")
        if prop_type == "status":
            return (prop.get("status") or {}).get("name", "")
        return ""

    def get_date_property(self, props: dict[str, Any], *names: str) -> str:
        prop = self.get_prop(props, *names)
        if not prop:
            return ""
        if prop.get("type") == "date" and prop.get("date"):
            return prop["date"].get("start", "")
        if prop.get("type") in {"created_time", "last_edited_time"}:
            return prop.get(prop["type"], "")
        return ""

    def get_checkbox_property(self, props: dict[str, Any], *names: str) -> bool:
        prop = self.get_prop(props, *names)
        return bool(prop and prop.get("type") == "checkbox" and prop.get("checkbox"))

    def get_multi_select_property(self, props: dict[str, Any], *names: str) -> list[str]:
        prop = self.get_prop(props, *names)
        if not prop:
            return []
        if prop.get("type") == "multi_select":
            return [item["name"] for item in prop.get("multi_select", []) if item.get("name")]
        if prop.get("type") == "select" and prop.get("select"):
            return [prop["select"]["name"]]
        return []

    def get_file_property(self, props: dict[str, Any], *names: str) -> dict[str, Any] | None:
        prop = self.get_prop(props, *names)
        if not prop or prop.get("type") != "files":
            return None
        files = prop.get("files", [])
        return files[0] if files else None

    def rich_text_to_plain(self, rich_text: list[dict[str, Any]]) -> str:
        return "".join(item.get("plain_text", "") for item in rich_text).strip()

    def rich_text_to_markdown(self, rich_text: list[dict[str, Any]], inline: bool = False) -> str:
        chunks: list[str] = []
        for item in rich_text:
            text = item.get("plain_text", "")
            if not text:
                continue
            annotations = item.get("annotations", {})
            if annotations.get("code"):
                text = f"`{text}`"
            if annotations.get("bold"):
                text = f"**{text}**"
            if annotations.get("italic"):
                text = f"*{text}*"
            if annotations.get("strikethrough"):
                text = f"~~{text}~~"
            if annotations.get("underline"):
                text = f"<u>{text}</u>"
            href = item.get("href")
            if href:
                text = f"[{text}]({href})"
            chunks.append(text)
        result = "".join(chunks)
        return result.replace("\n", " ") if inline else result

    def convert_blocks(self, blocks: list[dict[str, Any]], depth: int = 0) -> str:
        parts: list[str] = []
        for block in blocks:
            converted = self.convert_block(block, depth)
            if converted:
                parts.append(converted.rstrip())
        return "\n\n".join(parts) + ("\n" if parts else "")

    def convert_block(self, block: dict[str, Any], depth: int = 0) -> str:
        block_type = block.get("type")
        payload = block.get(block_type, {}) if block_type else {}
        children = self.block_children(block["id"]) if block.get("has_children") else []
        child_md = self.convert_blocks(children, depth + 1).strip() if children else ""

        if block_type == "paragraph":
            text = self.rich_text_to_markdown(payload.get("rich_text", []))
            return self.with_children(text, child_md, depth)
        if block_type == "heading_1":
            return f"# {self.rich_text_to_markdown(payload.get('rich_text', []), inline=True)}"
        if block_type == "heading_2":
            return f"## {self.rich_text_to_markdown(payload.get('rich_text', []), inline=True)}"
        if block_type == "heading_3":
            return f"### {self.rich_text_to_markdown(payload.get('rich_text', []), inline=True)}"
        if block_type == "bulleted_list_item":
            return self.list_item("-", payload, child_md, depth)
        if block_type == "numbered_list_item":
            return self.list_item("1.", payload, child_md, depth)
        if block_type == "to_do":
            marker = "[x]" if payload.get("checked") else "[ ]"
            return self.list_item(f"- {marker}", payload, child_md, depth)
        if block_type == "toggle":
            title = self.rich_text_to_markdown(payload.get("rich_text", []), inline=True)
            return f"<details>\n<summary>{title}</summary>\n\n{child_md}\n</details>"
        if block_type == "quote":
            text = self.rich_text_to_markdown(payload.get("rich_text", []))
            quote = "\n".join(f"> {line}" for line in text.splitlines())
            return self.with_children(quote, child_md, depth)
        if block_type == "callout":
            icon = payload.get("icon", {}).get("emoji", "💡")
            text = self.rich_text_to_markdown(payload.get("rich_text", []))
            return self.with_children(f"> {icon} {text}", child_md, depth)
        if block_type == "divider":
            return "---"
        if block_type == "code":
            language = payload.get("language") or "text"
            text = self.rich_text_to_plain(payload.get("rich_text", []))
            return f"```{language}\n{text}\n```"
        if block_type == "image":
            url = self.media_url(payload, block["id"], "image")
            caption = self.rich_text_to_plain(payload.get("caption", []))
            return f"![{caption}]({url})" if url else ""
        if block_type == "video":
            url = self.media_url(payload, block["id"], "video")
            return f'<video controls src="{url}"></video>' if url else ""
        if block_type == "audio":
            url = self.media_url(payload, block["id"], "audio")
            return f'<audio controls src="{url}"></audio>' if url else ""
        if block_type in {"file", "pdf"}:
            url = self.media_url(payload, block["id"], block_type)
            caption = self.rich_text_to_plain(payload.get("caption", [])) or payload.get("name") or block_type.upper()
            return f"[{caption}]({url})" if url else ""
        if block_type in {"bookmark", "embed", "link_preview"}:
            url = payload.get("url", "")
            caption = self.rich_text_to_plain(payload.get("caption", []))
            return f"[{caption or url}]({url})" if url else ""
        if block_type == "equation":
            return f"$$\n{payload.get('expression', '')}\n$$"
        if block_type == "table":
            return self.convert_table(children)
        if block_type == "child_page":
            title = payload.get("title", "Untitled")
            return f"## {title}\n\n{child_md}" if child_md else f"## {title}"
        if child_md:
            return child_md
        return f"<!-- Unsupported Notion block: {block_type} -->"

    def with_children(self, text: str, child_md: str, depth: int) -> str:
        if not child_md:
            return text
        return f"{text}\n\n{self.indent(child_md, depth + 1)}"

    def list_item(self, bullet: str, payload: dict[str, Any], child_md: str, depth: int) -> str:
        indent = "  " * depth
        text = self.rich_text_to_markdown(payload.get("rich_text", []), inline=True)
        line = f"{indent}{bullet} {text}".rstrip()
        if child_md:
            line += "\n" + self.indent(child_md, depth + 1)
        return line

    def indent(self, text: str, depth: int) -> str:
        prefix = "  " * depth
        return "\n".join(prefix + line if line else line for line in text.splitlines())

    def convert_table(self, rows: list[dict[str, Any]]) -> str:
        table_rows: list[list[str]] = []
        for row in rows:
            payload = row.get("table_row", {})
            cells = payload.get("cells", [])
            table_rows.append([self.rich_text_to_markdown(cell, inline=True).replace("|", "\\|") for cell in cells])
        if not table_rows:
            return ""
        width = max(len(row) for row in table_rows)
        table_rows = [row + [""] * (width - len(row)) for row in table_rows]
        lines = ["| " + " | ".join(table_rows[0]) + " |"]
        lines.append("| " + " | ".join(["---"] * width) + " |")
        for row in table_rows[1:]:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    def media_url(self, payload: dict[str, Any], block_id: str, media_type: str) -> str:
        media_kind = payload.get("type")
        if media_kind == "external":
            return payload.get("external", {}).get("url", "")
        if media_kind == "file":
            source = payload.get("file", {}).get("url", "")
            return self.notion_proxy_url(source, block_id, media_type)
        if media_kind == "file_upload":
            source = payload.get("file_upload", {}).get("url", "")
            return self.notion_proxy_url(source, block_id, media_type)
        # Cover/file properties use the same file object shape without nesting under block type.
        if payload.get("file", {}).get("url"):
            return self.notion_proxy_url(payload["file"]["url"], block_id, media_type)
        if payload.get("external", {}).get("url"):
            return payload["external"]["url"]
        return payload.get("url", "")

    def notion_proxy_url(self, url: str, block_id: str, media_type: str) -> str:
        if not url:
            return ""
        encoded = quote(url, safe="")
        clean_id = normalize_id(block_id)
        if media_type == "image":
            return f"{self.notion_host}/image/{encoded}?table=block&id={clean_id}&cache=v2"
        return f"{self.notion_host}/signed/{encoded}?table=block&id={clean_id}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Notion database pages to Hugo Markdown.")
    parser.add_argument("--database-id", default=os.getenv("NOTION_DATABASE_ID"), help="Notion database ID")
    parser.add_argument("--content-dir", default=os.getenv("CONTENT_DIR", "content/posts"), help="Output content directory")
    parser.add_argument("--notion-host", default=os.getenv("NOTION_HOST", DEFAULT_NOTION_HOST), help="Notion host used for /image and /signed proxy URLs")
    parser.add_argument("--dry-run", action="store_true", help="Print files that would be written")
    args = parser.parse_args()

    token = os.getenv("NOTION_TOKEN")
    if not token:
        print("NOTION_TOKEN is required", file=sys.stderr)
        return 2
    if not args.database_id:
        print("NOTION_DATABASE_ID or --database-id is required", file=sys.stderr)
        return 2

    syncer = NotionToMarkdown(token=token, notion_host=args.notion_host)
    written = syncer.convert_database(args.database_id, Path(args.content_dir), dry_run=args.dry_run)
    print(f"synced {len(written)} page(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
