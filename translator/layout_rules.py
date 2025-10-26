# android2flutter/translator/layout_rules.py
from ..parser.resource_resolver import ResourceResolver
from ..utils import indent, apply_layout_modifiers

def _wrap_match_parent_for_linear(child_code: str, child_attrs: dict, parent_orientation: str) -> str:
    """LinearLayout 配下の子の match_parent を Expanded / width∞ で表現する"""
    w = (child_attrs.get("layout_width") or "").lower()
    h = (child_attrs.get("layout_height") or "").lower()
    code = child_code

    if parent_orientation == "vertical":
        if h == "match_parent":
            code = f"Expanded(child: {code})"
        if w == "match_parent":
            code = f"SizedBox(width: double.infinity, child: {code})"
    else:  # horizontal
        if w == "match_parent":
            code = f"Expanded(child: {code})"
        if h == "match_parent":
            code = f"SizedBox(height: double.infinity, child: {code})"
    return code

def _axes_from_gravity_for_linear(gravity: str, orientation: str):
    """gravity を Flutter の main/cross axis に落とす。シンプルに center/horizontal/vertical を扱う。"""
    g = (gravity or "").lower()
    main = "MainAxisAlignment.start"
    cross = "CrossAxisAlignment.start"

    if "center" in g:
        if orientation == "vertical":
            main = "MainAxisAlignment.center" if ("center_vertical" in g or "center" in g) else main
            cross = "CrossAxisAlignment.center" if ("center_horizontal" in g or "center" in g) else cross
        else:
            main = "MainAxisAlignment.center" if ("center_horizontal" in g or "center" in g) else main
            cross = "CrossAxisAlignment.center" if ("center_vertical" in g or "center" in g) else cross

    if "end" in g or "right" in g:
        if orientation == "vertical":
            cross = "CrossAxisAlignment.end"
        else:
            main = "MainAxisAlignment.end"

    if "start" in g or "left" in g:
        if orientation == "vertical":
            cross = "CrossAxisAlignment.start"
        else:
            main = "MainAxisAlignment.start"

    return main, cross

def translate_layout(node, resolver, logic_map=None):
    """
    ViewGroup を Flutter ウィジェットへ。
    logic_map: view_id → handler 名
    """
    t = node["type"]
    attrs = node.get("attrs", {}) or {}
    children = node.get("children", []) or []

    # ========== LinearLayout ==========
    if t == "LinearLayout":
        orientation = attrs.get("orientation", "vertical").lower()

        dart_children_list = []
        for ch in children:
            child_code = translate_node(ch, resolver, logic_map=logic_map)
            child_attrs = ch.get("attrs", {}) or {}
            child_code = _wrap_match_parent_for_linear(child_code, child_attrs, orientation)
            dart_children_list.append(child_code)

        children_joined = ",\n".join(dart_children_list)
        main, cross = _axes_from_gravity_for_linear(attrs.get("gravity", ""), orientation)

        if orientation == "horizontal":
            body = (
                f"Row(mainAxisAlignment: {main}, crossAxisAlignment: {cross}, children: [\n"
                f"{indent(children_joined)}\n])"
            )
        else:
            body = (
                f"Column(mainAxisAlignment: {main}, crossAxisAlignment: {cross}, children: [\n"
                f"{indent(children_joined)}\n])"
            )
        return apply_layout_modifiers(body, attrs, resolver)

    # ========== FrameLayout ==========
    if t == "FrameLayout":
        dart_children = [translate_node(ch, resolver, logic_map=logic_map) for ch in children]
        body = f"Stack(children: [\n{indent(',\n'.join(dart_children))}\n])"
        return apply_layout_modifiers(body, attrs, resolver)

    # ========== RelativeLayout ==========
    if t == "RelativeLayout":
        dart_children = [translate_node(ch, resolver, logic_map=logic_map) for ch in children]
        body = f"Stack(children: [\n{indent(',\n'.join(dart_children))}\n])"
        return apply_layout_modifiers(body, attrs, resolver)

    # ========== ConstraintLayout ==========
    if t == "ConstraintLayout":
        dart_children = [translate_node(ch, resolver, logic_map=logic_map) for ch in children]
        body = f"Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [\n{indent(',\n'.join(dart_children))}\n])"
        return apply_layout_modifiers(body, attrs, resolver)

    # fallback
    dart_children = [translate_node(ch, resolver, logic_map=logic_map) for ch in children]
    body = f"Column(children: [\n{indent(',\n'.join(dart_children))}\n])"
    return apply_layout_modifiers(body, attrs, resolver)

def translate_node(node: dict, resolver, logic_map=None):
    t = (node.get("type") or "")
    attrs = node.get("attrs", {}) or {}
    children = node.get("children", []) or []

    # === 追加: ConstraintLayout を Column にフォールバック ===
    if t in ("androidx.constraintlayout.widget.ConstraintLayout", "ConstraintLayout"):
        child_widgets = [translate_node(ch, resolver, logic_map=logic_map) for ch in children]
        body = "Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [\n  " \
               + ",\n  ".join(child_widgets) + "\n])"
        return apply_layout_modifiers(body, attrs, resolver)
    
    if t in ("LinearLayout", "FrameLayout", "RelativeLayout", "ConstraintLayout"):
        return translate_layout(node, resolver, logic_map)
    from .view_rules import translate_view
    return translate_view(node, resolver, logic_map)
