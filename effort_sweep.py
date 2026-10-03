#!/usr/bin/env python3
"""effort_sweep ― 固定した評価セットを effort ごとに流し、合格率と 1 件あたり費用を並べる。

    python effort_sweep.py --model claude-opus-5 --levels low,medium,high samples/eval.jsonl

eval.jsonl: 1 行 1 件。{"prompt": "...", "expect": "..."}（expect は出力に含まれるべき文字列。無ければ費用だけ出す）
- 設定ごとに全件を順に流す（キャッシュの読みを揃えるため。混ぜない）
- 費用は定価で概算（モデルの単価は --in-price/--out-price で上書き）
- 1 件 2 件の差は誤差。決める前に試行を重ねる（本文 第 12 章）
"""
import argparse
import json
import sys
import time

import anthropic

PRICES = {  # $/MTok (input, output) 2026-10 時点の定価
    "claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5": (5.0, 25.0), "claude-sonnet-5": (2.0, 10.0), "claude-fable-5-1": (10.0, 50.0),
    "claude-opus-4-8": (5.0, 25.0), "claude-haiku-4-5": (1.0, 5.0),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--levels", default="low,medium,high")
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--in-price", type=float)
    ap.add_argument("--out-price", type=float)
    a = ap.parse_args()
    pin, pout = PRICES.get(a.model, (None, None))
    pin = a.in_price or pin; pout = a.out_price or pout
    if pin is None:
        sys.exit("単価が未登録のモデルです。--in-price/--out-price を指定してください")
    cases = [json.loads(l) for l in open(a.file, encoding="utf-8") if l.strip()]
    client = anthropic.Anthropic()
    print(f"model={a.model} cases={len(cases)}")
    print(f"{'effort':>8} {'pass':>6} {'$/case':>8} {'sec/case':>9} {'out_tok/case':>13}")
    for level in a.levels.split(","):
        level = level.strip(); passed = 0; cost = 0.0; secs = 0.0; out_tok = 0
        for c in cases:
            t0 = time.monotonic()
            with client.messages.stream(model=a.model, max_tokens=a.max_tokens, output_config={"effort": level},
                                        messages=[{"role": "user", "content": c["prompt"]}]) as s:
                r = s.get_final_message()
            secs += time.monotonic() - t0
            text = "".join(b.text for b in r.content if b.type == "text")
            if "expect" not in c or c["expect"] in text:
                passed += 1
            u = r.usage
            cost += (u.input_tokens + (u.cache_creation_input_tokens or 0) * 1.25 + (u.cache_read_input_tokens or 0) * 0.1) * pin / 1e6 + u.output_tokens * pout / 1e6
            out_tok += u.output_tokens
        n = len(cases)
        print(f"{level:>8} {passed:>3}/{n:<2} {cost / n:>8.4f} {secs / n:>9.1f} {out_tok / n:>13.0f}")


if __name__ == "__main__":
    sys.exit(main())
