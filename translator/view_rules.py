# convert_tool/translator/view_rules.py
from ..parser.resource_resolver import ResourceResolver
from .layout_rules import indent, apply_layout_modifiers

def translate_view(node, resolver):
    t = node["type"]
    attrs = node.get("attrs", {})

    if t == "TextView":
        text = resolver.resolve(attrs.get("text", "")) or ""
        size = resolver.parse_dimen_to_px(resolver.resolve(attrs.get("textSize", ""))) or None
        color_raw = resolver.resolve(attrs.get("textColor", "")) or None
        color_hex = resolver.android_color_to_flutter(color_raw) if color_raw else None
        style_parts = []
        if size is not None:
            style_parts.append(f"fontSize: {size}")
        if color_hex:
            style_parts.append(f"color: Color({color_hex})")
        style = f", style: TextStyle({', '.join(style_parts)})" if style_parts else ""
        body = f'Text("{escape_dart(text)}"{style})'
        return apply_layout_modifiers(body, attrs, resolver)

    if t == "Button":
        text = resolver.resolve(attrs.get("text", "")) or "Button"
        body = f'ElevatedButton(onPressed: (){{}}, child: Text("{escape_dart(text)}"))'
        return apply_layout_modifiers(body, attrs, resolver)

    if t == "EditText":
        hint = resolver.resolve(attrs.get("hint", "")) or ""
        body = f'TextField(decoration: InputDecoration(hintText: "{escape_dart(hint)}"))'
        return apply_layout_modifiers(body, attrs, resolver)

    if "RecyclerView" in t:
        # MVP: ListView.builder のダミー。後で itemBuilder を TaskItem に差し替える
        body = ("Expanded(child: ListView.builder("
                "itemCount: 20, itemBuilder: (ctx, i) => const SizedBox(height: 48)))")
        return apply_layout_modifiers(body, attrs, resolver)

    if t == "CheckBox" or t.endswith(".CheckBox"):
        body = "Checkbox(value: false, onChanged: (v){})"
        return apply_layout_modifiers(body, attrs, resolver)

    if t == "View":
        # weight=1 → Expanded のスペーサ（Row/Column 内で効く）
        w = attrs.get("layout_width"); h = attrs.get("layout_height")
        weight = attrs.get("layout_weight")
        if weight and (w == "0dp" or h == "0dp"):
            body = "Expanded(child: SizedBox.shrink())"
        else:
            body = "SizedBox.shrink()"
        return apply_layout_modifiers(body, attrs, resolver)

    # 未対応ビュー
    return apply_layout_modifiers("SizedBox.shrink()", attrs, resolver)


def escape_dart(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')
