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


def copy_pack_assets(source_dir, pack_dir):
    source_images = collect_source_images(source_dir)
    pack_dir = Path(pack_dir)
    references_dir = ensure_dir(pack_dir / "references")
    state_bases_dir = ensure_dir(pack_dir / "state_bases")
    reference_output = references_dir / "000-base.png"
    shutil.copy2(source_images["base"], reference_output)
    state_outputs = {}
    for state, source_path in source_images["states"].items():
        output = state_bases_dir / f"{state}.png"
        shutil.copy2(source_path, output)
        state_outputs[state] = output
    return {"reference": reference_output, "stateBases": state_outputs}


def _render_tile(path, preview_size):
    with Image.open(path) as image:
        frame = image.convert("RGBA")
    frame.thumbnail((preview_size, preview_size), hq._resample_filter())
    tile = Image.new("RGBA", (preview_size, preview_size), (245, 247, 250, 255))
    left = (preview_size - frame.width) // 2
    top = (preview_size - frame.height) // 2
    tile.alpha_composite(frame, (left, top))
    return tile


def write_state_base_contact_sheet(path, state_paths, preview_size=DEFAULT_PREVIEW_SIZE):
    path = Path(path)
    ensure_dir(path.parent)
    columns = 4
    label_height = 22
    rows = (len(REQUIRED_STATES) + columns - 1) // columns
    sheet = Image.new(
        "RGBA",
        (columns * preview_size, rows * (preview_size + label_height)),
        (245, 247, 250, 255),
    )
    draw = ImageDraw.Draw(sheet)
    for index, state in enumerate(REQUIRED_STATES):
        tile = _render_tile(state_paths[state], preview_size)
        column = index % columns
        row = index // columns
        left = column * preview_size
        top = row * (preview_size + label_height)
        sheet.alpha_composite(tile, (left, top))
        draw.text((left + 6, top + preview_size + 4), state, fill=(20, 24, 32, 255))
    sheet.convert("RGB").save(path)
    return path


def write_archive(pack_dir, archive_path=None):
    pack_dir = Path(pack_dir)
    archive_path = Path(archive_path) if archive_path else pack_dir.parent / f"{pack_dir.name}.tar.gz"
    ensure_dir(archive_path.parent)
    if archive_path.exists():
        archive_path.unlink()
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in sorted(pack_dir.rglob("*")):
            if path.is_file():
                archive.add(path, arcname=Path(pack_dir.name) / path.relative_to(pack_dir))
    return archive_path


def build_faithful_pack(
    *,
    source_dir=DEFAULT_SOURCE_DIR,
    output_root=DEFAULT_OUTPUT_ROOT,
    pack_id=DEFAULT_PACK_ID,
    preview_size=DEFAULT_PREVIEW_SIZE,
):
    output_root = Path(output_root)
    pack_dir = output_root / pack_id
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    ensure_dir(pack_dir)
    copied = copy_pack_assets(source_dir, pack_dir)
    manifest = write_manifest(pack_dir, pack_id=pack_id)
    prompt = write_prompt(pack_dir)
    contact_sheet = write_state_base_contact_sheet(
        pack_dir / "contact-sheets" / "state-bases.png",
        copied["stateBases"],
        preview_size=preview_size,
    )
    archive = write_archive(pack_dir)
    return {
        "archive": archive,
        "contactSheet": contact_sheet,
        "manifest": manifest,
        "packDir": pack_dir,
        "prompt": prompt,
    }


def _build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build a ChatGPT Pro A Faithful request pack")
    build.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    build.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    build.add_argument("--pack-id", default=DEFAULT_PACK_ID)
    build.add_argument("--preview-size", type=int, default=DEFAULT_PREVIEW_SIZE)
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    if args.command == "build":
        result = build_faithful_pack(
            source_dir=args.source_dir,
            output_root=args.output_root,
            pack_id=args.pack_id,
            preview_size=args.preview_size,
        )
        print(f"wrote {result['archive']}")


if __name__ == "__main__":
    main()
