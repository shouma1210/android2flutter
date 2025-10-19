# android2flutter/main.py
import argparse
import os
from .parser.xml_parser import parse_layout_xml
from .translator.generator import render_screen

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--xml",    required=True)
    parser.add_argument("--values")
    parser.add_argument("--java")
    parser.add_argument("--out",    required=True)
    parser.add_argument("--class", dest="class_name", required=True)  # ← 予約語回避
    args = parser.parse_args()

    ir, resolver = parse_layout_xml(args.xml, args.values)

    # 初期は空。Java があれば generator 側で抽出→上書きされる
    logic_map = {}

    # Dart を生成（ファイル書き込みは render_screen 内で実施）
    render_screen(
        ir=ir,
        resolver=resolver,
        logic_map=logic_map,
        java_path=args.java,
        output_path=args.out,
        class_name=args.class_name,
    )

if __name__ == "__main__":
    main()
