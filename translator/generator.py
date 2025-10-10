# convert_tool/translator/generator.py
from jinja2 import Environment, FileSystemLoader
import os

def render_screen(widget_tree_code, class_name="ConvertedScreen"):
    env = Environment(
        loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "..", "templates")),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    tpl = env.get_template("screen.dart.j2")
    return tpl.render(class_name=class_name, widget_tree=widget_tree_code)
