"""Build Phase 4 review diff packs for WebUI-imported Akari base images."""

from __future__ import annotations

import json
from pathlib import Path

from pet_akari import clawd_hq_theme as hq

DEFAULT_OUTPUT_ROOT = Path("work/akari-hq-apng/phase4-webui-diff-packs")
DEFAULT_PACK_ID = "webui-diff-001"
DEFAULT_PREVIEW_SIZES = (128, 160)
WEBUI_VALIDATION = Path("qa/webui-base-import-validation.json")
REQUIRED_STATES = hq.CORE_STATES
ALLOWED_DECISIONS = ("adopt", "hold", "reject")


def ensure_dir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path, data):
    path = Path(path)
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_json(path):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _normalized_paths(import_dir):
    import_dir = Path(import_dir)
    normalized_dir = import_dir / "normalized"
    paths = {}
    for state in REQUIRED_STATES:
        path = normalized_dir / f"{state}.png"
        if not path.is_file():
            raise FileNotFoundError(path)
        paths[state] = path
    return paths


def load_webui_import(import_dir):
    import_dir = Path(import_dir)
    validation_path = import_dir / WEBUI_VALIDATION
    validation = load_json(validation_path)
    if validation.get("status") == "fail":
        raise ValueError("WebUI import validation status is fail")
    state_order = validation.get("stateOrder")
    if state_order is not None and list(state_order) != list(REQUIRED_STATES):
        raise ValueError("WebUI import stateOrder must match hq.CORE_STATES")
    return {
        "importDir": import_dir,
        "normalizedPaths": _normalized_paths(import_dir),
        "validation": validation,
        "validationPath": validation_path,
    }
