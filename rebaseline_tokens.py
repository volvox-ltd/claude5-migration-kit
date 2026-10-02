#!/usr/bin/env python3
"""rebaseline_tokens ― 同じプロンプトを旧モデルと新モデルで count_tokens し、トークン数の変化を表にする。

    python rebaseline_tokens.py --old claude-sonnet-4-6 --new claude-sonnet-5 samples/prompts.jsonl

prompts.jsonl: 1 行 1 リクエスト。{"system": "...", "messages": [...]} の形（messages 必須）。
count_tokens は推論を走らせないので無料に近い（レート制限は消費する）。
新トークナイザ（Opus 4.7 以降・Sonnet 5）は同じ文章で 1.0〜1.35 倍のトークンになる。
max_tokens・コンテキスト予算・コスト試算は、この表を見てから更新する。一律の倍率は当てない。
"""
import argparse
import json
import sys

import anthropic


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    a = ap.parse_args()
    client = anthropic.Anthropic()
    rows = []
    with open(a.file, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            req = json.loads(line)
            kw = {"messages": req["messages"]}
            if req.get("system"):
                kw["system"] = req["system"]
            if req.get("tools"):
                kw["tools"] = req["tools"]
            old = client.messages.count_tokens(model=a.old, **kw).input_tokens
            new = client.messages.count_tokens(model=a.new, **kw).input_tokens
            rows.append((i, old, new, new / old if old else float("nan")))
    print(f"{'#':>3} {a.old:>22} {a.new:>22} {'ratio':>6}")
    for i, old, new, r in rows:
        print(f"{i:>3} {old:>22} {new:>22} {r:>6.2f}")
    if rows:
        tot_old = sum(r[1] for r in rows); tot_new = sum(r[2] for r in rows)
        print(f"{'sum':>3} {tot_old:>22} {tot_new:>22} {tot_new / tot_old:>6.2f}")


if __name__ == "__main__":
    sys.exit(main())
