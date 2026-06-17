"""Import ChatGPT WebUI-generated Akari base PNGs for Phase 4 review."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pet_akari import clawd_hq_theme as hq

DEFAULT_OUTPUT_ROOT = Path("work/akari-hq-apng/phase4-webui-base-images")
DEFAULT_RUN_ID = "webui-base-001"
DEFAULT_CANVAS_SIZE = 1024
DEFAULT_PREVIEW_SIZES = (128, 160)
DEFAULT_BACKGROUND_TOLERANCE = 18
DEFAULT_PADDING_RATIO = 0.06
REQUIRED_STATES = hq.CORE_STATES


def ensure_dir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path, data):
    path = Path(path)
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _state_from_filename(path):
    stem = Path(path).stem.lower()
    for state in REQUIRED_STATES:
        if re.search(rf"(^|[-_]){re.escape(state)}($|[-_])", stem):
            return state
    return None


def collect_state_images(input_dir):
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        raise FileNotFoundError(input_dir)
    states = {}
    for path in sorted(input_dir.glob("*.png")):
        state = _state_from_filename(path)
        if state and state not in states:
            states[state] = path
    missing = [state for state in REQUIRED_STATES if state not in states]
    if missing:
        raise ValueError(f"missing required state image: {missing[0]}")
    return {state: states[state] for state in REQUIRED_STATES}
