#!/usr/bin/env python3
"""refusal_fallback_demo ― stop_reason: refusal の扱いと、サーバー側 fallbacks: "default" の opt-in。

    python refusal_fallback_demo.py --model claude-opus-5

Opus 5 / Fable 5.1 の安全分類器は HTTP 200 のまま stop_reason="refusal" を返す（content は空か途中まで）。
content[0] を無条件に読むコードはここで落ちる。fallbacks: "default" を付けると、拒否カテゴリに応じて
推奨の代替モデルで同じリクエストをサーバー側が再実行する。
"""
import argparse
import sys

import anthropic


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-opus-5")
    ap.add_argument("--prompt", default="Python で CSV を読む最小のコードを 1 つ。")
    a = ap.parse_args()
    client = anthropic.Anthropic()
    r = client.beta.messages.create(
        model=a.model, max_tokens=2000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": a.prompt}],
    )
    print("model:", r.model, "stop_reason:", r.stop_reason)
    if r.stop_reason == "refusal":
        sd = r.stop_details
        print("refused. category:", getattr(sd, "category", None), "explanation:", getattr(sd, "explanation", None))
        return 2
    for b in r.content:
        if b.type == "fallback":
            print(f"fallback: {b.from_.model} → {b.to.model}")
    fallback_ran = any(getattr(it, "type", "") == "fallback_message" for it in (r.usage.iterations or []))
    print("served by fallback:", fallback_ran)
    print("".join(b.text for b in r.content if b.type == "text")[:400])
    return 0


if __name__ == "__main__":
    sys.exit(main())
