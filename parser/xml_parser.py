# convert_tool/parser/xml_parser.py
from lxml import etree
from .resource_resolver import ResourceResolver

import os


ANDROID_NS = "{http://schemas.android.com/apk/res/android}"

def _attr(el, name, default=None):
    return el.get(ANDROID_NS + name, default)

def _parse_node(el):
    node = {
        "type": el.tag.split('}')[-1],   # e.g., LinearLayout / TextView
        "attrs": {},
        "children": []
    }
    # すべてのandroid:属性を attrs に詰める
    for k, v in el.attrib.items():
        if k.startswith(ANDROID_NS):
            node["attrs"][k.split('}')[-1]] = v
    # 子
    for child in el:
        if isinstance(child.tag, str):  # コメント等スキップ
            node["children"].append(_parse_node(child))
    return node

def parse_layout_xml(xml_path, values_dir=None):
    """
    xml_path: res/layout/xxx.xml
    values_dir: res/values ディレクトリ
    return: (ir: dict, resolver: ResourceResolver)
    """
    tree = etree.parse(xml_path)
    root = tree.getroot()
    ir = _parse_node(root)
    resolver = ResourceResolver(values_dir) if values_dir else None
    return ir, resolver
