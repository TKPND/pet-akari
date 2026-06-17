# Phase 4 候補バッチ設計

日付: 2026-06-17
状態: planning 承認済み
リポジトリ: pet-akari

## 目的

Phase 4 の視覚修復ループを軽くするため、コード生成だけで複数の修復候補をまとめて作り、label-hidden human recognition で人間が最も良い方向を選べるようにする。

今の進め方は、1つの修復案を丁寧に作って、theme 生成、preview 生成、人間判定まで毎回通している。これは正確ではあるけれど、A04/A05 のような「人間にどう見えるか」が本質の問題では試行錯誤が重い。

この設計では、1候補ずつ固めるのではなく、小さな候補農場を作る。曖昧な state だけを複数レシピで差し替え、同じ条件の preview に並べ、人間が早く選べる形にする。

## 問題

現在の修復ループには次の問題がある。

- 1つの実装変更ごとに theme を作り直し、recognition pass を回す必要がある。
- 自動テストは構造的な破綻を検出できるが、128-160px で人間が即認識できるかは予測しきれない。
- 直近の候補は fail-closed になった。A04 と A05 は answer key と逆に見え、A05 は low confidence、A06 は error と当たったが low confidence で、右側の謎アーティファクトも邪魔だった。

この段階の作業は、正しさ証明より探索に近い。最短経路は探索コストを下げること。

## 非目標

- human recognition を自動分類器で置き換えない。
- この段階では image generation を導入しない。
- batch 結果から Clawd theme を自動 package/release しない。
- idle、thinking、working、sleeping は初期 batch では変更しない。
- compatibility、face-zone、pairwise metrics が通っただけで候補を accepted 扱いにしない。

## 推奨アプローチ

parameterized recipe grid を使う。

各 candidate は state-local repair recipe の組み合わせで表す。

- `attention`: `raised-hand-only`, `check-badge`, `small-star-side`
- `notification`: `permission-card`, `message-bubble`, `bell-side`
- `error`: `lower-x-only`, `broken-card-lower`, `alert-panel-lower`

初期 batch は `attention x notification x error = 3 x 3 x 3` の 27 候補を生成する。各 candidate について既存の compatibility validation と visual-recognition artifact 生成を流し、batch 全体の contact sheet を作る。人間は contact sheet を見て、有望な候補を選ぶか、batch 全体を reject する。

## アーキテクチャ

新しい batch orchestration module を追加する。

- `src/pet_akari/akari_phase4_candidate_batch.py`

既存 pipeline はできるだけ再利用する。

- `akari_phase4_gap_repair` は、frame repair、theme export、validation、candidate ごとの visual recognition artifact 生成を引き続き担当する。
- `akari_phase4_visual_recognition` は、answer key、label-hidden preview、recognition template、最終 recognition validation を引き続き担当する。
- `clawd_hq_theme` は、APNG/theme contract 層としてそのまま使う。

修復モジュールには、recipe 選択を狭い interface として追加する。batch runner はその recipe choices を渡すだけで、build pipeline 全体を複製しない。

## Candidate データモデル

candidate は次の情報を持つ。

- `candidateId`: `C001` のような安定した短い ID。
- `recipes`: state から recipe id への mapping。
- `runDir`: candidate の出力 directory。
- `themeDir`: repaired theme の path。
- `validationJson`: compatibility-only repair validation の path。
- `visualRecognitionJson`: pending または validated recognition evidence の path。
- `previewPaths`: 128px / 160px、light / dark の label-hidden preview path。
- `status`: `built`, `invalid`, `selected`, `rejected`。
- `notes`: machine note または human note。

batch 出力先は次の形にする。

```text
work/akari-hq-apng/phase4-candidate-batch/<batch-id>/
  batch-manifest.json
  batch-contact-sheet.png
  selection-template.json
  candidate-C001/
  candidate-C002/
  ...
```

生成される `work/` artifact は git ignore のままにする。

## Batch Contact Sheet

batch contact sheet は、人間が候補を比較するための主画面になる。

初期版では、各 candidate を1行で表示する。

- candidate id だけを表示する。
- state label は表示しない。
- 128px light preview から A04/A05/A06 tile を切り出して並べる。
- 128px を優先する。ここが一番認識が難しいため。

各 candidate directory には full A01-A07 preview も残す。batch sheet は、今 recognition で落ちている A04/A05/A06 に集中する。

## Human Selection Flow

human review は2段階にする。

1. `batch-contact-sheet.png` を見て、最も有望な candidate を1つ選ぶ。良い候補がなければ batch 全体を reject する。
2. 選ばれた candidate に対して、既存の label-hidden recognition gate を実行する。

最終 recognition gate では次を集める。

- A01-A07 それぞれの guessed state。
- 各 tile の confidence。
- sleeping、error、attention、notification の cue notes。

選ばれた candidate も、次のどれかに該当すれば fail-closed のままにする。

- required answer が間違っている。
- confidence が low。
- cue notes が欠けている。
- human reviewer が reject している。

## Validation

candidate ごとの自動 validation は軽量で構造的なものに留める。

- theme export が成功する。
- Clawd validator が pass する。
- runtime asset hash が正しく bind される。
- attention、notification、error の protected face zone が変更されない。
- pet size で cue pixel が存在する。
- face-crop distinctness artifact が生成される。
- label-hidden preview が生成される。

これらは「review 可能か」を決めるための gate であり、visual acceptance を決めるものではない。

## Error Handling

batch runner は、可能な限り invalid candidate をまたいで処理を続ける。

- recipe combination が export または validation で失敗したら、その candidate を `invalid` にし、例外 text を記録する。
- 全 candidate が失敗した場合は non-zero exit にし、診断用 manifest を残す。
- 一部 candidate が pass した場合は、valid candidate だけで batch contact sheet を作り、invalid candidate も `batch-manifest.json` に残す。

1つの recipe が壊れていても探索全体を止めない。

## CLI

初期 CLI は次の形にする。

```bash
rtk uv run python -m pet_akari.akari_phase4_candidate_batch build \
  --batch-id <id> \
  --max-candidates 27 \
  --clawd-validator <path>
```

recipe override flags も初期実装に含める。ただし通常実行では defaults だけで使えるようにする。

```bash
--attention-recipes raised-hand-only,check-badge,small-star-side
--notification-recipes permission-card,message-bubble,bell-side
--error-recipes lower-x-only,broken-card-lower,alert-panel-lower
--include-all-states
```

`--include-all-states` は contact sheet に A01-A07 全部を出したいときだけ使う。default は A04/A05/A06 に絞る。

## Testing

テストは visual truth ではなく batch machinery を確認する。

- recipe grid expansion が deterministic で、`--max-candidates` に従う。
- invalid candidate が batch 全体を abort せず manifest に記録される。
- valid candidate が manifest entry と preview path を持つ。
- batch contact sheet が state label を出さず、candidate id を出す。
- selection template が candidate id と required recognition fields を参照する。

既存の repair tests は、face-zone と pet-size structural gate を引き続き守る。

## Acceptance Criteria

- 1コマンドで複数の Phase 4 repair candidate を ignored `work/` batch directory に生成できる。
- 各 valid candidate が repaired theme artifact と label-hidden preview を持つ。
- batch contact sheet で、人間が answer label を見ずに candidate を比較できる。
- batch manifest が recipe choices、validation status、artifact paths を記録する。
- selected candidate は既存 recognition validation path を使い、human recognition が通るまで fail-closed のままになる。

## 初期スコープ決定

- default batch size は 27。attention、notification、error の 3 x 3 x 3 recipe grid を全探索する。
- 最初の batch contact sheet は candidate id と A04/A05/A06 の 128px light tile を表示する。
- selection 後も rejected candidate directory は消さない。失敗 evidence を見比べられるようにする。
