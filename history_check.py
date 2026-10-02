#!/usr/bin/env python3
"""history_check ― Fable 5.1 の preserved thinking（履歴編集の検査）に自分のループが耐えるかを確かめる。

    python history_check.py --turns 3

thinking-binding-controls ベータで prefix_mismatch_behavior=drop_block を送り、
各応答の input_transformations を表示する。全ターン空配列なら履歴は無傷。
prefix_binding_mismatch が出たら、その path より前の何かを前回から変えている。
CI では "error" にして、編集があれば失敗させる（本文 第 6 章・三段階の確認）。
ここでは「わざと履歴を編集する」ケースも最後に 1 回流して、検出されることを示す。
"""
import argparse
import sys

import anthropic

BETA = "thinking-binding-controls-2026-08-01"


def ask(client, model, messages, behavior):
    r = client.beta.messages.create(
        model=model, max_tokens=2000, betas=[BETA],
        thinking={"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": behavior}},
        system="短く答えてください。",
        messages=messages,
    )
    tr = getattr(r, "input_transformations", None)
    print("  input_transformations:", [getattr(t, "reason", t) for t in (tr or [])] if tr is not None else "(フィールドなし)")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-fable-5-1")
    ap.add_argument("--turns", type=int, default=3)
    a = ap.parse_args()
    client = anthropic.Anthropic()
    messages = []
    print("== 追記のみの会話（無傷のはず）")
    for i in range(a.turns):
        messages.append({"role": "user", "content": f"{i + 1} に 1 を足すと？"})
        r = ask(client, a.model, messages, "drop_block")
        messages.append({"role": "assistant", "content": r.content})  # thinking ブロックごと、そのまま戻す
    print("== 先頭ターンを削って送る（履歴編集 → prefix_binding_mismatch が出るはず）")
    edited = messages[2:]
    edited.append({"role": "user", "content": "最後の答えをもう一度。"})
    ask(client, a.model, edited, "drop_block")
    return 0


if __name__ == "__main__":
    sys.exit(main())
