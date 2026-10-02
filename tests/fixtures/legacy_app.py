# テスト用の「4.x 時代」のコード。scan.py がここの問題をすべて拾うことを確認する。
import anthropic
from datetime import datetime

client = anthropic.Anthropic()
MODEL = "claude-3-5-sonnet-20241022"           # H01

def ask(q):
    return client.beta.messages.create(
        model=MODEL,
        max_tokens=1024,                          # H11
        temperature=0.2,                          # H03
        betas=["interleaved-thinking-2025-05-14", "effort-2025-11-24"],   # H06
        thinking={"type": "enabled", "budget_tokens": 8000},               # H02
        system=f"今日は {datetime.now():%Y-%m-%d} です。CRITICAL: YOU MUST use the search tool.",  # H14 H13
        messages=[
            {"role": "user", "content": q},
            {"role": "assistant", "content": "{\"answer\": \""},            # H04
        ],
        tool_choice={"type": "any"},                                       # H07
        tools=[{"type": "text_editor_20250124", "name": "str_replace_editor"}],   # H12
    )

def read(r):
    return r.content[0].text                      # H10

def chat(messages):
    messages = messages[-10:]                     # H15
    r = client.messages.create(model="claude-opus-4-6-fast", max_tokens=16000, messages=messages,   # H16
                               thinking={"type": "disabled"}, output_config={"effort": "xhigh"})  # H08
    for b in r.content:
        if b.type == "thinking":
            print(b.thinking)                     # H09
    return r
