#!/usr/bin/env python3
"""cache_probe ― 同じリクエストを 2 回送り、2 回目で cache_read_input_tokens > 0 になることを確かめる。

    python cache_probe.py --model claude-opus-5-5 --system-file prompts/system.md

キャッシュが効いているかは usage の数字だけが根拠。コードレビューでは分からない。
プロンプト組み立てを変えたら、毎回これを回す（CI に入れてよい。exit 1 = 効いていない）。
モデルごとの最小キャッシュ長: Opus 5.5 / Sonnet 5.5 / Opus 5 / Fable 5.1 は 512、Opus 4.8 / Sonnet 5 は 1024、Opus 4.6 / Haiku 4.5 は 4096 トークン。
"""
import argparse
import sys

import anthropic


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--system-file", required=True)
    ap.add_argument("--question", default="この指示書の要点を 1 行で。")
    a = ap.parse_args()
    client = anthropic.Anthropic()
    system = open(a.system_file, encoding="utf-8").read()
    kw = dict(
        model=a.model, max_tokens=256,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": a.question}],
        output_config={"effort": "low"},
    )
    r1 = client.messages.create(**kw)
    r2 = client.messages.create(**kw)
    for name, r in (("1回目", r1), ("2回目", r2)):
        u = r.usage
        print(f"{name}: input={u.input_tokens} cache_write={u.cache_creation_input_tokens} cache_read={u.cache_read_input_tokens} output={u.output_tokens}")
    ok = (r2.usage.cache_read_input_tokens or 0) > 0
    print("OK: キャッシュが効いています" if ok else "NG: 2回目も cache_read が 0。最小長未満か、プレフィックスに毎回変わる要素があります")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
