# convert_tool/translator/layout_rules.py
from ..parser.resource_resolver import ResourceResolver

def translate_layout(node, resolver):
    t = node["type"]
    attrs = node.get("attrs", {})
    children = node.get("children", [])

    dart_children = [translate_node(ch, resolver) for ch in children]
    children_list = ",\n".join(dart_children) if dart_children else ""

    if t == "LinearLayout":
        orientation = attrs.get("orientation", "vertical")
        body = (f"Row(children: [\n{indent(children_list)}\n])"
                if orientation == "horizontal"
                else f"Column(crossAxisAlignment: CrossAxisAlignment.start, children: [\n{indent(children_list)}\n])")
        return apply_layout_modifiers(body, attrs, resolver)

    if t == "FrameLayout":
        body = f"Stack(children: [\n{indent(children_list)}\n])"
        return apply_layout_modifiers(body, attrs, resolver)

    if t == "RelativeLayout":
        # MVP方針:
        # 1) alignParentBottom/centerHorizontal/marginBottom 等は子ウィジェット側で Align/Padding をかける
        # 2) layout_below は順序通りに Column へ並べ、"end" は Align(end) で近似
        positioned = []
        normal_children = []

        for ch, code in zip(children, dart_children):
            ca = ch.get("attrs", {})
            code2 = code

            # child-level bottom align
            if str(ca.get("layout_alignParentBottom", "")).lower() == "true":
                # centerHorizontal 判定
                if str(ca.get("layout_centerHorizontal", "")).lower() == "true":
                    code2 = f"Align(alignment: Alignment.bottomCenter, child: {code2})"
                else:
                    # alignParentEnd/Right を簡易サポート
                    if str(ca.get("layout_alignParentEnd", "")).lower() == "true":
                        code2 = f"Align(alignment: Alignment.bottomRight, child: {code2})"
                    else:
                        code2 = f"Align(alignment: Alignment.bottomCenter, child: {code2})"

                # marginBottom を Padding に
                mb = ca.get("layout_marginBottom")
                if mb:
                    mbv = resolver.parse_dimen_to_px(resolver.resolve(mb))
                    if mbv is not None:
                        code2 = f"Padding(padding: EdgeInsets.only(bottom: {mbv}), child: {code2})"
                positioned.append(code2)
                continue

            # layout_below → Column で順序近似（Flutterでは自然と下に来る）
            # gravity/end → Align(end)
            grav = ca.get("gravity")
            if grav and ("end" in grav or "right" in grav):
                code2 = f"Align(alignment: Alignment.centerRight, child: {code2})"

            normal_children.append(code2)

        # 上に自然順序（normal）、最前面にpositioned（Stack）で近似
        column = "Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [\n" + indent(",\n".join(normal_children)) + "\n])" if normal_children else "SizedBox()"
        if positioned:
            body = f"Stack(children: [\n{indent(column+',')}\n{indent(',\n'.join(positioned))}\n])"
        else:
            body = column

        return apply_layout_modifiers(body, attrs, resolver)

    # fallback
    body = f"Column(children: [\n{indent(children_list)}\n])"
    return apply_layout_modifiers(body, attrs, resolver)


def apply_layout_modifiers(body, attrs, resolver):
    # padding (all のみ簡易)
    padding = attrs.get("padding")
    if padding:
        p = resolver.parse_dimen_to_px(resolver.resolve(padding))
        if p is not None:
            body = f"Padding(padding: EdgeInsets.all({p}), child: {body})"

    # width/height
    w = attrs.get("layout_width"); h = attrs.get("layout_height")
    w = resolver.resolve(w) if w else None
    h = resolver.resolve(h) if h else None
    if w == "match_parent" or h == "match_parent":
        body = f"SizedBox.expand(child: {body})"  # Expanded は親がFlex必須。ここは SizedBox.expand に。

    # margin（よく使う bottom のみ簡易対応）
    mb = attrs.get("layout_marginBottom")
    if mb:
        mbv = resolver.parse_dimen_to_px(resolver.resolve(mb))
        if mbv is not None:
            body = f"Padding(padding: EdgeInsets.only(bottom: {mbv}), child: {body})"

    # gravity / layout_gravity
    grav = attrs.get("gravity") or attrs.get("layout_gravity")
    if grav:
        if "center" in grav and "vertical" not in grav and "horizontal" not in grav:
            body = f"Center(child: {body})"

    return body


def translate_node(node, resolver):
    t = node["type"]
    if t in ("LinearLayout", "FrameLayout", "RelativeLayout"):
        return translate_layout(node, resolver)
    from .view_rules import translate_view
    return translate_view(node, resolver)


def indent(s, n=2):
    pad = " " * n
    return "\n".join(pad + line for line in s.splitlines() if line.strip())
