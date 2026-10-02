# 移行済みのコード。scan.py で BLOCKS が 0 であること。
import anthropic

client = anthropic.Anthropic()

def ask(q):
    r = client.messages.create(
        model="claude-opus-5",
        max_tokens=16000,
        thinking={"type": "adaptive", "display": "summarized"},
        output_config={"effort": "medium"},
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": q}],
    )
    if r.stop_reason == "refusal":
        return None
    return "".join(b.text for b in r.content if b.type == "text")

SYSTEM = "あなたは社内 FAQ の回答担当です。"
