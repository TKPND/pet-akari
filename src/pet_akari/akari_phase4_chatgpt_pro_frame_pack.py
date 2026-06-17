"""Build a ChatGPT Pro Web request pack for Akari animation frames."""

from __future__ import annotations

import argparse
import json
import shutil
import tarfile
from pathlib import Path

from PIL import Image, ImageDraw

from pet_akari import clawd_hq_theme as hq

REQUIRED_STATES = hq.CORE_STATES
DEFAULT_SOURCE_DIR = Path("work/akari-hq-apng/phase4-chatgpt-pro-faithful-pack/pro-faithful-raw")
DEFAULT_OUTPUT_ROOT = Path("work/akari-hq-apng/phase4-chatgpt-pro-faithful-pack")
DEFAULT_PACK_ID = "akari-pro-inbetween-frame-pack"
DEFAULT_BASE_REFERENCE = Path.home() / "akari_clawd_base_images_include_hat" / "000-base.png"
DEFAULT_PREVIEW_RUN_DIR = Path("work/akari-hq-apng/phase4-chatgpt-pro-faithful-pack") / "keypose-motion-preview-run"
DEFAULT_PREVIEW_SIZE = 180
REQUESTED_FRAME_COUNT = 8

STATE_INTENTS = {
    "idle": "quiet standing idle loop",
    "thinking": "thinking pose loop with small thinking cue",
    "working": "desk work loop with laptop, notebook, and pen",
    "notification": "notification cue loop with card and bell",
    "attention": "attention/callout loop with hand gesture and star cue",
    "error": "gentle error loop with red cue and worried expression",
    "sleeping": "seated sleeping loop with breathing and small Zzz cue",
}

STATE_MOTION_BRIEFS = {
    "idle": (
        "Subtle breathing, blink, tiny hoodie/hair/bag sway. The loop must be visibly alive at pet size, "
        "but no new props or large gestures."
    ),
    "thinking": (
        "Small head/eye movement, hand/chin pose variation, and a gentle thinking cue pulse. Keep the cue "
        "small and away from the face."
    ),
    "working": (
        "Keep the desk, laptop, notebook, and pen. Animate a small writing/typing rhythm, blink, and light "
        "body bob while keeping the desk stable."
    ),
    "notification": (
        "Keep the notification card and bell cue. Animate a small point/tap and a restrained cue pulse so it "
        "does not read like the working state."
    ),
    "attention": (
        "Animate the calling hand/arm and a compact star/callout cue. Make the attention gesture readable "
        "without adding extra floating clutter."
    ),
    "error": (
        "Animate a worried expression, slight card shake, and restrained red cue pulse. Keep it gentle, not "
        "scary or chaotic."
    ),
    "sleeping": (
        "Animate slow breathing, head nod, closed eyes, and a small Zzz drift. The seated silhouette should "
        "stay stable and readable."
    ),
}


def ensure_dir(path: Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, data: object) -> Path:
    path = Path(path)
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def collect_keypose_images(source_dir: Path) -> dict[str, Path]:
    source_dir = Path(source_dir)
    if not source_dir.is_dir():
        raise FileNotFoundError(source_dir)
    keyposes = {}
    for state in REQUIRED_STATES:
        exact = source_dir / f"{state}.png"
        matches = [exact] if exact.is_file() else sorted(source_dir.glob(f"*{state}*.png"))
        if not matches:
            raise FileNotFoundError(f"missing Pro keypose image for {state} under {source_dir}")
        keyposes[state] = matches[0]
    return keyposes


def _manifest_states() -> list[dict[str, object]]:
    return [
        {
            "state": state,
            "input": f"keyposes/{state}.png",
            "stateIntent": STATE_INTENTS[state],
            "motionBrief": STATE_MOTION_BRIEFS[state],
            "requestedFrameCount": REQUESTED_FRAME_COUNT,
            "preferredStripOutput": f"outputs/strips/{state}-8f.png",
            "preferredFrameDir": f"outputs/frames/{state}",
        }
        for state in REQUIRED_STATES
    ]


def write_manifest(pack_dir: Path, pack_id: str = DEFAULT_PACK_ID, *, include_base_reference: bool = True) -> Path:
    references = ["references/pro-idle-reference.png"]
    if include_base_reference:
        references.append("references/stage2-base.png")
    return write_json(
        Path(pack_dir) / "MANIFEST.json",
        {
            "schemaVersion": 1,
            "packId": pack_id,
            "objective": "Generate visible 8-frame source animation candidates from ChatGPT Pro keyposes.",
            "clawdContract": "clawd-on-desk/CONTRACT.md",
            "localPreview": "local-preview/current-local-motion-contact-sheet.png",
            "referenceImages": references,
            "outputContract": {
                "frameCountPerState": REQUESTED_FRAME_COUNT,
                "preferredArchiveName": "akari-pro-inbetween-frames.tar.gz",
                "preferredFrameRoot": "outputs/frames",
                "preferredStripRoot": "outputs/strips",
                "stripMode": "single horizontal strip per state, 8 equal-width cells, no labels or dividers",
            },
            "states": _manifest_states(),
        },
    )


def clawd_contract_text() -> str:
    return f"""# Clawd On Desk Contract For Akari

This request targets the Akari clawd-on-desk theme, not the generic 9-row Codex pet atlas.

## Runtime Contract

- States: {", ".join(REQUIRED_STATES)}
- Master frame size after local normalization: {hq.MASTER_SIZE[0]}x{hq.MASTER_SIZE[1]} RGBA
- Runtime APNG size: {hq.RUNTIME_SIZE[0]}x{hq.RUNTIME_SIZE[1]} RGBA
- Final frame duration: {hq.DEFAULT_DURATION_MS}ms
- Local exporter can insert in-betweens; the Web request should provide {REQUESTED_FRAME_COUNT} strong source keyframes.
- Local placement is bottom-aligned with a stable baseline. Do not create camera zooms or scale popping.

## Image Requirements For GPT Pro Outputs

- Prefer one horizontal strip per state: 8 equal-width cells, ordered left-to-right as frame 00 to frame 07.
- Individual PNG frames are also welcome if the Web UI can produce a file archive.
- Keep the same canvas ratio, character scale, style, face, orange hair, navy hat, teal jacket, cream hoodie,
  black shoulder bag, skirt, socks, and black/orange/teal shoes.
- Background should be transparent if available; otherwise use a flat plain white or near-white background.
- Do not include labels, frame numbers, visible guides, UI screenshots, scenery, floor shadows, drop shadows,
  borders, dividers, or explanatory text.
- Existing state cues may animate, but do not add unrelated new symbols.
"""


def write_clawd_contract(pack_dir: Path) -> Path:
    output = ensure_dir(Path(pack_dir) / "clawd-on-desk") / "CONTRACT.md"
    output.write_text(clawd_contract_text(), encoding="utf-8")
    return output


def expected_output_text() -> str:
    return """# Expected GPT Pro Output

Preferred archive layout if file generation/export is available:

```text
akari-pro-inbetween-frames/
  outputs/
    strips/
      idle-8f.png
      thinking-8f.png
      working-8f.png
      notification-8f.png
      attention-8f.png
      error-8f.png
      sleeping-8f.png
    frames/
      idle/00.png ... 07.png
      thinking/00.png ... 07.png
      working/00.png ... 07.png
      notification/00.png ... 07.png
      attention/00.png ... 07.png
      error/00.png ... 07.png
      sleeping/00.png ... 07.png
```

If archive export is not available, generate one state at a time and provide a single horizontal 8-frame strip.
The local pipeline can split strips, remove plain backgrounds, normalize, add in-betweens, encode APNG, and QA.
"""


def write_expected_output_readme(pack_dir: Path) -> Path:
    output = ensure_dir(Path(pack_dir) / "outputs-expected") / "README.md"
    output.write_text(expected_output_text(), encoding="utf-8")
    return output


def prompt_text() -> str:
    state_lines = "\n".join(
        f"- {state}: input `keyposes/{state}.png`, output strip `outputs/strips/{state}-8f.png`, "
        f"motion: {STATE_MOTION_BRIEFS[state]}"
        for state in REQUIRED_STATES
    )
    return f"""# Akari Pro In-Between Frame Request

最初の応答では画像生成しないでください。

まずこの tar.gz を展開し、`MANIFEST.json`、`clawd-on-desk/CONTRACT.md`、`keyposes/`、`references/`、`local-preview/` を確認してください。
最初の応答では以下だけを日本語で返してください。

1. tar.gz を展開できたか
2. `MANIFEST.json` と画像一覧を確認できたか
3. clawd-on-desk の 7 state / 8 source frames / 384x480 runtime 制約を認識したか
4. state ごとの 8コマ構成案
5. 推奨生成順

その後、私が「承認、生成して」と言ったら、可能なら state ごとに 8コマのソースフレームを生成してください。

## Your Role

あなたはアニメーション中割り作画と小型デスクトップマスコット用sprite制作に強いアートディレクターです。
目的は、すでにOK済みの高品質keyposeを壊さずに、Clawd上で「動いている」と分かる8コマ候補を作ることです。

## Inputs

- Identity references:
  - `references/pro-idle-reference.png`
  - `references/stage2-base.png` if present
- Current local preview reference:
  - `local-preview/current-local-motion-contact-sheet.png`
  - This is useful context, but its motion is too procedural/subtle. Do not merely copy this level of motion.
- State keyposes:
{state_lines}

## Output Format

Preferred:

- `outputs/strips/<state>-8f.png`
- One horizontal strip per state
- Exactly 8 equal-width cells, ordered frame 00 through frame 07 from left to right
- No visible cell borders, labels, frame numbers, guide marks, or text

Also helpful if file export is available:

- `outputs/frames/<state>/00.png` through `07.png`
- A final `akari-pro-inbetween-frames.tar.gz`

If the Web UI cannot export a tar.gz, generate one state at a time as a single 8-frame strip image.

## Animation Requirements

- 8枚は単なる複製ではなく、128-160px表示でも動きが分かる差分にする
- ただしキャラクター同一性、顔、髪、帽子、服、バッグ、靴、色、全体プロポーションは固定
- フレーム00を基準、フレーム04を動きの反対側または最大変化、フレーム07をフレーム00へ自然に戻る直前にする
- ループ時にスケール、足元、机、座り位置がガタつかないようにする
- 背景は透明、またはローカル処理しやすい単色白/薄灰色
- 文字、UI、説明ラベル、床、風景、影、フレーム枠を入れない
- 全身や状態小物を切らない
- 既存の state cue は維持してよいが、無関係な記号や新しい小物は足さない

## State Notes

- idle: 呼吸、まばたき、髪/服/バッグのごく小さな揺れ。大きな手振りや新しい小物は禁止。
- thinking: 考え顔、手元、思考cueを維持。cueは小さく、顔や帽子に被せない。
- working: 机、PC、ノート、ペンを維持。机は安定、手/ペン/視線だけで作業感を出す。
- notification: 通知カードとベルcueを維持。workingと見分けがつく通知らしい指差し/タップ/小さなpulse。
- attention: 呼びかけポーズ、手、星/注目cueを維持。遠くに散らさずコンパクトに。
- error: 赤いerror cue、困り顔、カードを維持。軽いshake/pulseで、怖くしすぎない。
- sleeping: 座り寝、閉じ目、Zzzを維持。呼吸と頭の小さな揺れ。座り姿勢は崩さない。

## Acceptance Checklist

- 各stateが8コマある
- stateごとに動きが見える
- 7 stateすべてで同じあかりに見える
- keyposeの魅力、服装、帽子、バッグ、靴、色が保たれている
- 低解像度でも idle / thinking / working / notification / attention / error / sleeping が区別できる
- ローカル側で透明化とAPNG化しやすい
"""


def write_prompt(pack_dir: Path) -> Path:
    output = ensure_dir(pack_dir) / "PROMPT.md"
    output.write_text(prompt_text(), encoding="utf-8")
    return output


def copy_pack_assets(
    source_dir: Path,
    pack_dir: Path,
    *,
    base_reference: Path | None = DEFAULT_BASE_REFERENCE,
    preview_run_dir: Path | None = DEFAULT_PREVIEW_RUN_DIR,
) -> dict[str, object]:
    keyposes = collect_keypose_images(source_dir)
    pack_dir = Path(pack_dir)
    keypose_dir = ensure_dir(pack_dir / "keyposes")
    reference_dir = ensure_dir(pack_dir / "references")
    copied_keyposes = {}
    for state, source in keyposes.items():
        output = keypose_dir / f"{state}.png"
        shutil.copy2(source, output)
        copied_keyposes[state] = output
    pro_idle = reference_dir / "pro-idle-reference.png"
    shutil.copy2(copied_keyposes["idle"], pro_idle)

    copied_base_reference = None
    if base_reference is not None and Path(base_reference).is_file():
        copied_base_reference = reference_dir / "stage2-base.png"
        shutil.copy2(base_reference, copied_base_reference)

    copied_preview = copy_optional_local_preview(preview_run_dir, pack_dir)
    return {
        "baseReference": copied_base_reference,
        "keyposes": copied_keyposes,
        "localPreview": copied_preview,
        "proIdleReference": pro_idle,
    }


def copy_optional_local_preview(preview_run_dir: Path | None, pack_dir: Path) -> dict[str, Path]:
    copied = {}
    if preview_run_dir is None:
        return copied
    preview_run_dir = Path(preview_run_dir)
    local_preview_dir = ensure_dir(Path(pack_dir) / "local-preview")
    contact_sheet = preview_run_dir / "qa" / "contact-sheet.png"
    if contact_sheet.is_file():
        output = local_preview_dir / "current-local-motion-contact-sheet.png"
        shutil.copy2(contact_sheet, output)
        copied["contactSheet"] = output
    summary = preview_run_dir / "qa" / "keypose-motion-summary.json"
    if summary.is_file():
        output = local_preview_dir / "keypose-motion-summary.json"
        shutil.copy2(summary, output)
        copied["summary"] = output
    return copied


def _render_tile(path: Path, preview_size: int) -> Image.Image:
    with Image.open(path) as image:
        frame = image.convert("RGBA")
    frame.thumbnail((preview_size, preview_size), hq._resample_filter())
    tile = Image.new("RGBA", (preview_size, preview_size), (245, 247, 250, 255))
    left = (preview_size - frame.width) // 2
    top = (preview_size - frame.height) // 2
    tile.alpha_composite(frame, (left, top))
    return tile


def write_keypose_contact_sheet(
    path: Path, state_paths: dict[str, Path], preview_size: int = DEFAULT_PREVIEW_SIZE
) -> Path:
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


def write_pack_tree(pack_dir: Path) -> Path:
    pack_dir = Path(pack_dir)
    lines = [f"{pack_dir.name}/"]
    for path in sorted(pack_dir.rglob("*")):
        if path.name == "tree.txt":
            continue
        relative = path.relative_to(pack_dir)
        prefix = "  " * len(relative.parts)
        suffix = "/" if path.is_dir() else ""
        lines.append(f"{prefix}{relative.name}{suffix}")
    output = pack_dir / "tree.txt"
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def write_archive(pack_dir: Path, archive_path: Path | None = None) -> Path:
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


def build_frame_pack(
    *,
    source_dir: Path = DEFAULT_SOURCE_DIR,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    pack_id: str = DEFAULT_PACK_ID,
    base_reference: Path | None = DEFAULT_BASE_REFERENCE,
    preview_run_dir: Path | None = DEFAULT_PREVIEW_RUN_DIR,
    preview_size: int = DEFAULT_PREVIEW_SIZE,
) -> dict[str, Path]:
    output_root = Path(output_root)
    pack_dir = output_root / pack_id
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    ensure_dir(pack_dir)
    copied = copy_pack_assets(
        source_dir,
        pack_dir,
        base_reference=base_reference,
        preview_run_dir=preview_run_dir,
    )
    prompt = write_prompt(pack_dir)
    manifest = write_manifest(pack_dir, pack_id=pack_id, include_base_reference=copied["baseReference"] is not None)
    clawd_contract = write_clawd_contract(pack_dir)
    expected_output = write_expected_output_readme(pack_dir)
    contact_sheet = write_keypose_contact_sheet(
        pack_dir / "contact-sheets" / "keyposes.png",
        copied["keyposes"],
        preview_size=preview_size,
    )
    tree = write_pack_tree(pack_dir)
    archive = write_archive(pack_dir)
    return {
        "archive": archive,
        "clawdContract": clawd_contract,
        "contactSheet": contact_sheet,
        "expectedOutput": expected_output,
        "manifest": manifest,
        "packDir": pack_dir,
        "prompt": prompt,
        "tree": tree,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build a ChatGPT Pro in-between frame request pack")
    build.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    build.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    build.add_argument("--pack-id", default=DEFAULT_PACK_ID)
    build.add_argument("--base-reference", type=Path, default=DEFAULT_BASE_REFERENCE)
    build.add_argument("--preview-run-dir", type=Path, default=DEFAULT_PREVIEW_RUN_DIR)
    build.add_argument("--preview-size", type=int, default=DEFAULT_PREVIEW_SIZE)
    build.add_argument("--no-base-reference", action="store_true")
    build.add_argument("--no-local-preview", action="store_true")
    return parser


def main(argv=None) -> None:
    args = _build_parser().parse_args(argv)
    if args.command == "build":
        result = build_frame_pack(
            source_dir=args.source_dir,
            output_root=args.output_root,
            pack_id=args.pack_id,
            base_reference=None if args.no_base_reference else args.base_reference,
            preview_run_dir=None if args.no_local_preview else args.preview_run_dir,
            preview_size=args.preview_size,
        )
        print(f"wrote {result['archive']}")


if __name__ == "__main__":
    main()
