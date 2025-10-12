# android2flutter/utils.py
def indent(text: str, spaces: int = 2) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line.strip() else line for line in text.splitlines())

def apply_layout_modifiers(body: str, attrs: dict, resolver) -> str:
    # padding (all)
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
        body = f"SizedBox.expand(child: {body})"

    # margin (bottom のみ簡易)
    mb = attrs.get("layout_marginBottom")
    if mb:
        mbv = resolver.parse_dimen_to_px(resolver.resolve(mb))
        if mbv is not None:
            body = f"Padding(padding: EdgeInsets.only(bottom: {mbv}), child: {body})"

    # gravity / layout_gravity
    grav = attrs.get("gravity") or attrs.get("layout_gravity")
    if grav and ("center" in grav) and ("vertical" not in grav) and ("horizontal" not in grav):
        body = f"Center(child: {body})"

    return body
