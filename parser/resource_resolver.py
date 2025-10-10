# convert_tool/parser/resource_resolver.py
import os
from lxml import etree

class ResourceResolver:
    def __init__(self, values_dir):
        self.colors = {}
        self.strings = {}
        self.dimens = {}
        if values_dir and os.path.isdir(values_dir):
            self._load_values(values_dir)

    def _load_values(self, values_dir):
        for fn in os.listdir(values_dir):
            if not fn.endswith(".xml"): continue
            path = os.path.join(values_dir, fn)
            try:
                root = etree.parse(path).getroot()
            except Exception:
                continue
            for child in root:
                tag = child.tag
                name = child.get("name")
                if not name: continue
                text = (child.text or "").strip()
                if tag == "color":
                    # #AARRGGBB / #RRGGBB のどちらでも来る想定
                    self.colors[name] = text
                elif tag == "string":
                    self.strings[name] = text
                elif tag == "dimen":
                    # "16dp" / "14sp" 等
                    self.dimens[name] = text

    def resolve(self, val):
        """ @color/primary → #RRGGBB / @dimen/margin → '16dp' ... """
        if not isinstance(val, str): return val
        if val.startswith("@color/"):
            key = val.split("/", 1)[1]
            return self.colors.get(key, val)
        if val.startswith("@string/"):
            key = val.split("/", 1)[1]
            return self.strings.get(key, val)
        if val.startswith("@dimen/"):
            key = val.split("/", 1)[1]
            return self.dimens.get(key, val)
        return val

    @staticmethod
    def parse_dimen_to_px(d):
        """ '16dp' / '14sp' / '24px' -> float に。簡易：dp,sp → px 同値扱い（MVP）"""
        if not isinstance(d, str): return d
        s = d.strip().lower()
        for suf in ("dp", "sp", "px"):
            if s.endswith(suf):
                try:
                    return float(s[:-len(suf)])
                except:
                    return None
        try:
            return float(s)
        except:
            return None

    @staticmethod
    def android_color_to_flutter(c):
        """
        '#RRGGBB' or '#AARRGGBB' → '0xAARRGGBB'
        Flutterは ARGB hex を Color(0xAARRGGBB) で使う。
        """
        if not isinstance(c, str): return None
        s = c.strip()
        if not s.startswith("#"): return None
        hexv = s[1:]
        if len(hexv) == 6:  # RRGGBB
            return "0xFF" + hexv.upper()
        if len(hexv) == 8:  # AARRGGBB
            return "0x" + hexv.upper()
        return None
