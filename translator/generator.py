# android2flutter/translator/generator.py
import os
import re
from typing import Dict, List, Tuple, Set

from ..parser.xml_parser import parse_layout_xml as parse_xml
from ..translator.layout_rules import translate_node

# =============== 小ユーティリティ ===============
def _collect_needed_controllers(edittexts: List[Dict]) -> List[str]:
    need_user = False
    need_pass = False
    need_confirm = False
    for et in edittexts:
        lower = ((et.get("hint") or "") + (et.get("id") or "") + (et.get("inputType") or "")).lower()
        if "username" in lower or "user" in lower or "mail" in lower:
            need_user = True
        if "password" in lower or "textpassword" in lower:
            if "confirm" in lower:
                need_confirm = True
            else:
                need_pass = True
    ctrls = []
    if need_user: ctrls.append("_usernameController")
    if need_pass: ctrls.append("_passwordController")
    if need_confirm: ctrls.append("_confirmPasswordController")
    return ctrls

def _root_is_scrollview(widget_tree: str) -> bool:
    # 先頭トークンが ScrollView 系なら True
    return re.match(
        r'\s*(SingleChildScrollView|CustomScrollView|ListView|GridView|NestedScrollView)\s*\(',
        widget_tree
    ) is not None

def _contains_expanders(widget_tree: str) -> bool:
    s = widget_tree.lower()
    return ("sizedbox.expand(" in s) or ("expanded(" in s)

def _cleanup_empty_statements(text: str) -> str:
    # 連続セミコロンを1つに（;; -> ;）
    text = re.sub(r';\s*;+', ';', text)
    # 行がセミコロンだけの「空文」を削除
    text = re.sub(r'^\s*;\s*$', '', text, flags=re.MULTILINE)
    # ブロック閉じの直後に付いたセミコロンを除去
    text = re.sub(r'(\})\s*;\s*', r'\1', text)
    # 不要な空行を畳む
    text = re.sub(r'\n\s*\n+', '\n', text)
    return text.strip()

def _to_camel(s: str) -> str:
    parts = re.split(r'[_\W]+', s)
    parts = [p for p in parts if p]
    if not parts:
        return s
    head = parts[0].lower()
    tail = ''.join(p[:1].upper() + p[1:] for p in parts[1:])
    return head + tail


def _func_name_from_viewkey(key: str) -> str:
    c = _to_camel(key)
    return f"_on{c[:1].upper()}{c[1:]}Pressed"


def _aliases(key: str) -> Set[str]:
    base = key or ""
    camel = _to_camel(base)
    snake = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', camel).lower()
    return {base, base.lower(), camel, camel.lower(), snake, snake.lower()}


# =============== XML から EditText 情報抽出 ===============
def _collect_edittexts(ir: Dict) -> List[Dict]:
    """IR から EditText ノード（id, hint, inputType）を集める"""
    result = []

    def walk(n):
        t = n.get("type")
        attrs = n.get("attrs", {})
        if t == "EditText":
            item = {
                "id": (attrs.get("id") or "").replace("@+id/", "").replace("@id/", ""),
                "hint": attrs.get("hint") or "",
                "inputType": attrs.get("inputType") or "",
            }
            result.append(item)
        for ch in n.get("children", []):
            walk(ch)

    walk(ir)
    return result


# =============== Java → Dart 変換 ===============
def _intent_replacement(match) -> Tuple[str, str]:
    java_cls = match.group(1)
    dart_cls = "Converted" + java_cls.replace("Activity", "")
    line = f'Navigator.push(context, MaterialPageRoute(builder: (context) => const {dart_cls}()));'
    return line, dart_cls


def convert_java_logic_to_dart(java_block: str) -> Tuple[str, Set[str]]:
    imported: Set[str] = set()

    # ---- Intent -> Navigator (既存ロジック) ----
    def repl_intent(m):
        line, dart_cls = _intent_replacement(m)
        imported.add(dart_cls)
        return line

    java_block = re.sub(r'new\s+Intent\(.*?,\s*(\w+)Activity\.class\)', repl_intent, java_block)

    # ---- Toast -> SnackBar（既存）----
    java_block = re.sub(
        r'Toast\.makeText\(.*?,\s*"(.*?)",\s*Toast\.LENGTH_(?:SHORT|LONG)\)\.show\(\);',
        r'ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("\1")));',
        java_block,
    )

    java_block = re.sub(r'(\w+)\.equals\(([^)]+)\)', r'\1 == \2', java_block)

    # ---- 不要記述の削除（既存 + keep）----
    removals = [
        r'startActivity\(.*?\);\s*',                 # ← startActivity本体を丸ごと削除
        r'\bnew\s+',                                  # new
        r'\bIntent\s+\w+\s*=\s*',                     # Intent intent =
        r'\bBoolean\b|\bboolean\b|\bString\b|\bint\b|\bdouble\b',  # Java型トークン
        r'.*binding\..*;\s*',                         # ViewBinding行
    ]
    for pat in removals:
        java_block = re.sub(pat, '', java_block)

    # ---- Dart 仕様に軽整形（既存）----
    java_block = re.sub(r'\b(username|password|confirmPassword)\.isEmpty\(\)', r'\1.isEmpty', java_block)
    java_block = re.sub(r';\s*', ';\n', java_block)  # セミコロン後に改行

    # ---- Controller 取得の前置き ----
    # ★ confirmPassword を検知して前置き取得を追加
    needs_user    = re.search(r'\busername\b', java_block, re.I) is not None
    needs_pass    = re.search(r'\bpassword\b', java_block, re.I) is not None
    needs_confirm = re.search(r'\bconfirmPassword\b', java_block, re.I) is not None

    prefix = ""
    if needs_user:
        prefix += "final username = _usernameController.text.trim();\n"
    if needs_pass:
        prefix += "final password = _passwordController.text.trim();\n"
    if needs_confirm:
        prefix += "final confirmPassword = _confirmPasswordController.text.trim();\n"

    if prefix:
        java_block = (prefix + java_block).strip()

    java_block = re.sub(
    r'\b\w+\s*=\s*databaseHelper\.insert\w*\([^;]*\)\s*;',
    'final bool inserted = true; // TODO: implement DB insert',
    java_block, flags=re.I,
)
    java_block = re.sub(
        r'databaseHelper\.insert\w*\([^;]*\)\s*;',
        'final bool inserted = true; // TODO: implement DB insert',
        java_block, flags=re.I,
    )
     # ★ 残った `insert` という“変数名”を `inserted` に統一（関数名は先に消しているため安全側）
    java_block = re.sub(r'\binsert\b', 'inserted', java_block)

    # ======================================================
    # ここから「DBチェック（checkdetails）」の安全置換を強化
    # ======================================================

    # 1) 代入形:   (var|final|Boolean|boolean)? <name> = databaseHelper.check...(...);
    #    → `final bool <name> = true; // TODO: implement DB check`
    def _repl_db_assign(m):
        varname = m.group(1)
        return f"final bool {varname} = true; // TODO: implement DB check"

    java_block = re.sub(
        r'(?:final|var|Boolean|boolean)?\s*(\w+)\s*=\s*databaseHelper\.check\w*\([^;]*\)\s*;',
        _repl_db_assign,
        java_block,
        flags=re.IGNORECASE,
    )

    # 2) 条件式内: if (databaseHelper.check...(...)) → if (true) { /* TODO... */ ... }
    #    単体置換：呼び出し自体を `true /* TODO */` に置換
    java_block = re.sub(
        r'databaseHelper\.check\w*\([^;]*\)',
        r'true /* TODO: implement DB check */',
        java_block,
        flags=re.IGNORECASE,
    )

    # 3) 古い置換の副作用： "checkdetails = // TODO..." を作らないよう
    #    （過去の置換痕跡が残っている場合に備えた保険）
    java_block = re.sub(
        r'\bcheckdetails\s*=\s*//.*?$',
        r'// TODO: implement DB check\nfinal bool checkdetails = true;',
        java_block,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    # ---- セミコロン/空文の徹底掃除 ----
    java_block = _cleanup_empty_statements(java_block)

    return java_block, imported


def extract_click_handlers(java_code: str) -> Tuple[List[Tuple[str, str, str]], Set[str]]:
    handlers = []
    imports: Set[str] = set()
    pattern = re.compile(
        r'(\w+)\.setOnClickListener\s*\('
        r'(?:new\s+View\.OnClickListener\(\)\s*\{.*?onClick\(.*?\)\s*\{(.*?)\}\s*\}'
        r'|\s*\w+\s*->\s*\{(.*?)\}\s*)\);',
        re.DOTALL,
    )

    for m in pattern.finditer(java_code):
        view_sym = m.group(1)
        block = (m.group(2) or m.group(3) or "").strip()
        func_name = _func_name_from_viewkey(view_sym)
        dart_logic, needed_imports = convert_java_logic_to_dart(block)
        imports |= needed_imports
        handler_code = f"""
  void {func_name}(BuildContext context) {{
    {dart_logic if dart_logic else '// (no logic)'}
  }}
""".rstrip()
        handlers.append((view_sym, func_name, handler_code))

    return handlers, imports


# =============== Dart コード生成 ===============
def _build_imports_line(import_classes: Set[str], output_path: str) -> str:
    lines = ["import 'package:flutter/material.dart';"]
    base = os.path.basename(output_path)
    for cls in sorted(import_classes):
        fname = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', cls.replace("Converted", "")).lower()
        dart_file = f"converted_{fname}.dart"
        if dart_file != base:
            lines.append(f"import '{dart_file}';")
    return "\n".join(lines)


def _inject_controllers_into_widget_tree(widget_tree: str, edittexts: List[Dict]) -> str:
    for et in edittexts:
        hint = (et.get("hint") or "").strip().strip('"').strip("'")
        itype = et.get("inputType") or ""
        vid = et.get("id") or ""
        controller_name = None
        obscure = False
        lower = (hint + vid).lower()

        if "password" in lower or "textpassword" in itype.lower():
            # ★ confirm を優先判定：confirm を含むなら confirm 用のコントローラを割当て
            if "confirm" in lower:
                controller_name = "_confirmPasswordController"   # ★ 追加
            else:
                controller_name = "_passwordController"
            obscure = True
        elif "username" in lower or "user" in lower or "mail" in lower:
            controller_name = "_usernameController"
        else:
            continue

        pattern = re.compile(
            r'TextField\(\s*decoration:\s*InputDecoration\(\s*hintText:\s*"' + re.escape(hint) + r'"\s*\)\s*\)'
        )

        def _repl(_):
            if obscure:
                return f'TextField(controller: {controller_name}, obscureText: true, decoration: InputDecoration(hintText: "{hint}"))'
            else:
                return f'TextField(controller: {controller_name}, decoration: InputDecoration(hintText: "{hint}"))'

        widget_tree, _ = pattern.subn(_repl, widget_tree, count=1)
    return widget_tree


def _wrap_as_widget_class(class_name: str, widget_tree: str, handlers_code: str, need_stateful: bool, use_scrollview: bool, controllers: List[str]) -> str:
    # body 部分の共通生成（use_scrollview に応じて切替）
    if use_scrollview:
        body_expr = (
            "SingleChildScrollView("
            "child: ConstrainedBox("
            "  constraints: BoxConstraints(minWidth: double.infinity),"
            "  child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: ["
            f"{widget_tree}"
            "  ]),"
            "),)"
        )
    else:
        body_expr = widget_tree

    ctrl_fields  = "\n  ".join([f"final TextEditingController {c} = TextEditingController();" for c in controllers])
    ctrl_dispose = "\n    ".join([f"{c}.dispose();" for c in controllers])

    if need_stateful:
        return f"""class {class_name} extends StatefulWidget {{
  const {class_name}({{super.key}});

  @override
  State<{class_name}> createState() => _{class_name}State();
}}

class _{class_name}State extends State<{class_name}> {{
  {ctrl_fields if controllers else ''}

  @override
  void dispose() {{
    {ctrl_dispose if controllers else ''}
    super.dispose();
  }}

  @override
  Widget build(BuildContext context) {{
    return Scaffold(
      appBar: AppBar(title: const Text('{class_name}')),
      body: {body_expr},
    );
  }}

  // ===== Auto-Generated Handlers (State Internal) =====
{handlers_code.strip() if handlers_code.strip() else '// (no handlers)'}
}}
"""

def render_screen(ir, resolver, logic_map, java_path, output_path, class_name):
    print(f"[INFO] Generating Dart from XML+Java -> {output_path}")
    edittexts = _collect_edittexts(ir)

    handlers: List[Tuple[str, str, str]] = []
    import_classes: Set[str] = set()
    handlers_code = ""
    

    if java_path and os.path.exists(java_path):
        with open(java_path, "r", encoding="utf-8") as f:
            java_src = f.read()
        handlers, imports = extract_click_handlers(java_src)
        import_classes |= imports
        handlers_code = "\n\n".join(h[2] for h in handlers)
        logic_map = {a: f for (v, f, _) in handlers for a in _aliases(v)}
    else:
        print("[WARN] Java file not found, skipping logic conversion.")

    widget_tree = translate_node(ir, resolver, logic_map=logic_map)
    widget_tree = _inject_controllers_into_widget_tree(widget_tree, edittexts)
    controllers = _collect_needed_controllers(edittexts)
        # === ここで use_scrollview を決定 ===
    use_scroll = True
    if _root_is_scrollview(widget_tree) or _contains_expanders(widget_tree):
        use_scroll = False

   # need_stateful: username/password/confirm のいずれかがあれば true
    need_stateful = any(
        any(kw in (e.get("hint", "") + e.get("id", "")).lower() for kw in ("password", "username", "confirm"))
        for e in edittexts
    )

    # ↓ 第5引数に use_scroll を渡す
    widget_class_code = _wrap_as_widget_class(
        class_name, widget_tree, handlers_code, need_stateful, use_scroll, controllers
    )

    import_lines = _build_imports_line(import_classes, output_path)

    dart_code = f"""{import_lines}

{widget_class_code}
"""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(dart_code)

    print(f"[DONE] Generated Dart: {output_path}")
