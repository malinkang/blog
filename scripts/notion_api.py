from datetime import datetime, timedelta
import json
import logging
import os
from notion_client import Client

NOTION_TOKEN = "secret_xvMkQzLkCRtZL478L8MhvLdIDOxicjjSUm9U9voAwbb"
NOTION_VERSION = "2022-06-28"
DATA_DIR = "./data/"
YEAR_DATABASE_ID = "f4d2374344ca409aa22d40e8d33833eb"
MONTH_DATABASE_ID = "dd39319e45964a64899ae5371c0a6421"
WEEK_DATABASE_ID = "194f66886cd8479899d38b0fb0b7da26"


# https://developers.notion.com/reference/page
class Page(dict):
    def parent(self, parent):
        self["parent"] = parent
        return self

    def children(self, children):
        self["children"] = children
        return self

    def cover(self, cover):
        self["cover"] = {"type": "external", "external": {"url": cover}}
        return self

    def icon(self, icon):
        self["icon"] = {"type": "emoji", "emoji": icon}
        return self

    def properties(self, properties):
        self["properties"] = properties
        return self


# https://developers.notion.com/reference/page#database-parent
class DatabaseParent(dict):
    def __init__(self, database_id):
        self["type"] = "database_id"
        self["database_id"] = database_id


class Properties(dict):
    """https://developers.notion.com/reference/property-value-object"""

    def title(self, title):
        self["title"] = {
            "title": [{"type": "text", "text": {"content": title}}]}
        return self

    def multi_select(self, property, list):
        multi_select = []
        for item in list:
            multi_select.append({"name": item})
        self[property] = {
            "type": "multi_select",
            "multi_select": multi_select,
        }
        return self

    def people(self, property, list):
        people = []
        for item in list:
            people.append({"object": "user", "id": item})
        self[property] = {
            "people": people,
        }
        return self

    def rich_text(self, property, text):
        rich_text = []
        rich_text.append({"type": "text", "text": {"content": text}})
        self[property] = {
            "rich_text": rich_text,
        }
        return self

    def status(self, property, status):
        self[property] = {"status": {"name": status}}
        return self

    def file(self, property, file):
        self[property] = {"files": [
            {
                "type": "external",
                "name": property,
                "external": {
                    "url": file
                }
            }
        ]}
        return self

    def select(self, property, name):
        self[property] = {"select": {"name": name}}
        return self
    def url(self, property, url):
        self[property] = {"url": url}
        return self

    def date(
        self,
        property="Date",
        start=datetime.now() + timedelta(hours=8),
        end=None,
        time_zone="Asia/Shanghai",
    ):
        # 如果是date类型需要格式化 如果是字符串类型则不需要
        if isinstance(start, datetime):
            start = start.isoformat()
        if isinstance(end, datetime):
            end = end.isoformat()
        self[property] = {"date": {"start": start,
                                   "end": end, "time_zone": time_zone}}
        return self

    def number(self, property, number):
        self[property] = {"number": number}
        return self

    def relation(self, property, relation):
        self[property] = {"relation": [{"id": relation}]}
        return self


class Children(list):
    def add_block(self, type, content, link=None, color="default"):
        text = Text(content)
        if link is not None:
            link = Link(link)
            text = text.link(link)
        rich_text = RichText(text)
        block = Block(type, color).add_rich_text(rich_text)
        self.append(block)
        return self

    def add_embed_block(self, url):
        self.append(EmbedBlock(url))
        return self


"""https://developers.notion.com/reference/block"""


class Block(dict):
    def __init__(self, type, color):
        self["object"] = "block"
        self["type"] = type
        self[type] = {"rich_text": [], "color": color}
        if type == "to_do":
            self[type]["checked"] = True

    def add_rich_text(self, rich_text):
        self[self["type"]]["rich_text"].append(rich_text)
        return self


"""https://developers.notion.com/reference/block#embed-blocks"""


class EmbedBlock(dict):
    def __init__(self, url):
        self["object"] = "block"
        self["type"] = "embed"
        self["embed"] = {"url": url}


class RichText(dict):
    def __init__(self, text, type="text"):
        self["type"] = type
        self["text"] = text


# https://developers.notion.com/reference/rich-text#link-objects
class Link(dict):
    def __init__(self, link):
        self["type"] = "url"
        self["url"] = link


# https://developers.notion.com/reference/rich-text#text-objects
class Text(dict):
    def __init__(self, content):
        self["content"] = content

    def link(self, link):
        self["link"] = link
        return self


client = Client(
    auth=NOTION_TOKEN, notion_version=NOTION_VERSION, 
    log_level=logging.DEBUG
)


def create_page(page):
    response = client.pages.create(
        parent=page["parent"],
        properties=page["properties"],
        children=page["children"],
        icon=page["icon"],
        cover=page["cover"],
    )
    return response


def update_page(page_id, properties, icon=None, cover=None):
    response = client.pages.update(
        page_id, properties=properties, icon=icon, cover=cover)
    return response


def query_database(database_id, filter=None, sorts=None, page_size=None):
    response = client.databases.query(
        database_id=database_id, filter=filter, sorts=sorts, page_size=page_size
    )
    return response

def blocks_retrieve(block_id):
    return client.blocks.retrieve(block_id=block_id)

def blocks_children_retrieve(block_id):
    return client.blocks.children.list(block_id=block_id)

def pages_retrieve(page_id):
    return client.pages.retrieve(page_id=page_id)


def properties_retrieve(page_id, property_id):
    response = client.pages.properties.retrieve(
        page_id=page_id, property_id=property_id
    )
    return response


def get_title(response, name, index=0):
    result = response.get("results")[index]
    response = client.pages.properties.retrieve(
        page_id=result.get("id"),
        property_id=result.get("properties").get(name).get("id"),
    )
    return response.get("results")[0].get("title").get("text").get("content")


def get_rich_text(response, name, index=0):
    result = response.get("results")[index]
    response = client.pages.properties.retrieve(
        page_id=result.get("id"),
        property_id=result.get("properties").get(name).get("id"),
    )
    if len(response.get("results")) > 0:
        return response.get("results")[0].get("rich_text").get("text").get("content")
    return None


def get_date(response, name="Date", index=0):
    result = response.get("results")[index]
    response = client.pages.properties.retrieve(
        page_id=result.get("id"),
        property_id=result.get("properties").get(name).get("id"),
    )
    return response.get("date")


def get_multi_select(response, name, index=0):
    result = response.get("results")[index]
    response = client.pages.properties.retrieve(
        page_id=result.get("id"),
        property_id=result.get("properties").get(name).get("id"),
    )
    return response.get("multi_select")


def get_select(response, name, index=0):
    result = response.get("results")[index]
    response = client.pages.properties.retrieve(
        page_id=result.get("id"),
        property_id=result.get("properties").get(name).get("id"),
    )
    return response.get("select").get("name")


# 根据类型获取
def get_by_type(response, name, type, index=0):
    result = response.get("results")[index]
    response = client.pages.properties.retrieve(
        page_id=result.get("id"),
        property_id=result.get("properties").get(name).get("id"),
    )
    return response.get(type)


def get_number(response, name, index=0):
    result = response.get("results")[index]
    response = client.pages.properties.retrieve(
        page_id=result.get("id"),
        property_id=result.get("properties").get(name).get("id"),
    )
    return response.get("number")


def get_formula(response, name, index=0, type="string"):
    if isinstance(response.get("results"), list):
        result = response.get("results")[index]
    else:
        result = response
    response = client.pages.properties.retrieve(
        page_id=result.get("id"),
        property_id=result.get("properties").get(name).get("id"),
    )
    return response.get("formula").get(type)


def get_page_id(response, index=0):
    return response.get("results")[index].get("id")


def get_properties_id(response, name, index=0):
    return response.get("results")[index].get("properties").get(name).get("id")


def get_week_relation(year_id, date):
    year = date.isocalendar().year
    week = date.isocalendar().week
    week = "第" + str(week) + "周"
    week_json_file = DATA_DIR + str(year) + "/" + week + ".json"
    if os.path.exists(week_json_file):
        with open(week_json_file, "r") as json_file:
            return json.load(json_file).get("id")

    filter = {
        "and": [
            {"property": "Name", "rich_text": {"equals": week}},
            {"property": "Year", "relation": {"contains": year_id}},
        ]
    }

    response = query_database(database_id=WEEK_DATABASE_ID, filter=filter)
    if len(response.get("results")) == 0:
        start = date - timedelta(days=date.weekday())
        end = start + timedelta(days=6)
        print(start)
        parent = DatabaseParent(WEEK_DATABASE_ID)
        properties = (
            Properties().title(week).date("Date", start, end).relation("Year", year_id)
        )
        page = (
            Page()
            .parent(parent=parent)
            .children(Children())
            .properties(properties)
            .icon("🌿")
            .cover(unsplash.random())
        )
        id = create_page(page=page).get("id")
    else:
        id = response.get("results")[0].get("id")
        print("week_id = ", id)
    json_data = {"id": id}
    with open(week_json_file, "w") as outfile:
        json.dump(json_data, outfile)
    return id


def get_month_relation(year_id, year, month):
    id = ""
    month_json_file = DATA_DIR + year + "/" + month + ".json"
    if os.path.exists(month_json_file):
        with open(month_json_file, "r") as json_file:
            return json.load(json_file).get("id")
    filter = {
        "and": [
            {"property": "Name", "title": {"equals": month}},
            {"property": "Year", "relation": {"contains": year_id}},
        ]
    }
    response = query_database(database_id=MONTH_DATABASE_ID, filter=filter)
    if len(response.get("results")) == 0:
        parent = DatabaseParent(MONTH_DATABASE_ID)
        properties = Properties().title(month).relation("Year", year_id)
        page = (
            Page()
            .parent(parent=parent)
            .children(Children())
            .properties(properties)
            .icon("😄")
            .cover(unsplash.random())
        )
        id = create_page(page=page).get("id")
    else:
        id = response.get("results")[0].get("id")
        print("month = ", id)
    json_data = {"id": id}
    with open(month_json_file, "w") as outfile:
        json.dump(json_data, outfile)
    return id


def get_year_releation(year):
    id = ""
    year_json_file = DATA_DIR + year + "/id.json"
    # 优先从json里面找
    if os.path.exists(year_json_file):
        with open(year_json_file, "r") as json_file:
            return json.load(json_file).get("id")
    filter = {"property": "Name", "rich_text": {"equals": year}}
    response = query_database(database_id=YEAR_DATABASE_ID, filter=filter)
    print(response)
    # 如果返回结果为空，则创建年份
    if len(response.get("results")) == 0:
        parent = DatabaseParent(YEAR_DATABASE_ID)
        properties = Properties().title(year)
        page = (
            Page()
            .parent(parent=parent)
            .children(Children())
            .properties(properties)
            .icon("😄")
            .cover(unsplash.random())
        )
        id = create_page(page=page).get("id")
    else:
        id = response.get("results")[0].get("id")
    print(id)
    json_data = {"id": id}
    year_dir = "./data/" + year
    if os.path.exists(year_dir) == False:
        os.makedirs(year_dir)
    with open(year_json_file, "w") as outfile:
        json.dump(json_data, outfile)
    return id


def get_relation(properties, date=datetime.now(), include_day=False):
    year = date.strftime("%Y")
    month = date.strftime("%-m月")
    year_id = get_year_releation(year)
    print("year_id:", year_id)
    properties["Year"] = {
        "relation": [
            {
                "id": year_id,
            }
        ]
    }
    properties["Month"] = {
        "relation": [
            {
                "id": get_month_relation(year_id, year, month),
            }
        ]
    }
    properties["Week"] = {
        "relation": [
            {
                "id": get_week_relation(year_id, date),
            }
        ]
    }
    return properties
