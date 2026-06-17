# Phase 4 ChatGPT Pro Faithful Pack Design

## Goal

`~/akari_clawd_base_images_include_hat` の完成済み state base から、ChatGPT Pro Web で最初の A Faithful 候補を生成するための tar.gz 依頼パックを定義する。

この設計では、ChatGPT Pro Web は画像生成の微改善だけを担当する。Clawd 仕様への収め込み、透明化、`384x480` contain、APNG 化、diff contact sheet、選別 UI はローカルパイプラインで保証する。

## Context

`include_hat` には以下の完成形 state base がある。

- `000-base.png`
- `1-idle.png`
- `2-thinking.png`
- `3-working.png`
- `4-attention.png`
- `5-notification.png`
- `6-error.png`
- `7-sleeping.png`

これらは「修正前素材」ではなく、各 state の正規ベースとして扱う。今回の目的は、正規ベースを壊さずに ChatGPT Pro の生成適性を確認することなので、A-E の全候補生成には進まず、まず A Faithful だけを全 state で試す。

## Clawd Constraints

ローカル Clawd theme の固定仕様は以下。

- Runtime asset size: `384x480`
- Core states: `idle`, `thinking`, `working`, `notification`, `attention`, `error`, `sleeping`
- Theme asset names: `assets/akari-<state>.apng`
- Additional states `juggling`, `sweeping`, `carrying` map to `working`
- Local pipeline must generate APNG assets, validate them, and create diff QA artifacts

ChatGPT Pro Web には厳密な runtime サイズを作らせない。生成結果は portrait PNG を期待し、最終的な Clawd 適合はローカル側で行う。

## Web Chat Assumptions

OpenAI の公開情報から、以下を前提にする。

- ChatGPT の画像入力として明示されているのは PNG、JPEG、非アニメ GIF。
- ChatGPT の通常ファイルアップロードは利用できる。tar.gz は依頼パックとして使うが、アーカイブ内 PNG を画像参照として使えない場合は、同じ `PROMPT.md` と `MANIFEST.json` を使い、`references/000-base.png` と対象 `state_bases/*.png` を個別アップロードする運用へ切り替える。
- `gpt-image-2` は API 上では `1024x1536` などの portrait サイズや柔軟な解像度に対応するが、Web Chat でピクセル単位の出力制御を保証しない。
- `gpt-image-2` は透明背景をサポートしないため、透明化はローカル処理で行う。

そのため、PROMPT では `1024x1536 portrait preferred` 程度に留め、透明背景は必須条件にしない。背景は「plain, removable, no scenery, no shadow」に寄せる。

## Pack Layout

作成する tar.gz は以下の構成にする。

```text
akari-stage2-faithful-pack.tar.gz
├── MANIFEST.json
├── PROMPT.md
├── references/
│   └── 000-base.png
└── state_bases/
    ├── idle.png
    ├── thinking.png
    ├── working.png
    ├── notification.png
    ├── attention.png
    ├── error.png
    └── sleeping.png
```

`references/000-base.png` はキャラクター同一性の基準として使う。`state_bases/*.png` は各 state のポーズ、表情、小物、意味の基準として使う。

## Manifest Contract

`MANIFEST.json` は、ChatGPT Pro が対象を誤認しないための機械可読インデックスにする。

```json
{
  "schemaVersion": 1,
  "packId": "akari-stage2-faithful-pack",
  "objective": "Generate one A Faithful candidate for each completed state base.",
  "referenceImage": "references/000-base.png",
  "candidateLane": "A Faithful",
  "states": [
    {
      "state": "idle",
      "input": "state_bases/idle.png",
      "outputName": "idle-a-faithful.png",
      "stateIntent": "calm standing idle pose"
    }
  ]
}
```

実際の manifest では 7 state すべてを列挙する。

## Prompt Contract

`PROMPT.md` は二段構えにする。

最初の応答では生成しない。ChatGPT Pro には以下を返してもらう。

1. tar.gz を展開できたか
2. `MANIFEST.json` と画像一覧を確認できたか
3. 各 state の入力画像と出力名を認識したか
4. state ごとの A Faithful 修正方針
5. 推奨生成順

その確認後に、ユーザーが「A Faithful を生成して」と指示してから画像生成する。

## A Faithful Requirements

全 state 共通の生成要件:

- 入力 state 画像に最も忠実な候補にする
- `references/000-base.png` の顔、髪、帽子、服、バッグ、靴、配色、全体プロポーションを維持する
- state base のポーズ、表情、小物、state 意味を維持する
- 128-160px 表示でも state が読みやすいよう、線、小物サイズ、全身の収まりだけ軽く改善する
- 全身を切らない
- 背景、床、風景、影、説明ラベル、UI、文字を入れない
- 画像を結合しない。state ごとに 1 枚ずつ出力する
- 可能なら portrait PNG、できれば `1024x1536` 相当

State-specific notes:

- `idle`: 静かな待機姿勢。新しい小物や大きな感情表現を足さない。
- `thinking`: 考え中の表情や手元 cue を維持。思考 cue は小さく、顔や帽子を隠さない。
- `working`: 机、PC、ノートを維持。ただしキャラの全身とClawd表示で読みやすい自然なサイズ感にする。
- `notification`: 通知カードやベル cue を維持。カードは大きくしすぎない。
- `attention`: 星や注目 cue と呼びかけポーズを維持。cue はキャラから離しすぎない。
- `error`: 赤い error cue を維持。ただし怖くしすぎない。表情は困り顔寄り。
- `sleeping`: 座り寝姿と Zzz を維持。寝姿の silhouette が小さく潰れないようにする。

## Acceptance Criteria

ChatGPT Pro から受け取る成果物の合格条件:

- 7 state それぞれに A Faithful 候補が 1 枚ある
- キャラ同一性が `000-base.png` と一致している
- 各 state の意味が state base から変わっていない
- 全身が切れていない
- 背景や影がローカル透明化を邪魔しない
- 文字、UI、説明ラベルが入っていない
- ローカル取り込み後、縦横比維持 contain と APNG validation を通せる
- diff contact sheet で state base と候補を比較できる

## Out of Scope

- A-E の 5 候補を全 state で一括生成すること
- ChatGPT Pro に `384x480` APNG を直接作らせること
- ChatGPT Pro に透明背景を保証させること
- Clawd theme へ即採用すること
- 現行 theme asset を参照画像として使うこと

## OpenAI Source Notes

- ChatGPT image inputs: PNG, JPEG, non-animated GIF are the explicitly documented image input formats. Source: <https://help.openai.com/en/articles/8400551-chatgpt-image-inputs-faq>
- ChatGPT file uploads: ordinary file uploads have size and usage limits, so tar.gz pack size must stay small. Source: <https://help.openai.com/en/articles/8555545-file-uploads-faq>
- OpenAI API image generation: `gpt-image-2` supports flexible sizes in the API, including portrait options, but transparent backgrounds are not supported by that model. Source: <https://developers.openai.com/api/docs/guides/image-generation>
