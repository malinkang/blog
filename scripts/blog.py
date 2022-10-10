#!/usr/bin/python
# -*- coding: UTF-8 -*-
from datetime import datetime, timedelta
import notion_api
template = '''
---
title: "{title}"
date: {date}
featured_image: "{cover}"
draft: false
tags: [{tags}]
categories: [Android]
comment : true
---
'''



ids = ['48fa2b28ce294476b12046589ac33663']

#查询笔记
def query(database_id):
    time = datetime.now()-timedelta(days=1)
    time = time.isoformat()
    print(time)
    filter = {
        'and': [
            {
                "property": "Publish",
                "checkbox": {
                    "equals": True
                }
                
            },
            {
                 "timestamp": "last_edited_time",
                 "last_edited_time":{
                    "after":time
                 }
            }
        ]
    }
    response = notion_api.query_database(database_id=database_id, filter=filter)
    results = response['results']
    for result in results:
        id = result['id']
        id = result['id']
        property = result['properties']
        tags = property['Tag']['multi_select']
        date = property['PublishDate']['date']['start']
        tags = ",".join(list(map(lambda tag:tag['name'],tags)))
        title = parse_text(property['Title']['title'])
        file = parse_text(property['File']['rich_text'])+'.md'
        cover = result['cover']['external']['url']
        post = template.format(title=title,date=date,cover=cover,tags=tags)
        blocks(post=post,id=id,file=file)
            

# 创建markdown文件


def new_post(markdown,file):
    with open("./content/posts/"+file, "w") as f:
        f.write(markdown)

# 解析文本


def parse_text(text):
    r = ''
    for t in text:
        content = t.get("text").get("content")
        link = t.get("text").get("link")
        annotations = t.get("annotations")
        bold = annotations.get("bold")
        italic = annotations.get("italic")
        strikethrough = annotations.get("strikethrough")
        underline = annotations.get("underline")
        code = annotations.get("code")
        color = annotations.get("color")
        if (bold):
            content = "**"+content+"**"
        if (italic):
            content = "_"+content+"_"
        if (strikethrough):
            content = "~~"+content+"~~"
        if (underline):
            content = "<u>"+content+"</u>"
        if (code):
            content = "`"+content+"`"
        if (color != 'default'):
            content = "<font color='"+color+"'>"+content+"</font>"
        if link:
            content = '['+content+']('+link['url']+')'
        r += content
    return r


def blocks(post,id,file):
    response = notion_api.blocks_children_retrieve(block_id=id)
    # new_post(json.dumps(response))
    results = response['results']
    for result in results:
        type = result.get("type")
        text = result.get(type).get("rich_text")
        print(text)
        if (not text is None):
            # text是一个数组 如果text长度为0 说明是回车
            if (len(text) > 0):
                content = parse_text(text)
                if (type == "heading_2"):
                    post += "\n## "+content+"\n\n"
                if (type == "heading_3"):
                    post += "\n### "+content+"\n\n"
                elif (type == "to_do"):
                    post += "- [x] "+content+"\n"
                elif (type == "bulleted_list_item"):
                    post += "* "+content+"\n"
                elif (type == "numbered_list_item"):
                    post += "1. "+content+"\n"
                elif (type == "paragraph"):
                    post += content+"\n"
                elif (type == "code"):
                    language = result.get(type).get('language')
                    post+='```'+language+'\n'
                    post+=content+"\n"
                    post+='```'+'\n'

            else:
                post += "\n"
        elif (type == "image"):
            external = result.get(type).get("external")
            file = result.get(type).get("file")
            if (not external is None):
                url = external.get("url")
            elif (not file is None):
                url = file.get("url")
            post += "![]("+url+")\n"
    new_post(post,file)


if __name__ == "__main__":
    for id in ids:
        query(id)