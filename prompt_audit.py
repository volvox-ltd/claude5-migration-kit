#!/usr/bin/env python3
"""claude5-migration-kit: prompt_audit ― プロンプト・スキル・ツール説明の「旧世代向けの癖」を機械的に拾う。

    python prompt_audit.py <file or dir> [--json]

対象: *.md *.txt *.yaml *.yml *.json *.py *.ts *.js（プロンプト文字列が入っていそうなもの）
出力: 行ごとに「パターン / なぜ今は害になるか / 直し方」。削除の最終判断は人がする（本文 第 9 章の keep list を参照）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", ".next", "__pycache__", "vendor"}
EXTS = {".md", ".txt", ".yaml", ".yml", ".json", ".py", ".ts", ".tsx", ".js"}

# (id, group, regex, why, fix)
PATTERNS = [
    ("P1a-pressure", "1a 圧力表現",
     r"\b(CRITICAL|IMPORTANT|MUST|NEVER|ALWAYS)\b(?![a-z])",
     "現行モデルはシステムプロンプトに強く従うため、強調は過剰発火・硬直の原因になる",
     "通常の文に戻し、理由を添える。本当に守らせたい 1〜2 件だけ残す"),
    ("P1a-hedge", "1a 弱い表現",
     r"\b(try to|if possible|ideally|when you can)\b",
     "必須事項に付いた逃げ道は、文字どおり『省略してよい』と読まれる",
     "必須なら断定形にする（Include a summary.）"),
    ("P1a-trait", "1a 性格の決めつけ",
     r"\byou (tend to|often|sometimes)\b|don'?t be too \w+",
     "旧モデルの癖への対症療法。現行モデルでは望む振る舞いを書くほうが効く",
     "望ましい振る舞いを肯定文で 1 行"),
    ("P1b-cot", "1b API 機能に置き換わった足場",
     r"think step[- ]by[- ]step|take a deep breath|<scratchpad>|<thinking>|use the think tool|plan before acting",
     "思考は adaptive thinking と effort が担う。文章で指示すると冗長か、過剰な計画を招く",
     "削除し、深さは output_config.effort で制御"),
    ("P1b-json", "1b JSON 強制の足場",
     r"output only valid json|respond only with json|return only json|no markdown|json\.loads\(.*retry|stop_sequences",
     "構造化出力（output_config.format / messages.parse）が保証するので、周辺のリトライや正規表現も不要",
     "構造化出力に置換し、パース再試行コードを削除"),
    ("P1b-cadence", "1b 出力の振り付け",
     r"every \d+ (tool calls|steps|messages)|summari[sz]e (your )?progress every",
     "現行モデルは自分で適切に進捗を報告する。固定頻度の指示は過剰な文章を生む",
     "削除して再計測。足りなければ『いつ』欲しいかを 1 行で"),
    ("P1b-caps", "1b 数値の出力上限",
     r"(at most|no more than|under|within) \d+ (words|sentences|bullets|lines)",
     "旧モデルの冗長さに合わせた数値は、難しい問題で推論を飢えさせる",
     "目的を書く（『聞かれたことだけに答える』）。形式が重要なら形式を指定する"),
    ("P1c-steps", "1c 手順の過剰指定",
     r"^\s*(STEP|Step) ?\d+[:.)]",
     "判断を要する作業の手順書は、モデル自身の計画より劣ることが多い",
     "成果・制約・検証方法を書く。順序が本当に重要な箇所だけ番号付きで"),
    ("P1c-prohibit", "1c 禁止の羅列",
     r"^\s*[-*]?\s*(Do not|Don'?t|Never|Avoid)\b",
     "失敗の列挙は成功の記述に劣り、起きない失敗を逆に誘導することがある",
     "対象モデルで再現する失敗だけ残し、他は肯定文に書き換える"),
    ("P1c-grader", "1c 採点者の記述",
     r"\b(graded|grader|rubric|hidden tests?)\b",
     "採点装置の説明は『見られている』方向に努力を向けさせる",
     "採点される要件そのものを書く"),
    ("P1d-model", "1d モデル名の化石",
     r"claude-(2|3|instant)|\b(3\.5|3\.7)\b.*(sonnet|haiku|opus)",
     "引退したモデル向けの回避策は所有者不在のまま残る",
     "どのモデルの何を直したかを特定し、引退済みなら削除して再テスト"),
    ("P1d-relative", "1d 差分的な言い回し",
     r"\b(now works differently|no longer|also counts|instead of the previous)\b",
     "モデルが見たことのない旧版との差分を書いている",
     "現行ルールだけを、最初からそうだったように書く"),
    ("P1d-suppress", "1d 更新の抑制",
     r"hold (all )?(findings|results)|don'?t narrate|no interim updates",
     "お喋りだった旧モデル向け。Fable 5.1 はこれがあると黙りすぎる",
     "削除して再計測。欲しい場面を 1 行で指定"),
    ("P1d-antiformat", "1d 書式禁止",
     r"never use (bullets|headers|bold)|no (bullet|header|bold)s?\b",
     "書式過多だった旧モデル向け。Fable 5.1 は元々書式が少なく、必要な書式まで消える",
     "削除、または『どんなときに書式を使うか』の条件文に置換"),
    ("P1d-identity", "1d 中身のない役割宣言",
     r"^You are (a|an) (helpful|expert) \w+\.?\s*$",
     "役割 1 行は可。それが唯一の文脈なら、読者・製品・品質基準が欠けている",
     "役割の代わりに、誰のために何を、どの基準で、を書く"),
    ("P3-tool-shout", "3 ツール説明の圧力",
     r"(CRITICAL|ALWAYS|NEVER)[^.\n]{0,40}(use|call) this tool",
     "発火しにくかった旧モデル向けの増幅は、今は過剰発火になる",
     "『Use this tool when ...』の平叙文に"),
    ("P4-cache", "4 キャッシュを壊す動的要素",
     r"(datetime\.now|Date\.now|time\.time|uuid4|randomUUID)\(",
     "プレフィックスが毎回変わり、プロンプトキャッシュが効かない",
     "最後のブレークポイントより後ろ（ユーザーターン末尾や role: system メッセージ）へ移す"),
]


def iter_files(root: Path):
    if root.is_file():
        yield root
        return
    for d, dn, fn in os.walk(root):
        dn[:] = [x for x in dn if x not in SKIP_DIRS]
        for f in fn:
            p = Path(d) / f
            if p.suffix in EXTS:
                yield p


def audit(root) -> list[dict]:
    out = []
    for p in iter_files(Path(root)):
        if p.resolve() == Path(__file__).resolve():
            continue
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            for pid, group, rx, why, fix in PATTERNS:
                if re.search(rx, line, re.IGNORECASE if not rx.startswith("^") else re.IGNORECASE | re.MULTILINE):
                    out.append({"id": pid, "group": group, "file": str(p), "line": i, "text": line.strip()[:160], "why": why, "fix": fix})
    out.sort(key=lambda f: (f["id"], f["file"], f["line"]))
    return out


def render(findings: list[dict]) -> str:
    if not findings:
        return "✓ 検出なし"
    out = [f"findings={len(findings)}", ""]
    last = None
    for f in findings:
        if f["id"] != last:
            out.append(f"[{f['id']}] {f['group']}")
            out.append(f"   なぜ: {f['why']}")
            out.append(f"   直し方: {f['fix']}")
            last = f["id"]
        out.append(f"      {f['file']}:{f['line']}  {f['text']}")
    out.append("")
    out.append("注意: これは候補の列挙です。読者・製品・品質基準・ツールの契約・理由付きの制約は残します（本文 第 9 章の keep list）。")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    f = audit(a.path)
    print(json.dumps(f, ensure_ascii=False, indent=1) if a.json else render(f))
    return 0


if __name__ == "__main__":
    sys.exit(main())
