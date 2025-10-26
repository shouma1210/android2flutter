# android2flutter/translator/generator.py
import os
import re
from typing import Dict, List, Tuple, Set, Optional

from ..translator.layout_rules import translate_node

# ===== ターゲット式（左辺）に findViewById(...) を許容する共通パターン =====
TARGET = r'(?:[A-Za-z_][\w\.\(\)\s]*|findViewById\(\s*R\.id\.\w+\s*\))'

# =============================================================
# Small utilities
# =============================================================

def _dart_file_from_class(cls: str) -> str:
    """Convert PascalCase class name to snake_case Dart filename."""
    out = []
    for i, ch in enumerate(cls):
        if ch.isupper() and i > 0 and (cls[i - 1].islower() or (i + 1 < len(cls) and cls[i + 1].islower())):
            out.append('_')
        out.append(ch.lower())
    return ''.join(out) + '.dart'

def _collect_button_ids(ir: Dict) -> List[str]:
    ids: List[str] = []

    def walk(n: Dict):
        t = (n.get("type") or "").lower()
        attrs = n.get("attrs", {}) or {}
        if t.endswith("button") or t == "button":
            rid = (attrs.get("id") or "")
            rid = rid.split("/")[-1] if rid else ""
            if rid:
                ids.append(rid)
        for ch in n.get("children", []) or []:
            walk(ch)

    walk(ir)
    return ids

def _to_camel(s: str) -> str:
    parts = re.split(r'[_\W]+', s)
    parts = [p for p in parts if p]
    if not parts:
        return s
    head = parts[0].lower()
    tail = ''.join(p[:1].upper() + p[1:] for p in parts[1:])
    return head + tail

def _camel_to_snake(name: str) -> str:
    s1 = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)
    return s1.replace('__', '_').lower()

def _func_name_from_viewkey(key: str) -> str:
    c = _to_camel(key)
    # ❌ もともと {c[1]} になっており 1 文字だけになっていた
    return f"_on{c[:1].upper()}{c[1:]}Pressed" if c else "_onUnknownPressed"


def _aliases(key: str) -> Set[str]:
    base = key or ""
    camel = _to_camel(base)
    snake = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', camel).lower()
    return {base, base.lower(), camel, camel.lower(), snake, snake.lower()}

def _id_base(raw_id: str) -> str:
    if not raw_id:
        return ""
    return raw_id.split("/")[-1]  # @+id/login_button -> login_button

def _collect_ids_from_ir(ir: Dict) -> Set[str]:
    ids: Set[str] = set()
    def walk(n: Dict):
        a = n.get("attrs", {}) or {}
        rid = a.get("id")
        if rid:
            ids.add(_id_base(rid))
        for c in n.get("children", []) or []:
            walk(c)
    walk(ir)
    return ids

def _id_aliases(s: str) -> Set[str]:
    camel = _to_camel(s)
    snake = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', camel).lower()
    return {s, s.lower(), camel, camel.lower(), snake, snake.lower()}

def _find_import_classes(dart_text: str) -> Set[str]:
    # 生成したハンドラ内のクラス（コンストラクタ呼び出し）を検出
    classes: Set[str] = set()
    for m in re.finditer(r'\b([A-Z][A-Za-z0-9_]*)\s*\(', dart_text):
        classes.add(m.group(1))
    return classes

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
    ctrls: List[str] = []
    if need_user: ctrls.append("_usernameController")
    if need_pass: ctrls.append("_passwordController")
    if need_confirm: ctrls.append("_confirmPasswordController")
    return ctrls

def _root_is_scrollview(widget_tree: str) -> bool:
    return re.match(r'\s*(SingleChildScrollView|CustomScrollView|ListView|GridView|NestedScrollView)\s*\(', widget_tree) is not None

def _contains_expanders(widget_tree: str) -> bool:
    s = widget_tree.lower()
    return ("sizedbox.expand(" in s) or ("expanded(" in s)

def _cleanup_empty_statements(text: str) -> str:
    text = re.sub(r';\s*;+', ';', text)
    text = re.sub(r'^\s*;\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'(\})\s*;\s*', r'\1', text)
    text = re.sub(r'\n\s*\n+', '\n', text)
    return text.strip()

def _derive_class_prefix(class_name: str) -> str:
    # 例: "FestoraLogin" -> "Festora", "ConvertedSignup" -> "Converted"
    words = re.findall(r'[A-Z][a-z0-9]*', class_name)
    return ''.join(words[:-1]) if len(words) >= 2 else ''

# =============================================================
# XML helpers
# =============================================================

def _collect_edittexts(ir: Dict) -> List[Dict]:
    result: List[Dict] = []
    def walk(n: Dict):
        t = n.get("type")
        attrs = n.get("attrs", {})
        if t == "EditText" or t == "TextInputEditText":
            item = {
                "id": (attrs.get("id") or "").replace("@+id/", "").replace("@id/", ""),
                "hint": attrs.get("hint") or "",
                "inputType": attrs.get("inputType") or "",
            }
            result.append(item)
        for ch in n.get("children", []) or []:
            walk(ch)
    walk(ir)
    return result

def _collect_xml_onclick(ir: Dict) -> List[Tuple[str, str]]:
    """
    XML から (viewId, onClickMethod) を収集
    例: android:onClick="openSignup", id=@+id/tvSignup -> ("tvSignup", "openSignup")
    """
    pairs: List[Tuple[str, str]] = []

    def _id_base2(v: str) -> str:
        if not v: return ""
        return v.split("/")[-1]

    def walk(n: Dict):
        attrs = n.get("attrs", {}) or {}
        onclick = attrs.get("onClick") or attrs.get("android:onClick")
        vid = _id_base2(attrs.get("id", ""))
        if onclick and vid:
            pairs.append((vid, onclick))
        for ch in n.get("children", []) or []:
            walk(ch)

    walk(ir)
    return pairs

# =============================================================
# Java -> Dart logic conversion
# =============================================================

def _intent_replacement(match, class_prefix: str) -> Tuple[str, str]:
    java_cls = match.group(1)  # e.g. SignupActivity
    dart_base = java_cls.replace("Activity", "")
    dart_cls = f"{class_prefix}{dart_base}" if class_prefix else f"Converted{dart_base}"
    line = f'Navigator.push(context, MaterialPageRoute(builder: (context) => const {dart_cls}()));'
    return line, dart_cls

def convert_java_logic_to_dart(java_block: str, class_prefix: str) -> Tuple[str, Set[str]]:
    imported: Set[str] = set()
    # Intent 変数 -> Activity をまず収集
    intent_map = {}
    for m in re.finditer(
        r'(?:final\s+|var\s+|Intent\s+)?(\w+)\s*=\s*new\s+Intent\([^,]+,\s*(\w+)Activity\.class\)\s*;',
        java_block
    ):
        var, cls = m.group(1), m.group(2)  # 例: i, Signup
        intent_map[var] = cls

    # 1) startActivity(new Intent(..., XxxActivity.class)) → Navigator.push(...)
    def _repl_start_new_intent(m):
        target = m.group(1)  # 例: SignupActivity
        base = target.replace("Activity", "")
        dart_cls = f"{class_prefix}{base}" if class_prefix else f"Converted{base}"
        imported.add(dart_cls)
        return f'Navigator.push(context, MaterialPageRoute(builder: (context) => {dart_cls}()));'
    java_block = re.sub(
        r'startActivity\(\s*new\s+Intent\(.*?,\s*(\w+)Activity\.class\)\s*\)\s*;?',
        _repl_start_new_intent,
        java_block
    )

    # 2) new Intent(..., XxxActivity.class) → Navigator.push(...)
    def _repl_new_intent(m):
        target = m.group(1)
        base = target.replace("Activity", "")
        dart_cls = f"{class_prefix}{base}" if class_prefix else f"Converted{base}"
        imported.add(dart_cls)
        return f'Navigator.push(context, MaterialPageRoute(builder: (context) => {dart_cls}()));'
    java_block = re.sub(
        r'new\s+Intent\(.*?,\s*(\w+)Activity\.class\)',
        _repl_new_intent,
        java_block
    )

    # ★ 追加: startActivity(intentVar) → Navigator.push(...)
    def _repl_start_with_var(m):
        var = m.group(1)
        cls = intent_map.get(var)
        if not cls:
            return m.group(0)  # 分からなければそのまま
        base = cls.replace('Activity','')
        dart_cls = f"{class_prefix}{base}" if class_prefix else f"Converted{base}"
        imported.add(dart_cls)
        return f'Navigator.push(context, MaterialPageRoute(builder: (context) => {dart_cls}()));'
    java_block = re.sub(r'startActivity\(\s*(\w+)\s*\)\s*;?', _repl_start_with_var, java_block)

    # 3) Toast → SnackBar
    java_block = re.sub(
        r'Toast\.makeText\(.*?,\s*"(.*?)",\s*Toast\.LENGTH_(?:SHORT|LONG)\)\.show\(\);',
        r'ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("\1")));',
        java_block,
    )

    # 4) equals → ==
    java_block = re.sub(r'(\w+)\.equals\(([^)]+)\)', r'\1 == \2', java_block)

    # 5) 型/冗長削り（startActivity自体は削らない）
    removals = [
        r'\bnew\s+',
        r'\bIntent\s+\w+\s*=\s*',
        r'\bBoolean\b|\bboolean\b|\bString\b|\bint\b|\bdouble\b',
        r'.*binding\..*;\s*',
    ]
    for pat in removals:
        java_block = re.sub(pat, '', java_block)

    # 6) Dart 向け整形
    java_block = re.sub(r'\b(username|password|confirmPassword)\.isEmpty\(\)', r'\1.isEmpty', java_block)
    java_block = re.sub(r';\s*', ';\n', java_block)

    # 7) Controller 前置き
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

    # 8) DB 呼び出しのダミー化（任意）
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
    def _repl_db_assign(m):
        varname = m.group(1)
        return f"final bool {varname} = true; // TODO: implement DB check"
    java_block = re.sub(
        r'(?:final|var|Boolean|boolean)?\s*(\w+)\s*=\s*databaseHelper\.check\w*\([^;]*\)\s*;',
        _repl_db_assign, java_block, flags=re.I,
    )
    java_block = re.sub(
        r'databaseHelper\.check\w*\([^;]*\)',
        r'true /* TODO: implement DB check */',
        java_block, flags=re.I,
    )

    java_block = _cleanup_empty_statements(java_block)
    return java_block, imported

# =============================================================
# Click handler extraction with id resolution
# =============================================================

def _build_expr_to_id_map(java_src: str) -> Dict[str, str]:
    """
    Java ソースから「式(変数名など) -> id名」の対応表を作る。
    - var = findViewById(R.id.foo)
    - 代入の別名伝播: a = b; （b が既に foo に解決されていれば a -> foo）
    """
    expr2id: Dict[str, str] = {}

    # 直接 findViewById 代入
    for m in re.finditer(r'\b(\w+)\s*=\s*findViewById\(\s*R\.id\.(\w+)\s*\)', java_src):
        var, _id = m.group(1), m.group(2)
        expr2id[var] = _id

    # 別名伝播（数回）
    for _ in range(4):
        changed = False
        for m in re.finditer(r'\b(\w+)\s*=\s*(\w+)\s*;', java_src):
            left, right = m.group(1), m.group(2)
            if right in expr2id and left not in expr2id:
                expr2id[left] = expr2id[right]
                changed = True
        if not changed:
            break

    return expr2id

def _resolve_target_expr_to_id(target_expr: str, expr2id: Dict[str, str]) -> Optional[str]:
    """
    setOnClick のターゲット式 -> id名 へ解決。
      - findViewById(R.id.foo) -> foo
      - binding.tvSignup      -> tvSignup
      - 変数名                -> expr2id 参照
    """
    s = target_expr.strip()

    # 直接 findViewById(...)
    m = re.match(r'(?:\(\s*\w+\s*\)\s*)?findViewById\s*\(\s*R\.id\.(\w+)\s*\)\s*', s)
    if m:
        return m.group(1)

    # ViewBinding/Databinding 規約: binding.foo
    m = re.match(r'\w+\.(\w+)$', s)  # ex) binding.tvSignup
    if m:
        return m.group(1)

    # 変数名
    if s in expr2id:
        return expr2id[s]

    return None

def _extract_method_body(java_code: str, method_name: str) -> Optional[str]:
    """
    Java の this::method / 単純メソッド呼び出しで参照されるメソッド本体を抽出。
    例:
      private void openSignup(View v) { ... }
      public  void openSignup(...)    { ... }
    """
    pat = re.compile(
        r'(?:public|private|protected)?\s+void\s+'
        + re.escape(method_name) +
        r'\s*\([^)]*\)\s*\{(?P<body>.*?)\}\s*',
        re.DOTALL
    )
    m = pat.search(java_code)
    return (m.group('body').strip() if m else None)

# 変更後（第3引数に all_sources を追加）
def _inline_single_call(block: str, java_code: str, all_sources: Optional[List[str]] = None) -> str:
    m = re.fullmatch(r'\s*(?:this\.)?(\w+)\s*\([^;]*\)\s*;?\s*', block or '')
    if not m:
        return block
    method = m.group(1)
    body = _extract_method_body(java_code, method)
    if not body and all_sources:
        body = _find_method_body_in_sources(all_sources, method)
    return (body if body else block)

def _extract_onclick_cases(java_code: str) -> Dict[str, str]:
    """
    Activity が implements OnClickListener し、onClick(View v) の中で
    v.getId() に対して if / switch で分岐するパターンを抽出。
    返り値: { 'tvSignup': '...java body...' , ... }
    """
    results: Dict[str, str] = {}

    # onClick 本体を取り出す（スタイル差異を許容）
    m = re.search(
        r'(?:public|private|protected)?\s+void\s+onClick\s*\(\s*View\s+\w+\s*\)\s*\)\s*\{(?P<body>.*?)\}\s*',
        java_code, flags=re.DOTALL
    )
    if not m:
        m = re.search(
            r'(?:public|private|protected)?\s+void\s+onClick\s*\(\s*View\s+\w+\s*\)\s*\{(?P<body>.*?)\}\s*',
            java_code, flags=re.DOTALL
        )
        if not m:
            return results
    body = m.group('body')

    # switch (v.getId()) { case R.id.xxx: ... break; }
    for mcase in re.finditer(
        r'case\s+R\.id\.(\w+)\s*:\s*(?P<block>.*?)\bbreak\s*;',
        body, flags=re.DOTALL
    ):
        _id = mcase.group(1)
        block = mcase.group('block').strip()
        results[_id] = block

    # if (v.getId() == R.id.xxx) { ... }
    for mif in re.finditer(
        r'if\s*\(\s*\w+\.getId\(\)\s*==\s*R\.id\.(\w+)\s*\)\s*\{(?P<block>.*?)\}',
        body, flags=re.DOTALL
    ):
        _id = mif.group(1)
        block = mif.group('block').strip()
        results[_id] = block

    return results

def extract_click_handlers_from_java(
    java_code: str,
    class_prefix: str,
    all_sources: Optional[List[str]] = None
) -> Tuple[List[Tuple[str, str, str]], Set[str]]:
    """
    Java コードからクリックハンドラを抽出。
    返り値: [(id_key, func_name, handler_code)], {imported_class_names}

    対応パターン:
      1) target.setOnClickListener(v -> { ... })
      1a) target.setOnClickListener(v -> singleCall())
      1b) target.setOnClickListener(new View.OnClickListener(){ public void onClick(View v){ ... }})
      2) target.setOnClickListener(this::method)
      3) target.setOnClickListener(this) + onClick(View v) 内で v.getId() 分岐
      3b) setOnClickListener(this) を取り逃がしても onClick 分岐があればフォールバックで採用
    """
    handlers: List[Tuple[str, str, str]] = []
    imports: Set[str] = set()

    # 変数名 → XML id の対応表
    expr2id = _build_expr_to_id_map(java_code)

    # ------- 正規表現（改行/空白/ドットの前後を許容）-------
    # 1) ラムダ/匿名クラス（ブレースあり）
    pat = re.compile(
        rf'({TARGET})\s*\.\s*setOnClickListener\s*\('
        r'(?:new\s+(?:\w+\.)?OnClickListener\(\)\s*\{.*?onClick\s*\(\s*[^)]*\s*\)\s*\{(.*?)\}\s*\}'
        r'|\s*(?:\w+|\([^)]*\))\s*->\s*\{(.*?)\}\s*)\)\s*;',
        re.DOTALL
    )

    # 1a) ブレース無しの 1 行ラムダ
    pat_arrow_no_brace = re.compile(
        rf'({TARGET})\s*\.\s*setOnClickListener\s*\('
        r'\s*(?:\w+|\([^)]*\))\s*->\s*(?!\{)\s*([^;]+?)\s*;\s*\)\s*;',
        re.DOTALL
    )

    # 2) メソッド参照 this::method
    pat_ref = re.compile(
        rf'({TARGET})\s*\.\s*setOnClickListener\s*\(\s*this::(\w+)\s*\)\s*;'
    )

    # 3) this デリゲート
    pat_this_delegate = re.compile(
        rf'({TARGET})\s*\.\s*setOnClickListener\s*\(\s*this\s*\)\s*;'
    )

    # （任意）デバッグ：各パターンのヒット件数
    try:
        print(
            "[DEBUG] match counts:",
            len(list(pat.finditer(java_code))),
            len(list(pat_arrow_no_brace.finditer(java_code))),
            len(list(pat_ref.finditer(java_code))),
            len(list(pat_this_delegate.finditer(java_code))),
        )
    except Exception:
        pass

    # ------- ヘルパ：単一呼び出しをメソッド本体に展開（2引数/3引数どちらの実装でも動くように） -------
    def _inline(block_or_expr: str) -> str:
        # まず 3 引数版 _inline_single_call(block, java_code, all_sources) を試す
        try:
            return _inline_single_call(block_or_expr, java_code, all_sources)
        except TypeError:
            # 2 引数版 _inline_single_call(block, java_code) しか無い場合
            body = _inline_single_call(block_or_expr, java_code)
            # なお、それでも見つからなければ all_sources 横断で直接探す
            m = re.fullmatch(r'\s*(?:this\.)?(\w+)\s*\([^;]*\)\s*;?\s*', block_or_expr or '')
            if not m:
                return body
            meth = m.group(1)
            if (not body) and all_sources:
                try:
                    # 3 引数版が無い環境向けフォールバック
                    mb = _find_method_body_in_sources(all_sources, meth)
                    return (mb if mb else block_or_expr)
                except Exception:
                    return body or block_or_expr
            return body or block_or_expr

    # ------- 1) ラムダ/匿名クラス（ブレースあり） -------
    for m in pat.finditer(java_code):
        target_expr = m.group(1)
        raw_block = (m.group(2) or m.group(3) or "").strip()
        block = _inline(raw_block)  # 単一呼び出しならメソッド本体へ展開
        view_id = _resolve_target_expr_to_id(target_expr, expr2id) or target_expr.split('.')[-1]

        func_name = _func_name_from_viewkey(view_id)
        dart_logic, needed_imports = convert_java_logic_to_dart(block, class_prefix)
        imports |= needed_imports

        handler_code = f"""
  void {func_name}(BuildContext context) {{
    {dart_logic if dart_logic else '// (no logic)'}
  }}
""".rstrip()
        handlers.append((view_id, func_name, handler_code))

    # ------- 1a) ブレース無しの 1 行ラムダ -------
    for m in pat_arrow_no_brace.finditer(java_code):
        target_expr = m.group(1)
        expr = (m.group(2) or "").strip()
        block = _inline(expr + ";")
        view_id = _resolve_target_expr_to_id(target_expr, expr2id) or target_expr.split('.')[-1]

        func_name = _func_name_from_viewkey(view_id)
        dart_logic, needed_imports = convert_java_logic_to_dart(block, class_prefix)
        imports |= needed_imports

        handler_code = f"""
  void {func_name}(BuildContext context) {{
    {dart_logic if dart_logic else '// (no logic)'}
  }}
""".rstrip()
        handlers.append((view_id, func_name, handler_code))

    # ------- 2) メソッド参照: setOnClickListener(this::openXxx) -------
    for m in pat_ref.finditer(java_code):
        target_expr = m.group(1)
        method_name = m.group(2)
        view_id = _resolve_target_expr_to_id(target_expr, expr2id) or target_expr.split('.')[-1]

        # まず同一ファイルを探し、無ければ全ソース横断
        method_body = _extract_method_body(java_code, method_name)
        if not method_body and all_sources:
            try:
                method_body = _find_method_body_in_sources(all_sources, method_name)
            except Exception:
                pass
        method_body = method_body or ""

        func_name = _func_name_from_viewkey(view_id)
        dart_logic, needed_imports = convert_java_logic_to_dart(method_body, class_prefix)
        imports |= needed_imports

        handler_code = f"""
  void {func_name}(BuildContext context) {{
    {dart_logic if dart_logic else '// (no logic)'}
  }}
""".rstrip()
        handlers.append((view_id, func_name, handler_code))

    # ------- 3) this デリゲート: setOnClickListener(this) + onClick(View v) 内で v.getId() 分岐 -------
    onclick_map = _extract_onclick_cases(java_code)  # {id: java_body}
    if onclick_map:
        try:
            print("[DEBUG] onclick_map ids:", list(onclick_map.keys()))
        except Exception:
            pass

        # 通常ルート：this をセットしている対象が分かる場合
        for m in pat_this_delegate.finditer(java_code):
            target_expr = m.group(1)
            view_id = _resolve_target_expr_to_id(target_expr, expr2id) or target_expr.split('.')[-1]
            java_body = onclick_map.get(view_id)
            if not java_body:
                continue

            func_name = _func_name_from_viewkey(view_id)
            dart_logic, needed_imports = convert_java_logic_to_dart(java_body, class_prefix)
            imports |= needed_imports

            handler_code = f"""
  void {func_name}(BuildContext context) {{
    {dart_logic if dart_logic else '// (no logic)'}
  }}
""".rstrip()
            handlers.append((view_id, func_name, handler_code))

        # ★ フォールバック：setOnClickListener(this) の検出自体を取り逃しても、
        # onClick の分岐に R.id.<id> が居れば、その id は採用（XML に存在する id のみ後段で残る）
        for view_id, java_body in onclick_map.items():
            if any(h[0] == view_id for h in handlers):
                continue  # 既に作成済みなら重複回避
            func_name = _func_name_from_viewkey(view_id)
            dart_logic, needed_imports = convert_java_logic_to_dart(java_body, class_prefix)
            imports |= needed_imports

            handler_code = f"""
  void {func_name}(BuildContext context) {{
    {dart_logic if dart_logic else '// (no logic)'}
  }}
""".rstrip()
            handlers.append((view_id, func_name, handler_code))

    return handlers, imports


def _patch_android_activity_calls(dart_code: str) -> str:
    # isTaskRoot() -> !Navigator.canPop(context)
    dart_code = re.sub(r'\bisTaskRoot\s*\(\s*\)', '!Navigator.canPop(context)', dart_code)
    # finish(); -> maybePop()
    dart_code = re.sub(r'\bfinish\s*\(\s*\)\s*;', 'Navigator.of(context).maybePop();', dart_code)

    # SystemNavigator.pop() の import 追加（必要時）
    dart_code = re.sub(
        r'if\s*\(\s*!?isTaskRoot\s*\(\s*\)\s*\)\s*\{',
        'if (!Navigator.canPop(context)) { SystemNavigator.pop();',
        dart_code
    )
    if 'SystemNavigator.pop()' in dart_code and "import 'package:flutter/services.dart'" not in dart_code:
        dart_code = "import 'package:flutter/services.dart';\n" + dart_code
    return dart_code

# =============================================================
# Dart code building
# =============================================================

def _build_imports_line(import_classes: Set[str], output_path: str) -> str:
    lines = ["import 'package:flutter/material.dart';"]
    base = os.path.basename(output_path)
    out_dir = os.path.dirname(output_path)
    for cls in sorted(import_classes):
        dart_file = f"{_camel_to_snake(cls)}.dart"
        if dart_file != base:
            candidate_path = os.path.join(out_dir, dart_file)
            if os.path.exists(candidate_path):  # ← 実在チェック
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
            if "confirm" in lower:
                controller_name = "_confirmPasswordController"
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

def _wrap_as_widget_class(class_name: str, widget_tree: str, handlers_code: str,
                          need_stateful: bool, use_scrollview: bool, controllers: List[str]) -> str:
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
    else:
        return f"""class {class_name} extends StatelessWidget {{
  const {class_name}({{super.key}});

  @override
  Widget build(BuildContext context) {{
    return Scaffold(
      appBar: AppBar(title: const Text('{class_name}')),
      body: {body_expr},
    );
  }}
}}
"""

# =============================================================
# Public entry point
# =============================================================

def _gather_java_sources(java_path: str) -> List[str]:
    if os.path.isfile(java_path):
        with open(java_path, "r", encoding="utf-8") as f:
            return [f.read()]
    srcs: List[str] = []
    for root, _, files in os.walk(java_path):
        for fn in files:
            if fn.endswith(".java"):
                p = os.path.join(root, fn)
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        srcs.append(f.read())
                except Exception:
                    pass
    return srcs

def _find_method_body_in_sources(java_sources: List[str], method_name: str) -> Optional[str]:
    pat = re.compile(
        r'(?:public|private|protected)?\s+void\s+'
        + re.escape(method_name) +
        r'\s*\([^)]*\)\s*\{(?P<body>.*?)\}\s*',
        re.DOTALL
    )
    for js in java_sources:
        m = pat.search(js)
        if m:
            return m.group('body').strip()
    return None

def render_screen(ir, resolver, logic_map, java_path, output_path, class_name):
    print(f"[INFO] Generating Dart from XML+Java -> {output_path}")
    edittexts = _collect_edittexts(ir)

    handlers: List[Tuple[str, str, str]] = []
    import_classes: Set[str] = set()
    handlers_code = ""

    # XML 側 id 一覧
    xml_ids = _collect_ids_from_ir(ir)
    xml_id_aliases: Set[str] = set()
    for x in xml_ids:
        xml_id_aliases |= _id_aliases(x)

    # ここでプレフィックス決定（例: FestoraLogin -> "Festora"）
    class_prefix = _derive_class_prefix(class_name)

    # ---- Java 解析 ----
    java_sources: List[str] = []
    if java_path and os.path.exists(java_path):
        java_sources = _gather_java_sources(java_path)
        # render_screen 内、java_sources 取得直後
        print(f"[DEBUG] java files loaded: {len(java_sources)}")

        collected: List[Tuple[str, str, str]] = []
        for js in java_sources:
            h, imps = extract_click_handlers_from_java(js, class_prefix, all_sources=java_sources)
            import_classes |= imps
            for (key, func, code) in h:
                # XML に存在する id のみ採用
                if _id_aliases(key) & xml_id_aliases:
                    collected.append((key, func, code))
                    import_classes |= _find_import_classes(code)

        # id 重複は最後勝ちでユニーク化
        uniq: Dict[str, Tuple[str, str, str]] = {}
        for k, f, c in collected:
            uniq[k] = (k, f, c)

        handlers = list(uniq.values())
        handlers_code = "\n\n".join(h[2] for h in handlers)
        # render_screen 内、collected 決定後
        print("[DEBUG] collected handlers:", [(k, f) for (k, f, _) in collected])
        print("[DEBUG] xml ids:", list(xml_ids))

        # render_screen(...) の中、Java から handlers を集め終わった直後に追加
        button_ids = _collect_button_ids(ir)

        # 既にある handler の id 集合
        handled = {k for (k, _, _) in handlers}

        # 足りないボタン用にスタブを生成
        for vid in button_ids:
            if vid in handled:
                continue
            func = _func_name_from_viewkey(vid)
            stub = f"""
        void {func}(BuildContext context) {{
            // TODO: add navigation or logic for {vid}
        }}
        """.rstrip()
            handlers.append((vid, func, stub))

        # 既存：ボタン用スタブ追加の直後に、これを追加
        handlers_code = "\n\n".join(h[2] for h in handlers) if handlers else ""
        # そして logic_map も更新
        logic_map = {a: f for (v, f, _) in handlers for a in _aliases(v)}

        # logic_map は id を基準に別名登録
        logic_map = {a: f for (v, f, _) in handlers for a in _aliases(v)}
    else:
        print("[WARN] Java path not provided or not found; skipping logic conversion.")

    # ---- ★ XML android:onClick 対応（Java メソッド本体を拾って結線） ----
    xml_onclicks = _collect_xml_onclick(ir)  # [(view_id, method)]
    if xml_onclicks:
        id2handler = {k: (f, c) for (k, f, c) in handlers}  # 既存のハンドラ（重複防止）
        for (vid, mname) in xml_onclicks:
            if vid in id2handler:
                continue  # 既に Java 側で拾えていればスキップ

            body = _find_method_body_in_sources(java_sources, mname) if java_sources else ""
            dart_logic, needed_imports = convert_java_logic_to_dart(body or "", class_prefix)
            import_classes |= needed_imports

            func_name = _func_name_from_viewkey(vid)
            handler_code = f"""
  void {func_name}(BuildContext context) {{
    {dart_logic if dart_logic else '// (no logic)'}
  }}
""".rstrip()

            handlers.append((vid, func_name, handler_code))

        # 再構築
        handlers_code = "\n\n".join(h[2] for h in handlers) if handlers else ""
        logic_map = {a: f for (v, f, _) in handlers for a in _aliases(v)}

    # ---- UI ツリー生成 ----
    widget_tree = translate_node(ir, resolver, logic_map=logic_map)
    widget_tree = _inject_controllers_into_widget_tree(widget_tree, edittexts)
    controllers = _collect_needed_controllers(edittexts)

    # スクロール判定
    use_scroll = True
    if _root_is_scrollview(widget_tree) or _contains_expanders(widget_tree):
        use_scroll = False

    # State 有無: 入力欄 or クリックハンドラがあれば Stateful
    need_stateful = bool(controllers) or bool(handlers)

    # クラスラップ
    widget_class_code = _wrap_as_widget_class(
        class_name, widget_tree, handlers_code, need_stateful, use_scroll, controllers
    )

    import_lines = ["import 'package:flutter/material.dart';"]
    for cls in sorted(import_classes):  # convert_java_logic_to_dart で集めた遷移先クラス群
        fname = _dart_file_from_class(cls)  # LearnEnglishAppMateri -> learnenglishapp_materi.dart
        import_lines.append(f"import '{fname}';")

    imports_block = "\n".join(import_lines)

    dart_code = f"""{imports_block}

// ===== Auto-Generated Widget Class =====

{widget_class_code}
"""
    


    dart_code = _patch_android_activity_calls(dart_code)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(dart_code)

    print(f"[DONE] Generated Dart: {output_path}")
