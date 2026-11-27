#!/usr/bin/env python3
"""テキストファイルの文字コード・BOM・改行コードが、形式ごとの要件を満たすか検査する。

ファイルを新規作成・編集した直後に実行する。要件と根拠は RULES の各行に書いてある。
ERROR は「そのまま実行・解析すると壊れる」ことを実測か一次資料で確かめたものだけに割り当て、
慣習・推奨にとどまるものは WARN にする（WARN だけなら終了コードは 0）。

使い方:
    python ~/.claude/scripts/check-encoding.py <パス...>             # 検査のみ（ディレクトリは再帰）
    python ~/.claude/scripts/check-encoding.py <パス...> --fix       # BOM と改行の違反を直す
    python ~/.claude/scripts/check-encoding.py <パス...> --quiet     # 問題のあるファイルと集計だけ
    python ~/.claude/scripts/check-encoding.py --gitattributes [dir] # .gitattributes のひな形を出す
                                                                     # （dir を渡すと、その中にある形式だけ）

終了コード: 0 = ERROR なし / 1 = ERROR あり（--fix 時は 0 を返し、再実行で確かめる）/ 2 = 引数エラー
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

for _s in (sys.stdout, sys.stderr):  # cp932 コンソールでも日本語を出す
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

BOM = b"\xef\xbb\xbf"
UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")


@dataclass(frozen=True)
class Rule:
    reason: str
    bom: str = "any"          # required / forbidden / any（UTF-8 の BOM）
    bom_level: str = "ERROR"
    eol: str = "any"          # lf / crlf / any
    eol_level: str = "ERROR"
    # utf8 / utf8-or-cookie（.py の PEP 263 宣言）/ utf8-or-xmldecl（XML 宣言の encoding）/
    # ansi-or-utf16（ASCII だけなら ANSI 可、非 ASCII は UTF-16 必須）/ utf16-preferred /
    # not-utf8（WSH: UTF-8 を読めない）/ any
    enc: str = "utf8"
    enc_level: str = "ERROR"
    nonascii_warn: str = ""   # 非 ASCII を含むときに出す WARN（空なら出さない）
    gitattr: str | None = None  # .gitattributes の推奨属性（None なら既定の text=auto eol=lf に任せる）
    check: bool = True        # False なら検査せず、.gitattributes のひな形だけに使う


# --- 形式ごとの要件 -------------------------------------------------------------
# 「実測」は手元（Windows 11 / git 2.53 / Python 3.14 / rustc / Node / WSL Ubuntu の bash）で確かめたもの。
_PS = Rule("Windows PowerShell 5.1 は BOM の無い UTF-8 を ANSI（cp932）として読み、日本語が壊れて構文エラーになる",
           bom="required")
_SH = Rule("BOM は shebang と 1 行目を壊し、CRLF は $'\\r': command not found になる（実測）",
           bom="forbidden", eol="lf", gitattr="text eol=lf")
_JS = Rule("Node は BOM 付きの .js を実行できる（実測）。BOM は不要なので慣習として付けない",
           bom="forbidden", bom_level="WARN")
_MAKE = Rule("CRLF は行継続（\\ + CRLF）や include したファイルで GNU make を壊すことがある。レシピの行頭は TAB",
             bom="forbidden", bom_level="WARN", eol="lf", eol_level="WARN", gitattr="text eol=lf")
_DOCKER = Rule("CRLF は RUN の行継続や heredoc でコンテナ内のシェルに \\r を渡す",
               bom="forbidden", bom_level="WARN", eol="lf", eol_level="WARN", gitattr="text eol=lf")
_GIT = Rule("git 2.53 は BOM・CRLF があってもパターンを正しく読む（実測）。慣習として UTF-8・BOM なし",
            bom="forbidden", bom_level="WARN")
_ENV = Rule("bash で source すると、BOM は 1 行目を壊し、CRLF は値の末尾に \\r を残す（実測。python-dotenv は両方とも読める）",
            bom="forbidden", bom_level="WARN", eol="lf", eol_level="WARN", gitattr="text eol=lf")
_BAT = Rule("cmd.exe は BOM を 1 行目のコマンドの一部として読み、LF だけの改行ではラベル・goto を誤解釈することがある",
            bom="forbidden", eol="crlf", eol_level="WARN", enc="any",
            nonascii_warn="UTF-8 の非 ASCII 文字は、chcp 65001 にしない限りコンソールのコードページ（cp932）で読まれて化ける",
            gitattr="text eol=crlf")
_WSH = Rule("Windows Script Host は UTF-8 を読めない（ANSI か UTF-16 LE のみ）。UTF-8 の BOM は構文エラー、BOM なしの日本語は化ける",
            enc="not-utf8", gitattr="text eol=crlf")
_RFC_CRLF = Rule("RFC 5545（iCalendar）/ RFC 6350（vCard 4.0）は UTF-8 と CRLF を規定する（多くの実装は LF も読む）",
                 eol="crlf", eol_level="WARN", enc_level="WARN", gitattr="text eol=crlf")
_XML = Rule("XML は宣言が無ければ UTF-8（か UTF-16）として読まれる。それ以外は <?xml encoding=...?> が必須",
            enc="utf8-or-xmldecl")

RULES: dict[str, Rule] = {
    ".ps1": _PS, ".psm1": _PS, ".psd1": _PS,
    ".sh": _SH, ".bash": _SH, ".zsh": _SH, ".ksh": _SH,
    ".py": Rule("Python 3 のソースの既定は UTF-8（PEP 3120）。cp932 で保存すると coding 宣言が無い限り SyntaxError（実測）。"
                "BOM と CRLF は Python 自体は読める（実測）",
                bom="forbidden", bom_level="WARN", enc="utf8-or-cookie"),
    ".json": Rule("Python の json.loads と Node の JSON.parse は BOM 付きを拒否する（実測）", bom="forbidden"),
    ".toml": Rule("TOML v1.0 は UTF-8 必須。Python の tomllib は BOM 付きを TOMLDecodeError で拒否する（実測）", bom="forbidden"),
    ".yml": Rule("YAML 1.2 は先頭の BOM を許し、PyYAML も読める（実測）。慣習として BOM なし",
                 bom="forbidden", bom_level="WARN"),
    ".md": Rule("BOM は不要で、結合や差分に紛れ込む", bom="forbidden", bom_level="WARN"),
    ".js": _JS, ".mjs": _JS, ".cjs": _JS, ".jsx": _JS, ".ts": _JS, ".tsx": _JS,
    ".css": Rule("BOM は @charset より優先されるだけで壊れない（CSS Syntax 3）。慣習として BOM なし",
                 bom="forbidden", bom_level="WARN"),
    ".html": Rule("WHATWG HTML は UTF-8 を要求する。BOM は許されるが不要",
                  bom="forbidden", bom_level="WARN", enc_level="WARN"),
    ".go": Rule("Go の仕様はソースを UTF-8 と定める（先頭の BOM は無視してよい）", enc="utf8"),
    ".rs": Rule("rustc は UTF-8 以外を読めない（実測）。BOM と CRLF は読める（実測）", enc="utf8"),
    ".java": Rule("javac は先頭の BOM を illegal character '\\ufeff' として拒否する。JDK 18 以降の既定の文字コードは UTF-8（JEP 400）",
                  bom="forbidden", enc_level="WARN"),
    ".properties": Rule("java.util.Properties.load(InputStream) は今も ISO-8859-1 で読む（UTF-8 で読むのは Java 9 以降の ResourceBundle だけ）",
                        enc="any", nonascii_warn="非 ASCII 文字は Properties.load(InputStream) で化ける。\\uXXXX でエスケープするか、読み手を確かめる"),
    ".ini": Rule("Python の configparser は encoding='utf-8-sig' を指定しないと BOM 付きを MissingSectionHeaderError で拒否する（実測）。"
                 "Windows API（GetPrivateProfileString）は ANSI か UTF-16 を読む",
                 bom="forbidden", bom_level="WARN", enc="any"),
    ".xml": _XML, ".svg": _XML,
    ".bat": _BAT, ".cmd": _BAT,
    ".vbs": _WSH, ".wsf": _WSH,
    ".reg": Rule("regedit の書き出し形式（Windows Registry Editor Version 5.00）は UTF-16 LE・BOM 付き。UTF-8 では非 ASCII が化けることがある",
                 enc="utf16-preferred", enc_level="WARN", gitattr="-text"),
    ".inf": Rule("INF は ANSI か UTF-16 LE のみ（UTF-8 は InfVerif のエラー 1003）。非 ASCII を含むなら UTF-16 LE 必須（Microsoft Learn）",
                 enc="ansi-or-utf16", gitattr="-text"),
    ".ics": _RFC_CRLF, ".vcf": _RFC_CRLF,
    ".sln": Rule("Visual Studio は .sln を UTF-8（BOM 付き）・CRLF で書く。LF にすると保存のたびに差分が出る",
                 eol="crlf", eol_level="WARN", gitattr="text eol=crlf"),
    # 検査しない（読み手で要件が変わる）が、.gitattributes では改行を変換させないもの
    ".csv": Rule("読み手（Excel・RFC 4180・プログラム）で文字コードも改行も変わる。リポジトリでは中身を変換させない",
                 gitattr="-text", check=False),
    ".tsv": Rule("同上", gitattr="-text", check=False),
    ".patch": Rule("CRLF のファイルへのパッチは CRLF のまま保つ必要がある", gitattr="-text", check=False),
    ".diff": Rule("同上", gitattr="-text", check=False),
}
RULES[".yaml"] = RULES[".yml"]
RULES[".txt"] = RULES[".md"]
RULES[".htm"] = RULES[".html"]

# 拡張子ではなくファイル名で決まるもの（小文字で照合）。値は (規則, .gitattributes のパターン)
NAME_RULES: dict[str, tuple[Rule, str]] = {
    "makefile": (_MAKE, "Makefile"), "gnumakefile": (_MAKE, "GNUmakefile"),
    "dockerfile": (_DOCKER, "Dockerfile"), "containerfile": (_DOCKER, "Containerfile"),
    ".gitattributes": (_GIT, ".gitattributes"), ".gitignore": (_GIT, ".gitignore"),
    ".editorconfig": (Rule("EditorConfig の仕様は UTF-8・改行 LF か CRLF を求める（BOM の可否は仕様に記載が無い）",
                           bom="forbidden", bom_level="WARN"), ".editorconfig"),
    ".env": (_ENV, ".env"),
}
PREFIX_RULES = [("dockerfile.", _DOCKER, "Dockerfile.*"), ("containerfile.", _DOCKER, "Containerfile.*"),
                (".env.", _ENV, ".env.*")]
SUFFIX_EXTRA = {".mk": (_MAKE, "*.mk"), ".dockerfile": (_DOCKER, "*.dockerfile")}

# 再帰検査で入らないディレクトリ（証跡・第三者由来・生成物・実行時状態）
SKIP_DIRS = {
    ".git", "node_modules", ".jobs", "__pycache__", ".venv", "venv",
    "dist", "prompt", "thought", "adr", "anthropics", "upstream", "for-human",
}
COOKIE_RE = re.compile(rb"^[ \t\f]*#.*?coding[:=][ \t]*([-\w.]+)")


def rule_for(path: Path) -> Rule | None:
    name = path.name.lower()
    if name in NAME_RULES:
        return NAME_RULES[name][0]
    for prefix, rule, _ in PREFIX_RULES:
        if name.startswith(prefix):
            return rule
    ext = path.suffix.lower()
    if ext in SUFFIX_EXTRA:
        return SUFFIX_EXTRA[ext][0]
    return RULES.get(ext)


def scan_paths(paths):
    """引数のパスを、検査対象ファイルの一覧に展開する。明示したファイルは規則が無くても shebang を検査する。"""
    files = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and not any(part in SKIP_DIRS for part in f.parts):
                    r = rule_for(f)
                    if r and r.check:
                        files.append(f)
        elif p.is_file():
            files.append(p)
        else:
            print(f"ERROR  存在しません: {raw}")
    return files


def _eol_counts(body: bytes) -> tuple[int, int, int]:
    crlf = body.count(b"\r\n")
    return crlf, body.count(b"\n") - crlf, body.count(b"\r") - crlf


def check(path: Path):
    """1 ファイルを検査して (findings, data) を返す。findings は (level, message, kind)。"""
    data = path.read_bytes()
    if not data:
        return [], data
    rule = rule_for(path)
    findings = []

    # UTF-16（BOM 付き）: 文字コードの要件だけを見る（BOM・改行の自動修正の対象外）
    if data.startswith(UTF16_BOMS):
        if rule and rule.check and rule.enc in ("utf8", "utf8-or-cookie"):
            findings.append((rule.enc_level, f"UTF-16 で保存されている: {rule.reason}", "encoding"))
        return findings, data

    has_bom = data.startswith(BOM)
    body = data[len(BOM):] if has_bom else data
    if data.startswith(BOM * 2):
        findings.append(("ERROR", "BOM が重複している", "bom"))
    try:
        body.decode("utf-8")
        is_utf8 = True
    except UnicodeDecodeError as e:
        is_utf8, err = False, e
    nonascii = any(b > 0x7F for b in body)

    # shebang（規則の有無にかかわらず）。BOM と 1 行目の CRLF は、Unix / WSL で直接実行すると壊れる（実測）。
    # Windows で `python x.py` のように呼ぶ分には壊れず、core.autocrlf で取り出したファイルはほぼ全部 CRLF に
    # なるため WARN にとどめる。シェルスクリプトは RULES の BOM・改行の規則で ERROR になる
    if body.startswith(b"#!"):
        first = body.split(b"\n", 1)[0]
        # 形式の規則に BOM・改行の要件があればそちらで指摘する（同じ問題を 2 回出さない）
        if has_bom and not (rule and rule.check and rule.bom == "forbidden"):
            findings.append(("WARN", "shebang の前に BOM がある（Unix / WSL で直接実行すると shebang が効かない）", "shebang"))
        if first.endswith(b"\r") and not (rule and rule.check and rule.eol == "lf"):
            findings.append(("WARN", "shebang の行が CRLF（Unix / WSL で直接実行すると bad interpreter になる）", "shebang"))

    if rule is None or not rule.check:
        return findings, data

    # 文字コード
    enc = rule.enc
    if enc in ("utf8", "utf8-or-cookie", "utf8-or-xmldecl") and not is_utf8:
        head = body.split(b"\n", 2)
        declared = (enc == "utf8-or-cookie" and any(COOKIE_RE.match(l) for l in head[:2])) or \
                   (enc == "utf8-or-xmldecl" and b"encoding=" in head[0])
        if not declared:
            findings.append((rule.enc_level, f"UTF-8 として読めない（{err.reason} at byte {err.start}）: {rule.reason}", "encoding"))
    elif enc == "ansi-or-utf16":
        if has_bom:
            findings.append(("ERROR", f"UTF-8 で保存されている: {rule.reason}", "encoding"))
        elif nonascii:
            findings.append(("ERROR", f"非 ASCII 文字があるのに UTF-16 LE でない: {rule.reason}", "encoding"))
    elif enc == "utf16-preferred" and (has_bom or nonascii):
        findings.append((rule.enc_level, f"UTF-16 LE（BOM 付き）でない: {rule.reason}", "encoding"))
    elif enc == "not-utf8" and (has_bom or (nonascii and is_utf8)):
        findings.append((rule.enc_level, f"UTF-8 で保存されている: {rule.reason}", "encoding"))
    if rule.nonascii_warn and nonascii and is_utf8:
        findings.append(("WARN", rule.nonascii_warn, "nonascii"))

    # BOM（UTF-8）
    if rule.bom == "required" and not has_bom:
        findings.append((rule.bom_level, f"BOM が無い: {rule.reason}", "bom"))
    elif rule.bom == "forbidden" and has_bom:
        findings.append((rule.bom_level, f"BOM がある: {rule.reason}", "bom"))

    # 改行
    crlf, lone_lf, lone_cr = _eol_counts(body)
    if lone_cr:
        findings.append(("ERROR", f"単独の CR が {lone_cr} 個ある（古い Mac 形式の混入）", "eol"))
    if crlf and lone_lf:
        # 改行の指定が無い形式の混在は、git の text=auto が格納時に正規化するので壊れない。差分が汚れるだけ
        level = rule.eol_level if rule.eol != "any" else "WARN"
        findings.append((level, f"CRLF と LF が混在している（CRLF {crlf} / LF {lone_lf}）", "eol"))
    elif rule.eol == "lf" and crlf:
        findings.append((rule.eol_level, f"改行が CRLF（{crlf} 行）: {rule.reason}", "eol"))
    elif rule.eol == "crlf" and lone_lf and not crlf:
        findings.append((rule.eol_level, f"改行が LF（{lone_lf} 行）: {rule.reason}", "eol"))
    return findings, data


def fix(path: Path, data: bytes, findings) -> str:
    """検出した違反のうち、機械的に直せるもの（UTF-8 の BOM・改行・shebang）を直す。"""
    kinds = {k for _, _, k in findings}
    if "encoding" in kinds:
        return f"SKIP  {path}: 文字コードの違反は自動修正しない（変換先を人が決める）"
    if data.startswith(UTF16_BOMS):
        return f"SKIP  {path}: UTF-16 のファイルは自動修正しない"
    rule = rule_for(path)
    body = data
    while body.startswith(BOM):
        body = body[len(BOM):]
    eol = rule.eol if rule else "any"
    if "shebang" in kinds and eol == "any":
        eol = "lf"
    if "eol" in kinds or "shebang" in kinds:
        body = body.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        if eol == "crlf":
            body = body.replace(b"\n", b"\r\n")
        elif eol == "any" and b"\r\n" in data:  # 混在の解消は多い方へ寄せる
            crlf, lone_lf, _ = _eol_counts(data)
            if crlf > lone_lf:
                body = body.replace(b"\n", b"\r\n")
    keep_bom = data.startswith(BOM) and not ({"bom", "shebang"} & kinds)
    out = (BOM + body) if (rule and rule.bom == "required") or keep_bom else body
    if out == data:
        return f"OK    {path}: 変更なし"
    path.write_bytes(out)
    return f"FIXED {path}: {len(data)} -> {len(out)} バイト"


def gitattributes(root: Path | None) -> str:
    """推奨する .gitattributes を返す。root を渡すと、その中に実在する形式の行だけにする。"""
    entries: list[tuple[str, str, str]] = []  # (パターン, 属性, 理由)
    for ext, r in RULES.items():
        if r.gitattr:
            entries.append((f"*{ext}", r.gitattr, r.reason))
    for _, (r, pat) in NAME_RULES.items():
        if r.gitattr:
            entries.append((pat, r.gitattr, r.reason))
    for _, r, pat in PREFIX_RULES:
        entries.append((pat, r.gitattr, r.reason))
    for _, (r, pat) in SUFFIX_EXTRA.items():
        entries.append((pat, r.gitattr, r.reason))

    if root is not None:
        present = set()
        for f in root.rglob("*"):
            if f.is_file() and not any(part in SKIP_DIRS for part in f.relative_to(root).parts):
                present.add(f.name.lower())
                present.add("*" + f.suffix.lower())
        def hit(pat: str) -> bool:
            p = pat.lower()
            if p.endswith(".*"):
                return any(n.startswith(p[:-1]) for n in present)
            return p in present
        entries = [e for e in entries if hit(e[0])]

    lines = ["# 改行はリポジトリでも作業ツリーでも LF を基本にする（core.autocrlf の設定に左右されない）",
             "* text=auto eol=lf", ""]
    last_attr = None
    for pat, attr, reason in sorted(entries, key=lambda e: (e[1], e[0])):
        if attr != last_attr:
            lines.append({"text eol=lf": "# LF でないと壊れる・壊れやすいもの",
                          "text eol=crlf": "# CRLF が必要・標準のもの",
                          "-text": "# 中身を変換させないもの（UTF-16・読み手で要件が変わるもの・パッチ）"}.get(attr, f"# {attr}"))
            last_attr = attr
        lines.append(f"{pat:<16} {attr}")
    return "\n".join(lines) + "\n"


def main() -> int:
    argv = sys.argv[1:]
    if "--gitattributes" in argv:
        rest = [a for a in argv if not a.startswith("--")]
        root = Path(rest[0]) if rest else None
        if root is not None and not root.is_dir():
            print(f"ディレクトリではありません: {root}")
            return 2
        sys.stdout.write(gitattributes(root))
        return 0

    args = [a for a in argv if not a.startswith("--")]
    do_fix = "--fix" in argv
    quiet = "--quiet" in argv
    if not args:
        print(__doc__)
        return 2

    files = scan_paths(args)
    if not files:
        print("検査対象がありません")
        return 0

    errors = warns = 0
    for f in files:
        findings, data = check(f)
        if not findings:
            if not quiet:
                print(f"OK     {f}")
            continue
        for level, msg, _ in findings:
            print(f"{level:<6} {f}: {msg}")
            if level == "ERROR":
                errors += 1
            else:
                warns += 1
        if do_fix:
            print("       " + fix(f, data, findings))

    print(f"\n検査 {len(files)} 件 / ERROR {errors} 件 / WARN {warns} 件"
          + ("（--fix で修正済み。再実行して 0 件になることを確認する）" if do_fix and errors else ""))
    return 1 if (errors and not do_fix) else 0


if __name__ == "__main__":
    sys.exit(main())
