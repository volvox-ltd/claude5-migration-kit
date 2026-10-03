# claude5-migration-kit

> Claude Opus 5.5 / Sonnet 5.5 / Opus 5 / Sonnet 5 / Fable 5.1 への移行で **400 になる箇所** と **黙って挙動が変わる箇所** を、既存コードから静的に見つけるツール。
> 解説: [Claude 5 世代 移行ガイド（Zenn 本）](https://zenn.dev/persimmoq/books/claude-5-migration-guide) ／ [model だけ変えて移行すると壊れる 7 つの理由（記事）](https://zenn.dev/persimmoq/articles/claude-opus-5-migration-400-errors)

Zenn 本『Claude 5 世代 移行ガイド ― Opus 5.5 / Sonnet 5.5 / Fable 5.1 で変わった API とプロンプト』の付属ツールです。2026-10-03: Opus 5.5（9/22）・Sonnet 5.5（9/28）に対応しました（`--target opus-5-5|sonnet-5-5`、H18 / H19 追加）。

| ツール | API | 用途 |
|---|---|---|
| `scan.py` | 不要 | コードを静的に走査し、移行で **400 になる箇所（BLOCKS）** と **黙って挙動が変わる箇所（TUNE）** を file:line で列挙。`--fail-on-blocks` で CI に |
| `prompt_audit.py` | 不要 | プロンプト・スキル・ツール説明から「旧世代向けの癖」（圧力表現、思考の指示、数値制限、化石）を拾う |
| `rebaseline_tokens.py` | 要 | 同じプロンプトを旧モデルと新モデルで `count_tokens` し、トークン数の変化を表にする |
| `cache_probe.py` | 要 | 同じリクエストを 2 回送り、キャッシュが効いているかを usage で確かめる（CI 可） |
| `effort_sweep.py` | 要 | 評価セットを effort ごとに流し、合格率と 1 件あたり費用を並べる |
| `history_check.py` | 要 | Fable 5.1 の preserved thinking（履歴編集の検査）に自分のループが耐えるか確かめる |
| `refusal_fallback_demo.py` | 要 | `stop_reason: refusal` の扱いと `fallbacks: "default"` の opt-in |

```bash
pip install -r requirements.txt
python scan.py path/to/your/app --target opus-5-5        # まずこれ（sonnet-5-5 / opus-5 / sonnet-5 / fable-5-1 も可）
python prompt_audit.py path/to/prompts
python tests/test_scan.py                                 # ツール自体の検証（ネットワーク不要）
```

`scan.py` と `prompt_audit.py` は候補を漏れなく出す側に倒してあります。誤検知を含むので、最終判断は本文の該当章を参照してください。

## ハザード一覧（scan.py）

| ID | 重大度 | 対象 | 内容 |
|---|---|---|---|
| H01 | BLOCKS | 全 | 引退済み・引退予定のモデル ID（Sonnet 4.5 は 2026-11-30 引退） |
| H02 | BLOCKS | 全 | `budget_tokens` / `type: enabled` |
| H03 | BLOCKS | 全 | `temperature` / `top_p` / `top_k` |
| H04 | BLOCKS | 全 | 末尾アシスタントターンのプリフィル |
| H05 | BLOCKS | 全 | `messages.create()` の `output_format` |
| H06 | TUNE | 全 | 古い・非推奨のベータヘッダ |
| H07 | BLOCKS | Opus 5.5, Sonnet 5.5, Fable 5.1 | `tool_choice` any / tool |
| H08 | BLOCKS | Opus 5, Opus 5.5, Sonnet 5.5, Fable 5.1 | `thinking: disabled`（Sonnet 5.5 は `between_tools` へ） |
| H09 | TUNE | 全 | thinking 本文を読んでいる（既定で空になる） |
| H10 | TUNE | 全 | `stop_reason` を見ずに `content[0]` |
| H11 | TUNE | 5 系すべて | 小さい `max_tokens` |
| H12 | BLOCKS | 全 | 古いツールバージョン |
| H13 | TUNE | 全 | 旧世代向けのプロンプト定型句 |
| H14 | TUNE | 全 | システムプロンプトの時刻・乱数（キャッシュ無効化） |
| H15 | TUNE | Opus 5.5, Sonnet 5.5, Fable 5.1 | 履歴の先頭・途中を削っている |
| H16 | BLOCKS | 全 | `-fast` 付きモデル ID |
| H17 | TUNE | Opus 5.5, Sonnet 5.5, Fable 5.1 | システムプロンプトを毎回組み立てている |
| H18 | BLOCKS | Opus 5.5, Sonnet 5.5 | `computer_20251124` / `computer_20250124`（Claude API / GCP はツールセットへ） |
| H19 | BLOCKS | Sonnet 5.5 | executor が Sonnet 5.5 のとき使えない advisor（Opus 4.x / Sonnet 5 / 4.6） |

## ライセンス

MIT
