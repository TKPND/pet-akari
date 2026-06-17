# Phase 4 WebUI Base Import 設計

日付: 2026-06-17
状態: brainstorming 承認済み
リポジトリ: pet-akari

## 目的

ChatGPT WebUI で生成したあかりの state 別 base PNG を、Phase 4 の視覚認識ループで扱える素材へ取り込む。

前回までの Phase 4 は、既存 APNG に対して attention、notification、error の cue をコードで足す方向だった。しかし、人間が見る state cue の良し悪しは実装を細かく詰めるより、複数案を見て選ぶ方が速い。今回生成した base images は、idle、thinking、working、attention、notification、error、sleeping の状態差がすでに強く出ている。

この設計では、WebUI 生成画像を raw input として保存し、Pillow だけで背景除去、crop、fit、preview、validation を行う。再生成は前提にしない。

## 入力素材

現時点の入力は次の場所へ退避済み。

```text
work/akari-hq-apng/phase4-webui-base-images/raw/
  akari_clawd_base_images.tar.gz
  akari_clawd_base_images/
    000-base.png
    1-idle.png
    2-thinking.png
    3-working.png
    4-attention.png
    5-notification.png
    6-error.png
    7-sleeping.png
    states_overview.png
```

`work/` は git ignore のままにする。raw input は再実行のために残すが、commit には含めない。

## 問題

WebUI 生成画像は見た目としては良いが、そのまま theme pipeline に入れるには次の問題がある。

- PNG は透明ではなく、チェッカー背景が画像として焼き込まれている。
- 各画像の canvas size が完全には揃っていない。
- `working` は机込みなので、128px pet tile に縮小するとキャラクター本体が小さくなりやすい。
- 背景除去を強くしすぎると、白い hoodie、肌、髪のハイライトまで削る危険がある。
- 過去の Phase 4 では `notification` が `working` と混同される失敗があったため、低解像度確認を省けない。

## 非目標

- ChatGPT WebUI で透明 PNG を再生成し直さない。
- rembg などの新しい画像処理依存を初期実装で追加しない。
- human recognition を自動分類器で置き換えない。
- 取り込み成功だけで `visualAcceptance: true` 相当にはしない。
- 既存の gap repair / candidate batch pipeline を壊したり置き換えたりしない。
- この段階では最終 Clawd theme release まで自動化しない。

## 推奨アプローチ

Pillow でチェッカー背景を透明化する importer を新規に追加する。

単純な色置換ではなく、画像端から到達できる背景領域だけを透明化する。背景候補は、画像端とその近傍から薄い白/グレーのチェッカーカラーを推定し、その色に近い edge-connected pixel として扱う。こうすると、人物内部にある白い hoodie や肌の明部が背景色に近くても、端から連結していなければ削られにくい。

背景除去後は、alpha が残った pixel の外接 bbox を取り、状態ごとに共通 canvas へ fit する。出力は静止 PNG の normalized base とし、後段で APNG/theme へ接続できる形にする。

## アーキテクチャ

新しい import module を追加する。

- `src/pet_akari/akari_phase4_webui_base_import.py`

責務は次に絞る。

- raw archive または raw directory から state PNG を発見する。
- 必須7 state が揃っているか確認する。
- チェッカー背景を透明化して `RGBA` PNG を作る。
- 外接 bbox と共通 canvas fit で normalized image を作る。
- normalized image の contact sheet と validation JSON を生成する。

既存 module との関係は次の通り。

- `akari_phase4_gap_repair` は既存 APNG 修復ルートとして残す。
- `akari_phase4_candidate_batch` はコード生成レシピ探索ルートとして残す。
- WebUI import は、静止 base 画像を取り込む別ルートとして追加する。
- 後段で theme/APNG 化が必要な場合は、import 結果を source image set として渡す小さな接続を別 plan で扱う。

## Data Flow

初期 CLI は次の流れにする。

1. input archive または input directory を受け取る。
2. raw input を run directory 配下へ copy する。
3. state filename を正規化して state map を作る。
4. 各 state 画像を `RGBA` に変換する。
5. edge-connected checker background を alpha 0 にする。
6. alpha bbox を計算し、padding を付けて crop する。
7. 共通 output canvas へ aspect-ratio preserving で fit する。
8. `normalized/<state>.png` を書き出す。
9. 128px/160px preview と contact sheet を作る。
10. validation JSON を書き出す。

出力 directory は次の形にする。

```text
work/akari-hq-apng/phase4-webui-base-images/<run-id>/
  raw/
  normalized/
    idle.png
    thinking.png
    working.png
    attention.png
    notification.png
    error.png
    sleeping.png
  qa/
    webui-base-import-validation.json
    contact-sheet-128.png
    contact-sheet-160.png
    background-removal-preview.png
```

## 背景除去

背景除去は deterministic な Pillow 処理にする。

- 画像を `RGBA` に変換する。
- 画像の四辺から sample pixels を集める。
- sample のうち、RGB 値が高く彩度が低いものを checker background palette として扱う。
- BFS または queue flood fill で、画像端から palette に近い pixel だけを訪問する。
- 訪問済み pixel の alpha を 0 にする。
- alpha 0 にした pixel 数、残った alpha bbox、端に残った opaque pixel 率を validation に記録する。

許容差は CLI option にできるが、default は固定値で始める。背景除去が強すぎる場合に備えて、validation JSON には crop 前後の bbox と retained pixel ratio を残す。

## Normalize / Fit

normalized image は、全 state を同じ output canvas に揃える。

初期 default は次の考え方にする。

- output canvas は `canvas-size x canvas-size` の正方形固定にする。
- 人物 bbox に少し padding を入れる。
- aspect ratio を維持して canvas 内に収める。
- 足元や座り姿が切れないよう、center fit を基本にする。
- `working` は机込みで bbox が広がるため、validation に「character area が小さくなりすぎていないか」を記録する。

最初の実装では state-specific manual crop は持たない。必要になったら、validation 結果を見て explicit override を追加する。

## Human Review

importer は visual acceptance を決めない。人間が見て判断するための artifact を作る。

contact sheet は次を満たす。

- state label を出す review 用と、label-hidden に近い確認用を分けられる。
- 128px と 160px の preview を作る。
- `notification` と `working` が混同されないかを重点確認できる。
- `attention`、`error`、`sleeping` の cue が低解像度でも残っているか確認できる。

人間確認が曖昧な場合は fail-closed にする。機械 validation が pass しても、`visualAcceptance` 相当は pending または false のままにする。

## Validation

validation JSON は、取り込み結果が review 可能かを判断するための構造チェックにする。

必須チェックは次の通り。

- 必須7 state が揃っている。
- 各 state の input image が読める。
- 各 output が `RGBA` である。
- 各 output に transparent pixel と opaque pixel の両方がある。
- alpha bbox が空ではない。
- normalized output size が全 state で揃っている。
- contact sheet が生成されている。
- 背景除去後、四辺に opaque checker が大量に残っていない。
- 背景除去で残った opaque pixel 率が低すぎない。

validation は `pass` / `fail` / `review` を持つ。機械的に破綻していれば `fail`、構造は通るが人間確認が必要なら `review` にする。

## Error Handling

importer は fail-closed にする。

- 入力 archive がない場合は non-zero exit。
- 必須 state が欠けている場合は non-zero exit。
- 1 state でも bbox が空になった場合は non-zero exit。
- 背景除去のメトリクスが危険域なら output は残すが status を `review` または `fail` にする。
- 例外時も run directory に可能な限り diagnostic JSON を残す。

画像処理で不確実なものを黙って accepted にしない。

## CLI

初期 CLI は次の形にする。

```bash
rtk uv run python -m pet_akari.akari_phase4_webui_base_import build \
  --input-archive work/akari-hq-apng/phase4-webui-base-images/raw/akari_clawd_base_images.tar.gz \
  --run-id webui-base-001
```

必要最小限の override は持たせる。

```bash
--input-dir <path>
--output-root work/akari-hq-apng/phase4-webui-base-images
--canvas-size 1024
--preview-sizes 128,160
--background-tolerance <int>
--padding-ratio <float>
```

`--input-archive` と `--input-dir` はどちらか一方だけ指定できる。

## Testing

テストは画像の芸術的な良し悪しではなく、import machinery と fail-closed behavior を見る。

- archive と directory の両 input path を扱える。
- filename から必須7 state を deterministic に解決できる。
- edge-connected background だけが透明化され、中央の白い foreground は残る。
- bbox が空の画像は fail する。
- normalized output size が揃う。
- validation JSON に background metrics と bbox が記録される。
- contact sheet が生成される。
- 必須 state 欠落は non-zero 相当の例外になる。

実画像を使う重い visual smoke は、unit test ではなく手動 run または optional smoke として扱う。

## Acceptance Criteria

- `/tmp` に依存せず、退避済み raw image set から importer を再実行できる。
- 1コマンドで raw copy、background removal、normalize、preview/contact sheet、validation JSON が生成される。
- 生成された normalized images は `RGBA` で transparent background を持つ。
- 128px/160px contact sheet で人間が state cue を確認できる。
- `notification` と `working` の混同リスクが validation/human review の明示項目になっている。
- 機械 validation が通っても human review なしに accepted 扱いしない。

## 初期スコープ決定

- 再生成はしない。現在の WebUI 生成 PNG を入力として使う。
- 背景除去は Pillow の edge-connected checker removal で実装する。
- 新規 dependency は追加しない。
- `work/` artifact は ignored のまま残す。
- 既存 gap repair / candidate batch は今回の初期実装では変更しない。
