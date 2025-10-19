# android2flutter/parser/java_parser.py
import os, re

# まずは正規表現ベース(MVP)。必要に応じて javalang や tree-sitter でAST化に置換可。
# 返り値: { "<xml-id>": "Dart の onPressed/onTap 本体コード" }
def parse_java_logic(java_path_or_dir):
    sources = []
    if os.path.isdir(java_path_or_dir):
        for root, _, files in os.walk(java_path_or_dir):
            for fn in files:
                if fn.endswith(".java"):
                    sources.append(os.path.join(root, fn))
    elif os.path.isfile(java_path_or_dir):
        sources.append(java_path_or_dir)

    logic = {}  # id -> dart handler body

    for p in sources:
        with open(p, encoding="utf-8", errors="ignore") as f:
            code = f.read()

        # ViewBinding: binding.signupRedirectText.setOnClickListener(...)
        for m in re.finditer(r"binding\.([A-Za-z0-9_]+)\.setOnClickListener\s*\(\s*new\s+View\.OnClickListener\s*\(\)\s*\{\s*@Override\s*public\s*void\s*onClick\s*\([^\)]*\)\s*\{\s*(?P<body>.*?)\}\s*\}\s*\)\s*;", code, re.S):
            field = m.group(1)  # 例: signupRedirectText / loginButton
            body = _java_body_to_dart(m.group("body"))
            # binding のフィールド名 → XML の id に一致する前提（Android Studio が生成）
            logic[field] = body

        # 古典 findViewById + 変数.setOnClickListener(...)
        # 1) 変数 ← findViewById(R.id.xxx)
        id_by_var = {}
        for mv in re.finditer(r"([A-Za-z0-9_]+)\s*=\s*findViewById\s*\(\s*R\.id\.([A-Za-z0-9_]+)\s*\)\s*;", code):
            var, rid = mv.group(1), mv.group(2)
            id_by_var[var] = rid
        # 2) var.setOnClickListener(...)
        for m in re.finditer(r"([A-Za-z0-9_]+)\.setOnClickListener\s*\(\s*new\s+View\.OnClickListener\s*\(\)\s*\{\s*@Override\s*public\s*void\s*onClick\s*\([^\)]*\)\s*\{\s*(?P<body>.*?)\}\s*\}\s*\)\s*;", code, re.S):
            var = m.group(1)
            body = _java_body_to_dart(m.group("body"))
            rid = id_by_var.get(var)
            if rid:
                logic[rid] = body

    return logic


def _java_body_to_dart(body: str) -> str:
    # ざっくりインテント遷移 / finish / Toast を Dart に写像 (必要に応じて拡張)
    t = body

    # startActivity(new Intent(X.this, Y.class));
    t = re.sub(
        r"startActivity\s*\(\s*new\s+Intent\s*\(\s*[^,]+,\s*([A-Za-z0-9_]+)\.class\s*\)\s*\)\s*;",
        r"Navigator.push(context, MaterialPageRoute(builder: (context) => \1()));",
        t
    )

    # finish();
    t = re.sub(r"\bfinish\s*\(\s*\)\s*;", r"Navigator.pop(context);", t)

    # Toast.makeText(ctx, "msg", Toast.LENGTH_SHORT).show();
    t = re.sub(
        r"Toast\.makeText\([^,]+,\s*\"([^\"]*)\",\s*Toast\.[A-Z_]+\)\.show\(\)\s*;",
        r"ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(\"\1\")));",
        t
    )

    # getText() -> controller.text 等は後で本格対応。ここは素通し。
    return t.strip()
