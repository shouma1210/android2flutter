# android2flutter/main.py
import argparse
import os
import sys

from .parser.xml_parser import parse_layout_xml
from .translator.generator import render_screen

def main():
    parser = argparse.ArgumentParser(
        prog="python -m android2flutter.main",
        description=(
            "Convert Android XML + Java logic into Flutter Dart code.\n"
            "You can pass either --java (single file) or --java-root (scan entire src)."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--xml", required=True, help="Path to layout XML (e.g. res/layout/activity_main.xml)")
    parser.add_argument("--values", help="Path to res/values directory for resource resolution")
    parser.add_argument("--java", help="Path to a single Java file for logic extraction")
    parser.add_argument("--java-root", dest="java_root", help="Path to Java source root (e.g. app/src/main/java)")
    parser.add_argument("--out", required=True, help="Output Dart file path (e.g. Converted/converted_main.dart)")
    parser.add_argument("--class", dest="class_name", required=True, help="Output Dart class name (e.g. ConvertedMain)")

    args = parser.parse_args()

    # 優先順位: --java-root > --java
    java_path = args.java_root or args.java
    if args.java_root and args.java:
        print("[INFO] Both --java and --java-root provided; using --java-root.")

    print(f"[CONFIG] xml= {args.xml}")
    print(f"[CONFIG] values= {args.values or '<none>'}")
    print(f"[CONFIG] java_path= {java_path or '<none>'}")
    print(f"[CONFIG] out= {args.out}")
    print(f"[CONFIG] class= {args.class_name}")

    try:
        ir, resolver = parse_layout_xml(args.xml, args.values)
    except Exception as e:
        print(f"[ERROR] Failed to parse XML: {e}")
        sys.exit(1)

    logic_map = {}

    try:
        render_screen(
            ir=ir,
            resolver=resolver,
            logic_map=logic_map,
            java_path=java_path,
            output_path=args.out,
            class_name=args.class_name,
        )
    except Exception as e:
        print(f"[ERROR] Generation failed: {e}")
        sys.exit(2)

if __name__ == "__main__":
    main()

