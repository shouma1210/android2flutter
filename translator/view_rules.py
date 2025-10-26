from ..parser.resource_resolver import ResourceResolver
from ..utils import indent, apply_layout_modifiers, escape_dart

# --- helpers -------------------------------------------------

def _id_base(v: str) -> str:
    if not v:
        return ""
    return v.split("/")[-1]

def _to_camel(s: str) -> str:
    if not s:
        return s
    parts = s.replace('-', '_').split('_')
    return parts[0] + ''.join(p.capitalize() for p in parts[1:])

def _to_snake(s: str) -> str:
    if not s:
        return s
    out = []
    for i, ch in enumerate(s):
        if ch.isupper() and i > 0 and s[i-1].islower():
            out.append('_')
        out.append(ch.lower())
    return ''.join(out)

def _fallback_handler_name(xml_id: str) -> str:
    # 例: btnLogin -> _onBtnLoginPressed
    if not xml_id:
        return "_onUnknownPressed"
    head = xml_id[0].upper() + xml_id[1:]
    return f"_on{head}Pressed"

def _find_handler(logic_map: dict, xml_id: str):
    if not xml_id:
        return None
    cands = {xml_id, xml_id.lower(), xml_id.capitalize(), _to_camel(xml_id), _to_snake(xml_id)}
    for k in cands:
        if k in (logic_map or {}):
            return logic_map[k]
    return None

def _text_style(attrs: dict, resolver: ResourceResolver) -> str:
    size = resolver.parse_dimen_to_px(resolver.resolve(attrs.get("textSize", ""))) or None
    color_raw = resolver.resolve(attrs.get("textColor", "")) or None
    color_hex = resolver.android_color_to_flutter(color_raw) if color_raw else None
    style_parts = []
    if size is not None:
        style_parts.append(f"fontSize: {size}")
    if color_hex:
        style_parts.append(f"color: Color({color_hex})")
    return f", style: TextStyle({', '.join(style_parts)})" if style_parts else ""

# --- main ----------------------------------------------------

def translate_view(node: dict, resolver: ResourceResolver, logic_map=None) -> str:
    """
    単一 View を Flutter ウィジェットへ変換（dict-IR 専用）。
    logic_map: {view_id -> handler_name}
    """
    logic_map = (logic_map or {})
    t = (node.get("type") or "")
    attrs = node.get("attrs", {}) or {}
    children = node.get("children", []) or []

    # ================== Button 系（先に処理） ==================
    # Button / AppCompatButton / MaterialButton など末尾が "Button"
    if t.lower().endswith("button") or t == "Button":
        raw_id = attrs.get("id") or ""
        xml_id = _id_base(raw_id)
        label_raw = attrs.get("text", "")
        label = resolver.resolve(label_raw) or "Button"

        handler_name = _find_handler(logic_map, xml_id) or _fallback_handler_name(xml_id)
        body = f'ElevatedButton(onPressed: () => {handler_name}(context), child: Text("{escape_dart(label)}"))'
        return apply_layout_modifiers(body, attrs, resolver)

    # ================== TextInputLayout（親） ==================
    if t.endswith("TextInputLayout") or t == "com.google.android.material.textfield.TextInputLayout":
        parent_hint = resolver.resolve(attrs.get("hint", "")) or ""
        child = None
        for ch in children:
            ct = ch.get("type")
            if ct in ("TextInputEditText", "EditText", "AppCompatEditText", "com.google.android.material.textfield.TextInputEditText"):
                child = ch
                break

        hint = parent_hint
        obscure = False
        if child:
            cattr = child.get("attrs", {}) or {}
            hint = resolver.resolve(cattr.get("hint", "")) or hint
            itype = (cattr.get("inputType") or "").lower()
            if "textpassword" in itype or "password" in (hint or "").lower():
                obscure = True

        dec = f'InputDecoration(hintText: "{escape_dart(hint)}")' if hint else "null"
        body = f'TextField(decoration: {dec}{", obscureText: true" if obscure else ""})'
        return apply_layout_modifiers(body, attrs, resolver)

    # ================== TextView ==================
    if t == "TextView":
        xml_id = _id_base(attrs.get("id", ""))
        handler_name = _find_handler(logic_map, xml_id)

        text = resolver.resolve(attrs.get("text", "")) or ""
        body = f'Text("{escape_dart(text)}"{_text_style(attrs, resolver)})'

        # XML の android:onClick を拾ってフォールバック名へ接続
        xml_onclick = attrs.get("onClick") or attrs.get("android:onClick")
        if handler_name:
            body = f'InkWell(onTap: () => {handler_name}(context), child: {body})'
        elif xml_onclick:
            camel = _to_camel(xml_id)
            fallback = f"_on{camel[:1].upper()}{camel[1:]}Pressed" if camel else "_onUnknownPressed"
            body = f'InkWell(onTap: () => {fallback}(context), child: {body})'
        elif (attrs.get("clickable", "") or "").lower() == "true":
            # clickable=true だが Java 側で検出できなかった場合は見た目だけボタン化（論理は null）
            body = f'TextButton(onPressed: null, child: {body})'

        return apply_layout_modifiers(body, attrs, resolver)

    # ================== EditText / TextInputEditText ==================
    if t in ("EditText", "AppCompatEditText", "TextInputEditText", "com.google.android.material.textfield.TextInputEditText"):
        hint = resolver.resolve(attrs.get("hint", "")) or ""
        input_type = (attrs.get("inputType") or "").lower()
        obscure = ("textpassword" in input_type) or ("password" in hint.lower())
        dec = f'InputDecoration(hintText: "{escape_dart(hint)}")' if hint else "null"
        parts = [f"decoration: {dec}"]
        if obscure:
            parts.append("obscureText: true")
        body = f"TextField({', '.join(parts)})"
        return apply_layout_modifiers(body, attrs, resolver)

    # ================== ImageView（簡易） ==================
    if t.endswith("ImageView"):
        # 画像リソースは省略（TODO）
        return apply_layout_modifiers("/* TODO: translate ImageView */ SizedBox()", attrs, resolver)

    # ================== fallback ==================
    return apply_layout_modifiers(f"/* TODO: translate {t} */ SizedBox()", attrs, resolver)
