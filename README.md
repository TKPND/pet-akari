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
| `akari_phase4_webui_base_import.py` | Phase 4 WebUI生成ベース画像の取り込み |
| `akari_phase4_candidate_batch.py` | Phase 4 修復候補のバッチ生成 |
| `akari_phase4_gap_repair.py` | Phase 4 ギャップ修復 |
| `akari_phase4_visual_recognition.py` | Phase 4 視覚認識テスト |
| `akari_denser_motion.py` | 高密度モーション生成 |
| `strip_outline.py` | クロマキーストリップからアウトライン除去 |
| `extract_peeled.py` | ピール済みストリップからフレーム抽出 |
| `align_row.py` | フレーム行アライメント |
| `measure_edges.py` | エッジ測定ユーティリティ |
| `reorder_loop.py` | ループフレーム順序調整 |

Phase 4 の label-hidden human recognition gate は [docs/phase4-human-recognition.md](docs/phase4-human-recognition.md) を参照。

Phase 4 の修復候補をまとめて探索する場合:

```bash
uv run python -m pet_akari.akari_phase4_candidate_batch build \
  --batch-id trial-001 \
  --max-candidates 27 \
  --clawd-validator /absolute/path/to/validate-theme.js
```

生成結果は `work/akari-hq-apng/phase4-candidate-batch/<batch-id>/` に出力される。`batch-contact-sheet.png` を見て候補を選び、選んだ candidate を既存の human recognition gate に通す。

### Phase 4 WebUI Base Import

ChatGPT WebUIで生成した、チェッカー背景が焼き込まれた状態別PNGを透明化・正規化し、レビュー用アセットに取り込む:

```bash
rtk uv run python -m pet_akari.akari_phase4_webui_base_import build \
  --input-archive work/akari-hq-apng/phase4-webui-base-images/raw/akari_clawd_base_images.tar.gz \
  --run-id webui-base-001
```

取り込み結果は ignored `work/` 配下に、正規化済みRGBA PNG、contact sheet、`qa/webui-base-import-validation.json` として出力される。視覚的な承認判定は自動化せず、人間レビューで確認する。

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
