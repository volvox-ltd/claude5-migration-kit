#!/usr/bin/env python3
"""claude5-migration-kit: scan ― Claude 5 世代（Opus 5 / Sonnet 5 / Fable 5.1）への移行で
壊れる・黙って変わる箇所を、ソースコードから静的に見つける。

    python scan.py <path> [--target opus-5|sonnet-5|fable-5-1] [--json] [--fail-on-blocks]

- 言語を問わず正規表現で探す（Python / TypeScript / Go / Ruby / Java / PHP / cURL のスクリプト等）
- 見つかったものは hazard ID・重大度（BLOCKS = 400 や無音の truncation / TUNE = 挙動変化）・修正のヒント付き
- --fail-on-blocks で CI に組み込める（BLOCKS が 1 件でもあれば exit 1）
- 誤検知はある。「候補を漏れなく出す」側に倒してあるので、最終判断は本文（第 2 章・第 12 章）で
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

TARGETS = ("opus-5", "sonnet-5", "fable-5-1", "all")
EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".go", ".rb", ".java", ".kt", ".cs", ".php", ".sh", ".yaml", ".yml", ".json", ".toml", ".env", ".txt", ".md"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", ".next", "__pycache__", "vendor", ".tox", ".mypy_cache"}


@dataclass
class Hazard:
    id: str
    severity: str          # BLOCKS | TUNE
    targets: tuple         # どのターゲットで問題になるか
    pattern: str
    title: str
    fix: str
    flags: int = re.IGNORECASE


HAZARDS: list[Hazard] = [
    Hazard("H01", "BLOCKS", ("all",),
           r"claude-(3-[a-z0-9-]+|2\.[01]|instant[a-z0-9-]*|opus-4-20250514|sonnet-4-20250514|opus-4-1(-20250805)?)\b",
           "引退済み・引退予定のモデル ID",
           "claude-opus-5 / claude-sonnet-5 / claude-haiku-4-5 のいずれかに置換（本文 第 1 章の対応表）"),
    Hazard("H02", "BLOCKS", ("all",),
           r"budget_tokens|[\"']type[\"']\s*[:=]\s*[\"']enabled[\"']",
           "固定予算の拡張思考（budget_tokens / type: enabled）",
           "thinking={\"type\": \"adaptive\"} ＋ output_config.effort に置換。Fable 5.1 では thinking 自体を省略"),
    Hazard("H03", "BLOCKS", ("all",),
           r"\b(temperature|top_p|top_k|topP|topK)\s*[:=]",
           "サンプリングパラメータ（temperature / top_p / top_k）",
           "削除。決定性が目的なら effort: low ＋ 明確なプロンプト、多様性が目的なら「4 案出して選ばせる」等のプロンプトへ"),
    Hazard("H04", "BLOCKS", ("all",),
           r"[\"']role[\"']\s*[:=]\s*[\"']assistant[\"']\s*,\s*[\"']content[\"']\s*[:=]\s*[\"'](\{|\[|Here|以下|\s*$)",
           "末尾アシスタントターンのプリフィル（JSON や前置きの強制）",
           "output_config.format（構造化出力）か messages.parse() に置換。few-shot の途中の assistant ターンは対象外"),
    Hazard("H05", "BLOCKS", ("all",),
           r"messages\.create\([^)]*output_format\s*=",
           "messages.create() の output_format（非推奨の旧パラメータ）",
           "output_config={\"format\": {...}} に移す（.parse() の output_format= は有効）",
           re.IGNORECASE | re.DOTALL),
    Hazard("H06", "TUNE", ("all",),
           r"effort-2025-11-24|interleaved-thinking-2025-05-14|fine-grained-tool-streaming-2025-05-14|token-efficient-tools-2025-02-19|output-128k-2025-02-19|server-side-fallback-2026-06-0[29]|mid-conversation-effort-2026-08-01|per-turn-control-2026-07-01",
           "古い・非推奨のベータヘッダ",
           "GA 済みのヘッダは削除し client.beta → client.messages に戻す。fallback の旧ヘッダは -2026-06-01（配列形）/ -2026-07-01（\"default\"）へ"),
    Hazard("H07", "BLOCKS", ("fable-5-1",),
           r"tool_choice\s*[:=]\s*\{[^}]*[\"']type[\"']\s*[:=]\s*[\"'](any|tool)[\"']",
           "強制ツール呼び出し（tool_choice any / tool）",
           "Fable 5.1 では 400。tool_choice auto ＋ プロンプトでツール名を指定、引数の保証は strict: true、JSON 抽出なら構造化出力"),
    Hazard("H08", "BLOCKS", ("opus-5", "fable-5-1"),
           r"[\"']type[\"']\s*[:=]\s*[\"']disabled[\"']",
           "thinking: disabled",
           "Fable 5.1 では常に 400。Opus 5 では effort xhigh/max との併用で 400、かつツール呼び出しが本文に漏れる既知の不具合あり → 思考はオンのまま effort low/medium で"),
    Hazard("H09", "TUNE", ("all",),
           r"\.thinking\b(?!\s*=)|\[[\"']thinking[\"']\]",
           "thinking ブロックの本文を読んでいる",
           "既定が display: omitted になり空文字になる。表示に使うなら thinking={\"type\": \"adaptive\", \"display\": \"summarized\"} を付ける"),
    Hazard("H10", "TUNE", ("all",),
           r"content\[0\]\.text|content\[0\][\"']text[\"']|\.content\[0\]\b",
           "stop_reason を見ずに content[0] を読んでいる",
           "refusal（HTTP 200・content 空）で落ちる。先に stop_reason を判定し、fallbacks: \"default\" への opt-in を検討"),
    Hazard("H11", "TUNE", ("opus-5", "sonnet-5", "fable-5-1"),
           r"max_tokens\s*[:=]\s*(?:[1-9]\d{0,2}|[1-3]\d{3})\b",
           "小さい max_tokens（4,000 未満）",
           "思考が既定でオンになり、max_tokens は思考＋本文の合計上限。途中で切れる（stop_reason: max_tokens）。16,000 以上、エージェントは 64,000 を目安に"),
    Hazard("H12", "BLOCKS", ("all",),
           r"text_editor_20250124|str_replace_editor\b|undo_edit|code_execution_2025(0522|0825)\b",
           "古いツールバージョン",
           "text_editor_20250728 ＋ str_replace_based_edit_tool（両方同時に変更）、code_execution_20260521 または _20260120。undo_edit は削除"),
    Hazard("H13", "TUNE", ("all",),
           r"think step by step|<scratchpad>|<thinking>|every \d+ (tool calls|messages)|at most \d+ (words|sentences|bullets)|\b(CRITICAL|IMPORTANT)\s*:\s*(YOU )?(MUST|NEVER|ALWAYS)",
           "旧世代向けのプロンプト定型句（圧力表現・思考の指示・出力の数値制限）",
           "第 8 章の監査へ。思考は adaptive thinking が担う。圧力表現は通常の文に戻す。数値制限は目的の記述に置き換える"),
    Hazard("H14", "TUNE", ("all",),
           r"(system\s*[:=][^\n]*(datetime\.now|Date\.now|time\.time|uuid4|randomUUID|new Date\())",
           "システムプロンプトに時刻や乱数を埋め込んでいる（キャッシュ無効化）",
           "プレフィックスが毎回変わりキャッシュが一切効かない。動的な情報は messages の末尾（role: system メッセージ等）へ"),
    Hazard("H15", "TUNE", ("fable-5-1",),
           r"messages\s*=\s*messages\[-\d+:\]|messages\.pop\(0\)|del\s+messages\[|messages\.splice\(0|messages\.shift\(\)|history\[-\d+:\]",
           "会話履歴の先頭・途中を削っている（履歴編集）",
           "Fable 5.1 の preserved thinking で 400 または思考ブロックの破棄。サーバー側 compaction / context editing か、要約 1 本に差し替える simple compaction へ"),
    Hazard("H16", "BLOCKS", ("all",),
           r"claude-opus-4-[678]-fast\b",
           "-fast 付きモデル ID",
           "claude-opus-5 ＋ speed=\"fast\" ＋ betas=[\"fast-mode-2026-02-01\"]（client.beta.messages）。4.6-fast は黙って通常速度に落ち、4.7-fast はエラー"),
    Hazard("H17", "TUNE", ("fable-5-1",),
           r"system\s*[:=]\s*[^\n]*(f[\"']|\$\{|\+\s*[a-zA-Z_]+\s*\+|%s|\{\{)",
           "システムプロンプトを毎リクエスト組み立てている（可変の可能性）",
           "セッション中に top-level system が変わると preserved thinking の検査で 400。固定し、変更は role: system メッセージで追記"),
]


@dataclass
class Finding:
    hazard: str
    severity: str
    targets: list
    file: str
    line: int
    text: str
    title: str
    fix: str


def iter_files(root: Path):
    if root.is_file():
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix in EXTS or fn.startswith(".env"):
                yield p


def scan_file(path: Path, target: str) -> list[Finding]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out: list[Finding] = []
    lines = text.splitlines()
    for h in HAZARDS:
        if target != "all" and "all" not in h.targets and target not in h.targets:
            continue
        if h.flags & re.DOTALL:
            for m in re.finditer(h.pattern, text, h.flags):
                ln = text.count("\n", 0, m.start()) + 1
                out.append(Finding(h.id, h.severity, list(h.targets), str(path), ln, lines[ln - 1].strip()[:160], h.title, h.fix))
            continue
        for i, line in enumerate(lines, 1):
            if re.search(h.pattern, line, h.flags):
                out.append(Finding(h.id, h.severity, list(h.targets), str(path), i, line.strip()[:160], h.title, h.fix))
    return out


def scan(root: str | Path, target: str = "all") -> list[Finding]:
    root = Path(root)
    findings: list[Finding] = []
    for f in iter_files(root):
        if f.resolve() == Path(__file__).resolve():
            continue
        findings.extend(scan_file(f, target))
    findings.sort(key=lambda x: (x.severity != "BLOCKS", x.hazard, x.file, x.line))
    return findings


def render(findings: list[Finding], target: str) -> str:
    if not findings:
        return f"✓ 検出なし（target={target}）"
    blocks = [f for f in findings if f.severity == "BLOCKS"]
    tunes = [f for f in findings if f.severity == "TUNE"]
    out = [f"target={target}  BLOCKS={len(blocks)}  TUNE={len(tunes)}", ""]
    for sev, group in (("BLOCKS", blocks), ("TUNE", tunes)):
        if not group:
            continue
        out.append(f"== {sev} ==")
        last = None
        for f in group:
            if f.hazard != last:
                out.append(f"[{f.hazard}] {f.title}")
                out.append(f"      → {f.fix}")
                last = f.hazard
            out.append(f"   {f.file}:{f.line}  {f.text}")
        out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--target", choices=TARGETS, default="all", help="移行先。既定は all（全ハザード）")
    ap.add_argument("--json", action="store_true", help="JSON で出力")
    ap.add_argument("--fail-on-blocks", action="store_true", help="BLOCKS があれば exit 1（CI 用）")
    a = ap.parse_args(argv)
    findings = scan(a.path, a.target)
    if a.json:
        print(json.dumps([asdict(f) for f in findings], ensure_ascii=False, indent=1))
    else:
        print(render(findings, a.target))
    if a.fail_on_blocks and any(f.severity == "BLOCKS" for f in findings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
