# Phase 4 ChatGPT Pro Faithful Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic tar.gz request pack for ChatGPT Pro Web that asks for one A Faithful candidate per completed Akari `include_hat` state base.

**Architecture:** Add one focused CLI module, `pet_akari.akari_phase4_chatgpt_pro_faithful_pack`, that validates the `include_hat` source folder, copies references into a clean pack layout, writes `MANIFEST.json` and `PROMPT.md`, creates a contact sheet, and archives the pack. It only prepares request artifacts; it does not import generated results, modify theme assets, or call image generation.

**Tech Stack:** Python 3, Pillow, `tarfile`, JSON, `argparse`, `unittest`, existing `pet_akari.clawd_hq_theme` constants, ignored `work/` artifacts.

---

## File Structure

- Create: `src/pet_akari/akari_phase4_chatgpt_pro_faithful_pack.py`
  - Owns source validation, pack layout creation, prompt/manifest writing, contact sheet rendering, tar.gz archive creation, and CLI.
- Create: `tests/test_akari_phase4_chatgpt_pro_faithful_pack.py`
  - Uses small synthetic PNG fixtures to verify manifest content, prompt content, copied paths, contact sheet, archive contents, missing-file errors, and parser behavior.
- Modify: `README.md`
  - Add one tool row and one usage block for building the ChatGPT Pro faithful request pack.
- Do not modify:
  - `src/pet_akari/akari_phase4_webui_base_import.py`
  - `src/pet_akari/akari_phase4_webui_diff_pack.py`
  - `src/pet_akari/akari_phase4_webui_selection_theme.py`
  - Existing Clawd theme generation or validation behavior.

Generated artifacts under `work/akari-hq-apng/phase4-chatgpt-pro-faithful-pack/` are ignored and must not be staged.

---

### Task 1: Source Validation, Manifest, And Prompt

**Files:**
- Create: `src/pet_akari/akari_phase4_chatgpt_pro_faithful_pack.py`
- Create: `tests/test_akari_phase4_chatgpt_pro_faithful_pack.py`

- [ ] **Step 1: Write failing tests for source validation, manifest content, and prompt content**

Create `tests/test_akari_phase4_chatgpt_pro_faithful_pack.py` with:

```python
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pet_akari import akari_phase4_chatgpt_pro_faithful_pack as faithful_pack


class Phase4ChatgptProFaithfulPackTests(unittest.TestCase):
    def write_include_hat_source(self, root, *, omit=None):
        source_dir = root / "include_hat"
        source_dir.mkdir()
        files = {
            "000-base.png": (255, 120, 80),
            "1-idle.png": (20, 40, 60),
            "2-thinking.png": (40, 80, 120),
            "3-working.png": (60, 100, 140),
            "4-attention.png": (80, 120, 160),
            "5-notification.png": (100, 140, 180),
            "6-error.png": (120, 160, 200),
            "7-sleeping.png": (140, 180, 220),
        }
        for name, color in files.items():
            if name == omit:
                continue
            image = Image.new("RGB", (32, 48), "white")
            for x in range(8, 24):
                for y in range(10, 38):
                    image.putpixel((x, y), color)
            image.save(source_dir / name)
        return source_dir

    def test_collect_source_images_finds_base_and_all_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = self.write_include_hat_source(Path(tmp))

            images = faithful_pack.collect_source_images(source_dir)

            self.assertEqual(source_dir / "000-base.png", images["base"])
            self.assertEqual(list(faithful_pack.REQUIRED_STATES), list(images["states"]))
            self.assertEqual(source_dir / "3-working.png", images["states"]["working"])

    def test_collect_source_images_rejects_missing_state_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = self.write_include_hat_source(Path(tmp), omit="7-sleeping.png")

            with self.assertRaisesRegex(FileNotFoundError, "7-sleeping.png"):
                faithful_pack.collect_source_images(source_dir)

    def test_build_manifest_lists_a_faithful_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack_dir = Path(tmp) / "akari-stage2-faithful-pack"

            manifest_path = faithful_pack.write_manifest(pack_dir)

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(1, manifest["schemaVersion"])
            self.assertEqual("akari-stage2-faithful-pack", manifest["packId"])
            self.assertEqual("A Faithful", manifest["candidateLane"])
            self.assertEqual("references/000-base.png", manifest["referenceImage"])
            self.assertEqual(
                list(faithful_pack.REQUIRED_STATES),
                [entry["state"] for entry in manifest["states"]],
            )
            self.assertEqual("state_bases/working.png", manifest["states"][2]["input"])
            self.assertEqual("working-a-faithful.png", manifest["states"][2]["outputName"])
            self.assertIn("desk", manifest["states"][2]["stateIntent"])

    def test_write_prompt_uses_two_step_chatgpt_pro_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack_dir = Path(tmp) / "akari-stage2-faithful-pack"

            prompt_path = faithful_pack.write_prompt(pack_dir)

            prompt = prompt_path.read_text(encoding="utf-8")
            self.assertIn("最初の応答では画像生成しない", prompt)
            self.assertIn("A Faithful", prompt)
            self.assertIn("references/000-base.png", prompt)
            self.assertIn("state_bases/working.png", prompt)
            self.assertIn("1024x1536", prompt)
            self.assertIn("transparent", prompt.lower())
            self.assertIn("ローカル側", prompt)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_chatgpt_pro_faithful_pack.py -q
```

Expected: FAIL during collection with `ImportError: cannot import name 'akari_phase4_chatgpt_pro_faithful_pack'`.

- [ ] **Step 3: Add minimal module for validation, manifest, and prompt**

Create `src/pet_akari/akari_phase4_chatgpt_pro_faithful_pack.py` with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_chatgpt_pro_faithful_pack.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
rtk git add src/pet_akari/akari_phase4_chatgpt_pro_faithful_pack.py tests/test_akari_phase4_chatgpt_pro_faithful_pack.py
rtk git commit -m "feat: add chatgpt pro faithful pack manifest"
```

---

### Task 2: Pack Assets, Contact Sheet, And Archive

**Files:**
- Modify: `src/pet_akari/akari_phase4_chatgpt_pro_faithful_pack.py`
- Modify: `tests/test_akari_phase4_chatgpt_pro_faithful_pack.py`

- [ ] **Step 1: Add failing tests for full pack build and tar.gz archive contents**

Append these tests to `tests/test_akari_phase4_chatgpt_pro_faithful_pack.py`:

```python
import tarfile
```

Add methods inside `Phase4ChatgptProFaithfulPackTests`:

```python
    def test_build_faithful_pack_copies_assets_and_writes_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = self.write_include_hat_source(root)

            result = faithful_pack.build_faithful_pack(
                source_dir=source_dir,
                output_root=root / "out",
                pack_id="akari-stage2-faithful-pack",
                preview_size=64,
            )

            pack_dir = result["packDir"]
            self.assertTrue((pack_dir / "PROMPT.md").is_file())
            self.assertTrue((pack_dir / "MANIFEST.json").is_file())
            self.assertTrue((pack_dir / "references" / "000-base.png").is_file())
            self.assertTrue((pack_dir / "state_bases" / "idle.png").is_file())
            self.assertTrue((pack_dir / "state_bases" / "working.png").is_file())
            self.assertTrue(result["contactSheet"].is_file())
            self.assertTrue(result["archive"].is_file())

            with tarfile.open(result["archive"], "r:gz") as archive:
                names = set(archive.getnames())
            self.assertIn("akari-stage2-faithful-pack/PROMPT.md", names)
            self.assertIn("akari-stage2-faithful-pack/MANIFEST.json", names)
            self.assertIn("akari-stage2-faithful-pack/references/000-base.png", names)
            self.assertIn("akari-stage2-faithful-pack/state_bases/sleeping.png", names)
            self.assertIn("akari-stage2-faithful-pack/contact-sheets/state-bases.png", names)

    def test_write_contact_sheet_renders_state_bases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = self.write_include_hat_source(root)
            pack_dir = root / "pack"
            copied = faithful_pack.copy_pack_assets(source_dir, pack_dir)

            contact_sheet = faithful_pack.write_state_base_contact_sheet(
                pack_dir / "contact-sheets" / "state-bases.png",
                copied["stateBases"],
                preview_size=64,
            )

            self.assertTrue(contact_sheet.is_file())
            with Image.open(contact_sheet) as image:
                self.assertEqual((64 * 4, (64 + 22) * 2), image.size)
                self.assertEqual("RGB", image.mode)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_chatgpt_pro_faithful_pack.py -q
```

Expected: FAIL with missing `build_faithful_pack`, `copy_pack_assets`, or `write_state_base_contact_sheet`.

- [ ] **Step 3: Add asset copy, contact sheet, archive, and full build functions**

Append this implementation to `src/pet_akari/akari_phase4_chatgpt_pro_faithful_pack.py` before `_build_parser` if `_build_parser` already exists, or after `write_prompt` if Task 1 module has no parser yet:

```python
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
```

If the module does not yet import `tarfile`, `shutil`, `ImageDraw`, and `Image`, add those imports exactly as shown in Task 1.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_chatgpt_pro_faithful_pack.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 5: Commit Task 2**

Run:

```bash
rtk git add src/pet_akari/akari_phase4_chatgpt_pro_faithful_pack.py tests/test_akari_phase4_chatgpt_pro_faithful_pack.py
rtk git commit -m "feat: build chatgpt pro faithful pack archive"
```

---

### Task 3: CLI, README, And Real Smoke Build

**Files:**
- Modify: `src/pet_akari/akari_phase4_chatgpt_pro_faithful_pack.py`
- Modify: `tests/test_akari_phase4_chatgpt_pro_faithful_pack.py`
- Modify: `README.md`

- [ ] **Step 1: Add failing parser test**

Append this test method inside `Phase4ChatgptProFaithfulPackTests`:

```python
    def test_build_parser_accepts_build_command(self):
        args = faithful_pack._build_parser().parse_args(
            [
                "build",
                "--source-dir",
                "include_hat",
                "--output-root",
                "out",
                "--pack-id",
                "trial-pack",
                "--preview-size",
                "96",
            ]
        )

        self.assertEqual("build", args.command)
        self.assertEqual(Path("include_hat"), args.source_dir)
        self.assertEqual(Path("out"), args.output_root)
        self.assertEqual("trial-pack", args.pack_id)
        self.assertEqual(96, args.preview_size)
```

- [ ] **Step 2: Run parser test to verify it fails**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_chatgpt_pro_faithful_pack.py::Phase4ChatgptProFaithfulPackTests::test_build_parser_accepts_build_command -q
```

Expected: FAIL with missing `_build_parser`.

- [ ] **Step 3: Add CLI parser and main**

Append this to `src/pet_akari/akari_phase4_chatgpt_pro_faithful_pack.py`:

```python
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
```

- [ ] **Step 4: Run parser and full module tests**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_chatgpt_pro_faithful_pack.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 5: Update README tool list and usage**

Modify `README.md`.

In the tool table, add:

```markdown
| `akari_phase4_chatgpt_pro_faithful_pack.py` | ChatGPT Pro Web向けA Faithful依頼パック生成 |
```

After the Phase 4 WebUI selection theme section, add:

````markdown
### Phase 4 ChatGPT Pro Faithful Pack

Build a tar.gz request pack for ChatGPT Pro Web from the completed `include_hat` state bases:

```bash
rtk uv run python -m pet_akari.akari_phase4_chatgpt_pro_faithful_pack build \
  --source-dir ~/akari_clawd_base_images_include_hat
```

The pack is written under ignored `work/akari-hq-apng/phase4-chatgpt-pro-faithful-pack/` and contains `PROMPT.md`, `MANIFEST.json`, `references/000-base.png`, normalized state-base filenames, a state-base contact sheet, and `akari-stage2-faithful-pack.tar.gz`. It asks ChatGPT Pro to first inspect the pack and only generate A Faithful candidates after explicit confirmation.
````

- [ ] **Step 6: Run real smoke build with the actual include_hat source**

Run:

```bash
rtk uv run python -m pet_akari.akari_phase4_chatgpt_pro_faithful_pack build \
  --source-dir ~/akari_clawd_base_images_include_hat
```

Expected output includes:

```text
wrote work/akari-hq-apng/phase4-chatgpt-pro-faithful-pack/akari-stage2-faithful-pack.tar.gz
```

Verify archive contents:

```bash
rtk tar -tzf work/akari-hq-apng/phase4-chatgpt-pro-faithful-pack/akari-stage2-faithful-pack.tar.gz | rtk head -40
```

Expected archive entries include:

```text
akari-stage2-faithful-pack/MANIFEST.json
akari-stage2-faithful-pack/PROMPT.md
akari-stage2-faithful-pack/references/000-base.png
akari-stage2-faithful-pack/state_bases/idle.png
akari-stage2-faithful-pack/state_bases/sleeping.png
akari-stage2-faithful-pack/contact-sheets/state-bases.png
```

- [ ] **Step 7: Run full verification**

Run:

```bash
rtk uv run pytest && rtk uv run ruff check . && rtk uv run ruff format --check .
```

Expected: all tests pass, ruff check passes, format check passes.

- [ ] **Step 8: Commit Task 3**

Run:

```bash
rtk git add README.md src/pet_akari/akari_phase4_chatgpt_pro_faithful_pack.py tests/test_akari_phase4_chatgpt_pro_faithful_pack.py
rtk git commit -m "docs: document chatgpt pro faithful pack"
```

---

## Final Verification Checklist

After all tasks are complete, run:

```bash
rtk uv run pytest && rtk uv run ruff check . && rtk uv run ruff format --check .
rtk uv run python -m pet_akari.akari_phase4_chatgpt_pro_faithful_pack build \
  --source-dir ~/akari_clawd_base_images_include_hat
rtk tar -tzf work/akari-hq-apng/phase4-chatgpt-pro-faithful-pack/akari-stage2-faithful-pack.tar.gz | rtk head -40
rtk git status --short --branch
```

Completion requires:

- Test suite passes.
- Ruff check and format check pass.
- Real pack archive exists at `work/akari-hq-apng/phase4-chatgpt-pro-faithful-pack/akari-stage2-faithful-pack.tar.gz`.
- Archive contains `PROMPT.md`, `MANIFEST.json`, `references/000-base.png`, all 7 `state_bases/*.png`, and `contact-sheets/state-bases.png`.
- Git status is clean after commits, ignoring generated `work/` artifacts.
