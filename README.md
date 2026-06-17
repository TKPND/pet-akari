# pet-akari

Akari pet theme の画像アセットパイプライン。[Clawd](https://github.com/nicholaschen09/ClaWd) デスクトップペット向けの APNG テーマを生成する。

## 概要

キャラクター「あかり」のペットテーマを、状態ごとに視覚的に区別できるアニメーション付きで生成するツール群。128-160px のデスクトップペットサイズでも、表情・ポーズ・動きだけで状態が判別できることを目標としている。

## セットアップ

```bash
# uv を使う場合
uv sync --extra dev

# pip を使う場合
pip install -e ".[dev]"
```

## ツール

| スクリプト | 説明 |
|---|---|
| `clawd_hq_theme.py` | HQ APNG テーマのビルドパイプライン |
| `akari_source_set_approval.py` | ソースセットの同一性検証 |
| `akari_full_motion_quality.py` | モーション品質チェック |
| `akari_phase3_staging.py` | Phase 3 ステージング処理 |
| `akari_phase4_gap_repair.py` | Phase 4 ギャップ修復 |
| `akari_phase4_visual_recognition.py` | Phase 4 視覚認識テスト |
| `akari_denser_motion.py` | 高密度モーション生成 |
| `strip_outline.py` | クロマキーストリップからアウトライン除去 |
| `extract_peeled.py` | ピール済みストリップからフレーム抽出 |
| `align_row.py` | フレーム行アライメント |
| `measure_edges.py` | エッジ測定ユーティリティ |
| `reorder_loop.py` | ループフレーム順序調整 |

Phase 4 の label-hidden human recognition gate は [docs/phase4-human-recognition.md](docs/phase4-human-recognition.md) を参照。

## テスト

```bash
uv run pytest
```

## Lint

```bash
uv run ruff check .
uv run ruff format --check .
```

## ライセンス

MIT
