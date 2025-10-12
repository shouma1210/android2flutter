# android2flutter/translator/layout_rules.py
from ..parser.resource_resolver import ResourceResolver
from ..utils import indent, apply_layout_modifiers


def translate_layout(node, resolver):
    t = node["type"]
    attrs = node.get("attrs", {})
    children = node.get("children", [])

    # 再帰的に子ノードをDart変換
    dart_children = [translate_node(ch, resolver) for ch in children]
    children_list = ",\n".join(dart_children) if dart_children else ""

    # ========== LinearLayout ==========
    if t == "LinearLayout":
        orientation = attrs.get("orientation", "vertical")
        body = (
            f"Row(children: [\n{indent(children_list)}\n])"
            if orientation == "horizontal"
            else f"Column(crossAxisAlignment: CrossAxisAlignment.start, children: [\n{indent(children_list)}\n])"
        )
        return apply_layout_modifiers(body, attrs, resolver)

    # ========== FrameLayout ==========
    if t == "FrameLayout":
        body = f"Stack(children: [\n{indent(children_list)}\n])"
        return apply_layout_modifiers(body, attrs, resolver)

    # ========== RelativeLayout ==========
    if t == "RelativeLayout":
        positioned = []
        normal_children = []
        for ch, code in zip(children, dart_children):
            ca = ch.get("attrs", {})
            code2 = code

            # 親ボトム固定
            if str(ca.get("layout_alignParentBottom", "")).lower() == "true":
                if str(ca.get("layout_centerHorizontal", "")).lower() == "true":
                    code2 = f"Align(alignment: Alignment.bottomCenter, child: {code2})"
                elif str(ca.get("layout_alignParentEnd", "")).lower() == "true":
                    code2 = f"Align(alignment: Alignment.bottomRight, child: {code2})"
                else:
                    code2 = f"Align(alignment: Alignment.bottomCenter, child: {code2})"
                mb = ca.get("layout_marginBottom")
                if mb:
                    mbv = resolver.parse_dimen_to_px(resolver.resolve(mb))
                    if mbv:
                        code2 = f"Padding(padding: EdgeInsets.only(bottom: {mbv}), child: {code2})"
                positioned.append(code2)
                continue

            grav = ca.get("gravity")
            if grav and ("end" in grav or "right" in grav):
                code2 = f"Align(alignment: Alignment.centerRight, child: {code2})"

            normal_children.append(code2)

        column = (
            "Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [\n"
            + indent(",\n".join(normal_children))
            + "\n])"
            if normal_children
            else "SizedBox()"
        )
        if positioned:
            body = f"Stack(children: [\n{indent(column+',')}\n{indent(',\n'.join(positioned))}\n])"
        else:
            body = column
        return apply_layout_modifiers(body, attrs, resolver)

    # ========== ConstraintLayout ==========
    if t == "ConstraintLayout":
        positioned = []
        normal_children = []
        for ch, code in zip(children, dart_children):
            ca = ch.get("attrs", {})
            code2 = code

            # bottom_toBottomOf=parent → 下寄せ
            if ca.get("layout_constraintBottom_toBottomOf") == "parent":
                align = "Alignment.bottomCenter"
                if (
                    ca.get("layout_constraintEnd_toEndOf") == "parent"
                    and ca.get("layout_constraintStart_toStartOf") == "parent"
                ):
                    align = "Alignment.bottomCenter"
                elif ca.get("layout_constraintEnd_toEndOf") == "parent":
                    align = "Alignment.bottomRight"
                elif ca.get("layout_constraintStart_toStartOf") == "parent":
                    align = "Alignment.bottomLeft"
                code2 = f"Align(alignment: {align}, child: {code2})"
                mb = ca.get("layout_marginBottom")
                if mb:
                    mbv = resolver.parse_dimen_to_px(resolver.resolve(mb))
                    if mbv:
                        code2 = f"Padding(padding: EdgeInsets.only(bottom: {mbv}), child: {code2})"
                positioned.append(code2)
                continue

            # 中央寄せ
            if (
                ca.get("layout_constraintStart_toStartOf") == "parent"
                and ca.get("layout_constraintEnd_toEndOf") == "parent"
            ):
                code2 = f"Align(alignment: Alignment.center, child: {code2})"

            normal_children.append(code2)

        column = (
            "Column(crossAxisAlignment: CrossAxisAlignment.stretch, "
            "children: [\n" + indent(",\n".join(normal_children)) + "\n])"
            if normal_children
            else "SizedBox()"
        )
        if positioned:
            body = f"Stack(children: [\n{indent(column+',')}\n{indent(',\n'.join(positioned))}\n])"
        else:
            body = column
        return apply_layout_modifiers(body, attrs, resolver)

    # fallback
    body = f"Column(children: [\n{indent(children_list)}\n])"
    return apply_layout_modifiers(body, attrs, resolver)


def translate_node(node, resolver):
    t = node["type"]

    # "androidx.constraintlayout.widget.ConstraintLayout" のような完全修飾タグも拾う
    if (
        "LinearLayout" in t
        or "FrameLayout" in t
        or "RelativeLayout" in t
        or "ConstraintLayout" in t
    ):
        return translate_layout(node, resolver)

    from .view_rules import translate_view
    return translate_view(node, resolver)