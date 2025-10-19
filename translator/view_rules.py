# android2flutter/translator/view_rules.py
import re
from ..utils import apply_layout_modifiers

def _id_base(raw_id: str) -> str:
    if not raw_id:
        return ""
    return raw_id.split("/")[-1]  # @+id/xxx -> xxx

def _to_camel(s: str) -> str:
    # snake_case / mixed -> camelCase
    if not s:
        return s
    parts = re.split(r'[_\W]+', s)
    if not parts:
        return s
    head = parts[0]
    tail = ''.join(p[:1].upper() + p[1:] for p in parts[1:] if p)
    return head if not tail else head + tail

def _handler_from_logic_map(raw_id: str, logic_map=None):
    """
    logic_map に登録がある場合のみ、`() => func(context)` を返す。
    ※未登録なら None を返し、ハンドラは付与しない。
    """
    logic_map = logic_map or {}
    base = _id_base(raw_id)
    if not base:
        return None
    camel = _to_camel(base)                  # login_button -> loginButton
    # キーのゆらぎ対応（別所で alias を作る実装もあるが、ここでは代表的な形を確認）
    for key in {base, base.lower(), camel, camel.lower()}:
        if key in logic_map:
            return f"() => {logic_map[key]}(context)"
    return None

def translate_view(node, resolver, logic_map=None):
    t = node["type"]
    attrs = node.get("attrs", {})
    raw_id = attrs.get("id", "")

    # --- TextView ---
    if t == "TextView":
        text = resolver.resolve(attrs.get("text", "")) or ""
        body = f'Text("{text}", style: const TextStyle(fontSize: 16))'

        # ★ 重要：logic_map にあるときだけ InkWell を付与
        handler = _handler_from_logic_map(raw_id, logic_map)
        if handler:
            body = f'InkWell(onTap: {handler}, child: {body})'
        return apply_layout_modifiers(body, attrs, resolver)

    # --- EditText ---
    if t == "EditText":
        hint = resolver.resolve(attrs.get("hint", "")) or ""
        body = f'TextField(decoration: InputDecoration(hintText: "{hint}"))'
        return apply_layout_modifiers(body, attrs, resolver)

    # --- Button ---
    if t == "Button":
        text = resolver.resolve(attrs.get("text", "")) or "Button"
        # ★ 重要：logic_map にあるときだけ onPressed を有効化。なければ null（無効）
        handler = _handler_from_logic_map(raw_id, logic_map) or "null"
        body = f'ElevatedButton(onPressed: {handler}, child: Text("{text}"))'
        return apply_layout_modifiers(body, attrs, resolver)

    # --- ImageView ---
    if t == "ImageView":
        src = resolver.resolve(attrs.get("src", "")) or ""
        return f'Image.asset("{src}")'

    # --- LinearLayout（簡易）---
    if t == "LinearLayout":
        orientation = attrs.get("orientation", "vertical")
        children = [translate_view(c, resolver, logic_map=logic_map) for c in node.get("children", [])]
        joined = ", ".join(children)
        layout = "Column" if orientation == "vertical" else "Row"
        return f'{layout}(children: [{joined}])'

    # --- ScrollView 系 ---
    if t.endswith("ScrollView"):
        child = (
            translate_view(node["children"][0], resolver, logic_map=logic_map)
            if node.get("children") else "SizedBox()"
        )
        return f'SingleChildScrollView(child: {child})'

    # --- その他の ViewGroup（簡易フォールバック）---
    children = [translate_view(c, resolver, logic_map=logic_map) for c in node.get("children", [])]
    joined = ", ".join(children)
    return f'Column(children: [{joined}])'
