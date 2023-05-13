#!/usr/bin/python
# -*- coding: UTF-8 -*-
from datetime import datetime
import json
import logging
from notion_client import Client
import argparse
import concurrent.futures

from datetime import datetime

from requests.api import get, post

template = """---
title: {title}
date: {date}
featured_image: {cover}
draft: {draft}
tags: {tags}
categories: {categories}
comment : true
---
"""

# _continued_numbered_list = False
# _numbered_list_number = 1

def blocks_children(block_id):
    response = client.blocks.children.list(block_id=block_id)
    with open(f"{block_id}.json","w") as f:
        f.write(json.dumps(response))
    return response.get("results")


def convert( blocks: dict) -> str:
    outcome_blocks: str = ""
    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = executor.map(convert_block, blocks)
        outcome_blocks = "".join([result for result in results])
    return outcome_blocks


def convert_block(block: dict, depth=0) -> str:
    outcome_block: str = ""
    block_type = block["type"]
    # Special Case: Block is blank
    if (
        block_type == "paragraph"
        and not block["has_children"]
        and not block[block_type]["rich_text"]
    ):
        return blank() + "\n\n"
    # Normal Case
    try:
        if block_type in BLOCK_TYPES:
            outcome_block = (
                BLOCK_TYPES[block_type](
                    collect_info(block[block_type])
                )
                + "\n\n"
            )
        else:
            outcome_block = f"[//]: # ({block_type} is not supported)\n\n"
        # Convert child block
        if block["has_children"]:
            # create child page
            if block_type == "child_page":
                # call make_child_function
                pass
            # create table block
            elif block_type == "table":
                depth += 1
                child_blocks = blocks_children(block["id"])
                with open("test2.json","w") as f:
                    f.write(json.dumps(child_blocks))
                outcome_block = create_table(cell_blocks=child_blocks)
            # create indent block
            else:
                depth += 1
                child_blocks = blocks_children(block["id"])
                for block in child_blocks:
                    outcome_block += "\t" * depth + convert_block(
                        block, depth
                    )
    except Exception as e:
        logging.error(e)
    return outcome_block

def create_table( cell_blocks: dict):
    table_list = []
    for cell_block in cell_blocks:
        cell_block_type = cell_block["type"]
        table_list.append(
            BLOCK_TYPES[cell_block_type](
                collect_info(cell_block[cell_block_type])
            )
        )
    # convert to markdown table
    for index, value in enumerate(table_list):
        if index == 0:
            table = " | " + " | ".join(value) + " | " + "\n"
            table += (
                " | " + " | ".join(["----"] * len(value)) + " | " + "\n"
            )
            continue
        table += " | " + " | ".join(value) + " | " + "\n"
    table += "\n"
    return table

def collect_info(payload: dict) -> dict:
    """内容"""
    info = dict()
    if "rich_text" in payload:
        info["text"] = richtext_convertor(payload["rich_text"])
    if "icon" in payload:
        info["icon"] = payload["icon"]["emoji"]
    if "checked" in payload:
        info["checked"] = payload["checked"]
    if "expression" in payload:
        info["text"] = payload["expression"]
    if "url" in payload:
        info["url"] = payload["url"]
    if "caption" in payload:
        info["caption"] = richtext_convertor(payload["caption"])
    if "external" in payload:
        info["url"] = payload["external"]["url"]
    if "language" in payload:
        info["language"] = payload["language"]
    # interal url
    if "file" in payload:
        info["url"] = payload["file"]["url"]
    # table cells
    if "cells" in payload:
        info["cells"] = payload["cells"]
    # info["number"] = _numbered_list_number
    return info
# Link
def text_link(item: dict):
    """
    input: item:dict ={"content":str,"link":str}
    """
    return f"[{item['content']}]({item['link']['url']})"


# Annotations
def bold(content: str):
    return f"**{content}**"


def italic(content: str):
    return f"*{content}*"


def strikethrough(content: str):
    return f"~~{content}~~"


def underline(content: str):
    return f"<u>{content}</u>"


def code(content: str):
    return f"`{content}`"


def color(content: str, color):
    return f"<span style='color:{color}'>{content}</span>"


def equation(content: str):
    return f"$ {content} $"


annotation_map = {
    "bold": bold,
    "italic": italic,
    "strikethrough": strikethrough,
    "underline": underline,
    "code": code,
}


# Mentions
def _mention_link(content, url):
    return f"([{content}]({url}])"


def user(information: dict):
    return f"({information['content']})"


def page(information: dict):
    return _mention_link(information["content"], information["url"])


def date(information: dict):
    return f"({information['content']})"


def database(information: dict):
    return _mention_link(information["content"], information["url"])


def mention_information(payload: dict):
    information = dict()
    if payload["href"]:
        information["url"] = payload["href"]
        if payload["plain_text"] != "Untitled":
            information["content"] = payload["plain_text"]
        else:
            information["content"] = payload["href"]
    else:
        information["content"] = payload["plain_text"]

    return information

def richtext_convertor(richtext_list: list) -> str:
    outcome_sentence = ""
    for richtext in richtext_list:
        outcome_sentence += richtext_word_converter(richtext)
    return outcome_sentence

mention_map = {"user": user, "page": page, "database": database, "date": date}



def richtext_word_converter(richtext: dict) -> str:
    outcome_word = ""
    plain_text = richtext["plain_text"]
    if richtext["type"] == "equation":
        outcome_word = equation(plain_text)
    elif richtext["type"] == "mention":
        mention_type = richtext["mention"]["type"]
        if mention_type in mention_map:
            outcome_word = mention_map[mention_type](
                mention_information(richtext)
            )
    else:
        if richtext["href"]:
            outcome_word = text_link(richtext["text"])
        else:
            outcome_word = plain_text
        annot = richtext["annotations"]
        for key, transfer in annotation_map.items():
            if richtext["annotations"][key]:
                outcome_word = transfer(outcome_word)
        if annot["color"] != "default":
            outcome_word = color(outcome_word, annot["color"])
    return outcome_word

# Converting Methods
def paragraph(info: dict) -> str:
    return info["text"]


def heading_1(info: dict) -> str:
    return f"# {info['text']}"


def heading_2(info: dict) -> str:
    return f"## {info['text']}"


def heading_3(info: dict) -> str:
    return f"### {info['text']}"


def callout(info: dict) -> str:
    return f"{info['icon']} {info['text']}"


def quote(info: dict) -> str:
    return f"> {info['text']}"


# toggle item will be changed as bulleted list item
def bulleted_list_item(info: dict) -> str:
    return f"- {info['text']}"


# numbering is not supported
def numbered_list_item(info: dict) -> str:
    """
    input: item:dict = {"number":int, "text":str}
    """
    return f"1. {info['text']}"


def to_do(info: dict) -> str:
    """
    input: item:dict = {"checked":bool, "test":str}
    """
    return f"- {'[x]' if info['checked'] else '[ ]'} {info['text']}"

def code(info: dict) -> str:
    """
    input: item:dict = {"language":str,"text":str}
    """
    return f"\n```{info['language']}\n{info['text']}\n```"


def embed(info: dict) -> str:
    """
    input: item:dict ={"url":str,"text":str}
    """
    print(info['url'])
    print(info['url'].startswith("https://twitter.com/"))
    if(info['url'].startswith("https://twitter.com/")):
       user = info['url'].split("/")[3]
       id = info['url'].split("/")[5]
       return f'{{{{< tweet user="{user}" id="{id}" >}}}}'
    return f"[{info['url']}]({info['url']})"


def image(info: dict) -> str:
    """
    input: item:dict ={"url":str,"text":str,"caption":str}
    """
    # name,file_path = downloader(info['url'])

    if info["caption"]:
        return (
            f"![{info['caption']}]({info['url']})"
        )
    else:
        return f"![]({info['url']})"


def file(info: dict) -> str:
    # name,file_path = downloader(info['url'])
    return f"[{info['file_name']}]({info['file_path']})"


def bookmark(info: dict) -> str:
    """
    input: item:dict ={"url":str,"text":str,"caption":str}
    """
    if info["caption"]:
        return f"[{info['url']}]({info['url']})\n\n{info['caption']}"
    else:
        return f"[{info['url']}]({info['url']})"


def equation(info: dict) -> str:
    return f"$$ {info['text']} $$"

def table(info: dict) -> str:
    return ""

def divider(info: dict) -> str:
    return "---"


def blank() -> str:
    return "<br/>"


def table_row(info: list) -> list:
    """
    input: item:list = [[richtext],....]
    """
    column_list = []
    for column in info["cells"]:
        column_list.append(richtext_convertor(column))
    return column_list


# Since Synced Block has only child blocks, not name, it will return blank
def synced_block(info: list) -> str:
    return "[//]: # (Synced Block)"

# Block type map
BLOCK_TYPES = {
    "paragraph": paragraph,
    "heading_1": heading_1,
    "heading_2": heading_2,
    "heading_3": heading_3,
    "callout": callout,
    "toggle": bulleted_list_item,
    "quote": quote,
    "bulleted_list_item": bulleted_list_item,
    "numbered_list_item": numbered_list_item,
    "to_do": to_do,
    # "child_page": child_page,
    "code": code,
    "embed": embed,
    "image": image,
    "bookmark": bookmark,
    "equation": equation,
    "divider": divider,
    "file": file,
    "table_row": table_row,
    "table": table,
    "synced_block": synced_block,
}

def query(database_id):
    response = client.databases.query(database_id=database_id)
    results = response.get("results")
    
    for result in results:
        id = result.get("id")
        cover = result.get("cover").get("external").get("url")
        properties = result.get("properties")
        print(properties)
        title = properties.get("Title").get("title")[0].get("text").get("content")
        tags = [x["name"] for x in properties.get("Tags").get("multi_select")]
        categories = [x["name"] for x in properties.get("Categories").get("multi_select")]
        date = properties.get("Date").get("created_time")
        draft = properties.get("Draft").get("checkbox")
        file = properties.get("File").get("rich_text")[0].get("plain_text")
        head = template.format(title=title,date=date,cover=cover,draft=draft,tags=tags,categories=categories)
        file = f"./content/posts/{file}.md"
        blocks =blocks_children(id)
        markdown = head
        markdown += convert(blocks)
        with open(file, "w") as f:
            f.write(markdown)
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("notion_token")
    parser.add_argument("database_id")
    args = parser.parse_args()
    notion_token = args.notion_token
    database_id = args.database_id
    client = Client(
        auth=notion_token,
        log_level=logging.ERROR
    )
    query(database_id)