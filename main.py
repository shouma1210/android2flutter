#android2flutter/main.py
import argparse, json, os, sys
sys.path.append(os.path.dirname(__file__))  # ← 追加！

from android2flutter.parser.xml_parser import parse_layout_xml
from android2flutter.translator.layout_rules import translate_node
from android2flutter.translator.generator import render_screen



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", required=True, help="res/layout/xxx.xml")
    ap.add_argument("--values", required=False, help="res/values dir")
    ap.add_argument("--out", required=True, help="output dart file path")
    ap.add_argument("--class", dest="cls", default="ConvertedScreen", help="Dart class name")
    args = ap.parse_args()

    ir, resolver = parse_layout_xml(args.xml, args.values)
    if resolver:
        # IR の attrs を参照解決（簡易：トップダウン一括）
        def resolve_attrs(node):
            attrs = node.get("attrs", {})
            for k, v in list(attrs.items()):
                attrs[k] = resolver.resolve(v)
            for ch in node.get("children", []):
                resolve_attrs(ch)
        resolve_attrs(ir)

    dart_tree = translate_node(ir, resolver)
    dart_code = render_screen(dart_tree, class_name=args.cls)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(dart_code)

    # レポート（超簡易：ノード統計）
    def count_nodes(n):
        c = 1
        for ch in n.get("children", []):
            c += count_nodes(ch)
        return c
    report = {
        "input_xml": args.xml,
        "node_count": count_nodes(ir),
        "class_name": args.cls,
        "status": "ok"
    }
    with open(args.out + ".report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[OK] Generated: {args.out}")

if __name__ == "__main__":
    main()