# android2flutter/translator/java_parser.py
import re
from pathlib import Path

# ---------- 公開API ----------
def parse_click_handlers(java_paths):
    """
    与えられた Java ファイル群から setOnClickListener(...) を検出し、
    {xml_id: dart_handler_body} の dict を返す。
    """
    if isinstance(java_paths, (str, Path)):
        java_paths = [java_paths]

    logic = {}

    for p in java_paths:
        src = Path(p).read_text(encoding="utf-8", errors="ignore")

        # 1) var = findViewById(R.id.someId);
        var_to_id = _collect_var_to_id(src)

        # 2) ラムダ形式 onClick: view.setOnClickListener(v -> { ... });
        for m in re.finditer(
            r'(\b[\w\.]+)\.setOnClickListener\s*\(\s*[\w\(\)\s]*->\s*\{(?P<body>.*?)\}\s*\)\s*;',
            src, flags=re.S
        ):
            target = m.group(1)          # e.g. btnLogin / binding.tvSignup
            body_java = m.group('body')
            xml_id = _resolve_xml_id_from_target(target, var_to_id)
            if not xml_id:
                continue
            logic[xml_id] = _to_dart(body_java)

        # 3) 匿名クラス形式 onClick: new View.OnClickListener(){ public void onClick(View v){ ... }}
        for m in re.finditer(
            r'(\b[\w\.]+)\.setOnClickListener\s*\(\s*new\s+View\.OnClickListener\s*\(\)\s*\{\s*.*?onClick\s*\(\s*View\s+\w+\s*\)\s*\{(?P<body>.*?)\}\s*\}\s*\)\s*;',
            src, flags=re.S
        ):
            target = m.group(1)
            body_java = m.group('body')
            xml_id = _resolve_xml_id_from_target(target, var_to_id)
            if not xml_id:
                continue
            logic[xml_id] = _to_dart(body_java)

    return logic


# ---------- 内部ヘルパ ----------

def _collect_var_to_id(src: str):
    """
    Java から 変数名→XML id の対応を拾う。
    例:
      Button btnLogin = findViewById(R.id.btnLogin);
      tvSignup = findViewById(R.id.tvSignup);
    """
    var_to_id = {}
    # 型あり/なしの両方に対応
    for m in re.finditer(
        r'(?:\b\w+\s+)?(\w+)\s*=\s*(?:\(\s*\w+\s*\)\s*)?findViewById\s*\(\s*R\.id\.(\w+)\s*\)\s*;',
        src
    ):
        var, xml_id = m.group(1), m.group(2)
        var_to_id[var] = xml_id
    return var_to_id



def _resolve_xml_id_from_target(target: str, var_to_id: dict):
    """
    target は "btnLogin" or "binding.tvSignup" のような形を想定。
    binding.* の場合は末尾名を取り、var_to_id があればそれを優先。
    """
    last = target.split('.')[-1]
    if last in var_to_id:
        return var_to_id[last]
    # binding.xx は xx がそのまま id 名になっているケースが多い
    return last


def _activity_to_widget(java_activity_name: str) -> str:
    """
    Java の 'SignupActivity' -> Dart 'ConvertedSignup'
    Java の 'LoginActivity'  -> Dart 'ConvertedLogin'
    """
    name = java_activity_name
    if name.endswith("Activity"):
        name = name[:-8]  # remove 'Activity'
    return f"Converted{name}"


def _to_dart(body_java: str) -> str:
    """
    onClick 本体(Java)を Dart 断片に置換する。
    ここでは最低限の遷移/finish をサポート。
    """
    s = body_java

    # startActivity(new Intent(this, SignupActivity.class));
    # startActivity(new Intent(LoginActivity.this, SignupActivity.class));
    s = re.sub(
        r'startActivity\s*\(\s*new\s+Intent\s*\([^,]+,\s*(\w+)Activity\s*\.class\)\s*\)\s*;',
        lambda m: f"Navigator.push(context, MaterialPageRoute(builder: (_) => {_activity_to_widget(m.group(1)+'Activity')}()));",
        s
    )

    # finish();
    s = re.sub(r'\bfinish\s*\(\s*\)\s*;', r'Navigator.maybePop(context);', s)

    # Toast.* は簡易コメント化
    s = re.sub(r'Toast\.makeText\(.*?\)\.show\(\)\s*;', r'// TODO: show a SnackBar/Toast', s, flags=re.S)

    # Java文末; は Dart 文としてもOKなので残す
    return s.strip()
