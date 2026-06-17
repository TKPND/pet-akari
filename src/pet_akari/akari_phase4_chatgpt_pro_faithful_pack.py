"""Build a ChatGPT Pro Web request pack for Akari A Faithful candidates."""

from __future__ import annotations

import argparse
import json
import shutil
import tarfile
from pathlib import Path

from PIL import Image, ImageDraw

from pet_akari import clawd_hq_theme as hq


REQUIRED_STATES = hq.CORE_STATES
DEFAULT_SOURCE_DIR = Path.home() / "akari_clawd_base_images_include_hat"
DEFAULT_OUTPUT_ROOT = Path("work/akari-hq-apng/phase4-chatgpt-pro-faithful-pack")
DEFAULT_PACK_ID = "akari-stage2-faithful-pack"
DEFAULT_PREVIEW_SIZE = 180

SOURCE_FILENAMES = {
    "base": "000-base.png",
    "idle": "1-idle.png",
    "thinking": "2-thinking.png",
    "working": "3-working.png",
    "attention": "4-attention.png",
    "notification": "5-notification.png",
    "error": "6-error.png",
    "sleeping": "7-sleeping.png",
}

STATE_INTENTS = {
    "idle": "calm standing idle pose",
    "thinking": "thinking pose with small thinking cue",
    "working": "working at desk with laptop and notebook",
    "notification": "notification card and bell cue",
    "attention": "attention pose with star or callout cue",
    "error": "gentle error cue with concerned expression",
    "sleeping": "seated sleeping pose with small Zzz cue",
}


def ensure_dir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path, data):
    path = Path(path)
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def collect_source_images(source_dir):
    source_dir = Path(source_dir)
    if not source_dir.is_dir():
        raise FileNotFoundError(source_dir)
    base = source_dir / SOURCE_FILENAMES["base"]
    if not base.is_file():
        raise FileNotFoundError(base)
    states = {}
    for state in REQUIRED_STATES:
        path = source_dir / SOURCE_FILENAMES[state]
        if not path.is_file():
            raise FileNotFoundError(path)
        states[state] = path
    return {"base": base, "states": states}


def _manifest_states():
    return [
        {
            "state": state,
            "input": f"state_bases/{state}.png",
            "outputName": f"{state}-a-faithful.png",
            "stateIntent": STATE_INTENTS[state],
        }
        for state in REQUIRED_STATES
    ]


def write_manifest(pack_dir, pack_id=DEFAULT_PACK_ID):
    return write_json(
        Path(pack_dir) / "MANIFEST.json",
        {
            "candidateLane": "A Faithful",
            "objective": "Generate one A Faithful candidate for each completed state base.",
            "packId": pack_id,
            "referenceImage": "references/000-base.png",
            "schemaVersion": 1,
            "states": _manifest_states(),
        },
    )


def prompt_text():
    state_lines = "\n".join(
        f"- {state}: input `state_bases/{state}.png`, output `{state}-a-faithful.png`, intent: {STATE_INTENTS[state]}"
        for state in REQUIRED_STATES
    )
    return f"""# Akari A Faithful Candidate Request

最初の応答では画像生成しないでください。

まずこの tar.gz を展開し、`MANIFEST.json` と画像一覧を確認してください。その最初の応答では、以下だけを返してください。

1. tar.gz を展開できたか
2. `MANIFEST.json` と画像一覧を確認できたか
3. 各 state の入力画像と出力名を認識したか
4. state ごとの A Faithful 修正方針
5. 推奨生成順

その後、私が「A Faithful を生成して」と言ったら、state ごとに 1 枚ずつ画像生成してください。

## References

- Character identity reference: `references/000-base.png`
- Completed state bases:
{state_lines}

## A Faithful Requirements

- 入力 state 画像に最も忠実な候補にする
- `references/000-base.png` の顔、髪、帽子、服、バッグ、靴、配色、全体プロポーションを維持する
- state base のポーズ、表情、小物、state 意味を維持する
- 128-160px 表示でも state が読みやすいよう、線、小物サイズ、全身の収まりだけ軽く改善する
- 全身を切らない
- 背景、床、風景、影、説明ラベル、UI、文字を入れない
- 画像を結合しない。state ごとに 1 枚ずつ出力する
- 可能なら portrait PNG、できれば 1024x1536 相当
- transparent background is not required; local processing will remove plain backgrounds and fit assets into Clawd

## State Notes

- idle: 静かな待機姿勢。新しい小物や大きな感情表現を足さない。
- thinking: 考え中の表情や手元 cue を維持。思考 cue は小さく、顔や帽子を隠さない。
- working: 机、PC、ノートを維持。ただしキャラの全身と Clawd 表示で読みやすい自然なサイズ感にする。
- notification: 通知カードやベル cue を維持。カードは大きくしすぎない。
- attention: 星や注目 cue と呼びかけポーズを維持。cue はキャラから離しすぎない。
- error: 赤い error cue を維持。ただし怖くしすぎない。表情は困り顔寄り。
- sleeping: 座り寝姿と Zzz を維持。寝姿の silhouette が小さく潰れないようにする。

## Local Pipeline

ローカル側で透明化、縦横比維持 contain、384x480 変換、APNG 化、diff contact sheet、選別 UI を実行します。Web Chat 側で 384x480 APNG や完全な transparent PNG を作る必要はありません。
"""


def write_prompt(pack_dir):
    pack_dir = ensure_dir(pack_dir)
    output = pack_dir / "PROMPT.md"
    output.write_text(prompt_text(), encoding="utf-8")
    return output
