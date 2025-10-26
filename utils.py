# android2flutter/utils.py
import re

def indent(text: str, spaces: int = 2) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line.strip() else line for line in text.splitlines())

def escape_dart(s: str) -> str:
    """
    Dart のダブルクォート文字列で安全に使えるよう最低限のエスケープを行う。
    - \ -> \\
    - " -> \"
    - 改行 -> \n（CRLF/CR は LF に正規化）
    """
    if s is None:
        return ""
    if isinstance(s, bytes):
        s = s.decode("utf-8", errors="ignore")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\\", "\\\\")
    s = s.replace('"', '\\"')
    s = s.replace("\n", "\\n")
    return s

def apply_layout_modifiers(body: str, attrs: dict, resolver) -> str:
    """
    レイアウト属性（padding / margin / gravity の一部）をウィジェットに反映。
    match_parent の処理は layout_rules 側（Expanded 等）で扱う。
    """
    def _res(v):
        return resolver.resolve(v) if (resolver and v is not None) else v
    def _px(v):
        return resolver.parse_dimen_to_px(_res(v)) if (resolver and v is not None) else None

    # padding（all）
    padding = attrs.get("padding")
    if padding:
        p = _px(padding)
        if p is not None:
            body = f"Padding(padding: EdgeInsets.all({p}), child: {body})"

    # padding 個別
    for side_attr, side_key in [
        ("paddingLeft", "left"),
        ("paddingRight", "right"),
        ("paddingTop", "top"),
        ("paddingBottom", "bottom"),
        ("paddingStart", "left"),
        ("paddingEnd", "right"),
    ]:
        val = attrs.get(side_attr)
        if val:
            px = _px(val)
            if px is not None:
                body = f"Padding(padding: EdgeInsets.only({side_key}: {px}), child: {body})"

    # margin（例：bottom のみ簡易対応）
    mb = attrs.get("layout_marginBottom")
    if mb:
        mbv = _px(mb)
        if mbv is not None:
            body = f"Padding(padding: EdgeInsets.only(bottom: {mbv}), child: {body})"

    # gravity / layout_gravity（全体センターのみ簡易対応）
    grav = attrs.get("gravity") or attrs.get("layout_gravity")
    if grav:
        g = str(grav).lower()
        if "center" in g and "vertical" not in g and "horizontal" not in g:
            body = f"Center(child: {body})"

    return body
