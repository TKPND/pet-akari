"""Build a repaired Phase 4 candidate for the visual-recognition gap."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageSequence

from pet_akari import akari_phase3_staging as phase3
from pet_akari import akari_phase4_visual_recognition as vr
from pet_akari import clawd_hq_theme as hq

DEFAULT_SOURCE_THEME = Path("work/akari-hq-apng/phase3-staging/theme")
DEFAULT_SOURCE_PHASE4_EVIDENCE = Path("work/akari-hq-apng/phase4-visual-recognition/qa/phase4-visual-recognition.json")
DEFAULT_RUN_DIR = Path("work/akari-hq-apng/phase4-gap-repair")
MIN_REPAIR_CUE_CANVAS = 24
REPAIR_TARGETS = ("attention", "error", "notification", "sleeping")
DEFAULT_REPAIR_RECIPES = {
    "attention": "small-star-side",
    "notification": "permission-card",
    "error": "broken-card-lower",
}
REPAIR_RECIPES = {
    "attention": ("raised-hand-only", "check-badge", "small-star-side"),
    "notification": ("permission-card", "message-bubble", "bell-side"),
    "error": ("lower-x-only", "broken-card-lower", "alert-panel-lower"),
}


@dataclass(frozen=True)
class GapRepairResult:
    run_dir: Path
    masters_dir: Path
    theme_dir: Path
    validation_json: Path
    visual_qa_dir: Path
    visual_recognition_json: Path


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


def resolve_repair_recipes(overrides=None):
    recipes = dict(DEFAULT_REPAIR_RECIPES)
    for state, recipe in (overrides or {}).items():
        if state not in REPAIR_RECIPES:
            raise ValueError(f"unknown repair recipe target: {state}")
        if recipe not in REPAIR_RECIPES[state]:
            raise ValueError(f"unknown {state} repair recipe: {recipe}")
        recipes[state] = recipe
    return recipes


def _display_frames(path):
    with Image.open(path) as image:
        frames = [frame.copy().convert("RGBA") for frame in ImageSequence.Iterator(image)]
        if image.info.get("default_image") and len(frames) > 1:
            frames = frames[1:]
    if not frames:
        raise ValueError(f"{path} has no APNG display frames")
    return frames


def _source_phase3_validation(source_evidence):
    phase3_path = source_evidence.get("inputs", {}).get("phase3Validation", {}).get("path")
    if not phase3_path:
        raise ValueError("source Phase 4 evidence must record inputs.phase3Validation.path")
    return Path(phase3_path)


def _validate_source_evidence(path):
    evidence = load_json(path)
    if evidence.get("visualAcceptance") is not False:
        raise ValueError("source Phase 4 evidence must have visualAcceptance false")
    recognition = evidence.get("recognition", {})
    if recognition.get("status") != "rejected":
        raise ValueError("source Phase 4 evidence must have rejected recognition status")
    failed = recognition.get("failedChecks") or evidence.get("validationChecks", {}).get("failed") or []
    failed_text = json.dumps(failed, sort_keys=True)
    has_a04_a05 = "A04" in failed_text and "A05" in failed_text
    has_attention_notification = "attention" in failed_text and "notification" in failed_text
    if not (has_a04_a05 and has_attention_notification):
        raise ValueError("source Phase 4 evidence must include the A04/A05 attention/notification gap")
    return evidence


def _motion_contract_from_manifest(manifest):
    return {
        "states": {
            state: {
                "durationMs": int(manifest["states"][state]["durationMs"]),
                "inbetweens": int(manifest["states"][state].get("inbetweens", 0)),
            }
            for state in hq.CORE_STATES
        }
    }


def _save_frames(frames, output_dir):
    ensure_dir(output_dir)
    for index, frame in enumerate(frames, start=1):
        frame.save(output_dir / f"{index:02d}.png")


def _protected_face_bottom(alpha):
    left, top, right, bottom = alpha
    return top + int((bottom - top) * 0.45)


def _can_draw_repair_cue(alpha, image_size):
    image_width, image_height = image_size
    if image_width < MIN_REPAIR_CUE_CANVAS or image_height < MIN_REPAIR_CUE_CANVAS:
        return False
    face_bottom = _protected_face_bottom(alpha)
    return image_height - face_bottom >= max(8, image_height // 6)


def _side_prop_rect(alpha, image_size, *, width_ratio, height_ratio, y_ratio):
    image_width, image_height = image_size
    left, top, right, bottom = alpha
    if image_width <= 0 or image_height <= 0:
        return (0, 0, 0, 0)
    prop_width = min(image_width, max(1, max(10, int(image_width * width_ratio))))
    prop_height = min(image_height, max(1, max(8, int(image_height * height_ratio))))
    gap = max(2, image_width // 48)
    if right + gap + prop_width <= image_width:
        prop_left = right + gap
    elif left - gap - prop_width >= 0:
        prop_left = left - gap - prop_width
    elif right + prop_width <= image_width:
        prop_left = right
    elif left - prop_width >= 0:
        prop_left = left - prop_width
    else:
        prop_left = max(0, min(image_width - prop_width, right - prop_width))
    prop_top = max(0, min(image_height - prop_height, top + int((bottom - top) * y_ratio)))
    return (prop_left, prop_top, prop_left + prop_width, prop_top + prop_height)


def _draw_star(draw, center, radius, *, fill, outline):
    cx, cy = center
    points = [
        (cx, cy - radius),
        (cx + radius // 3, cy - radius // 3),
        (cx + radius, cy - radius // 4),
        (cx + radius // 2, cy + radius // 5),
        (cx + radius * 2 // 3, cy + radius),
        (cx, cy + radius // 2),
        (cx - radius * 2 // 3, cy + radius),
        (cx - radius // 2, cy + radius // 5),
        (cx - radius, cy - radius // 4),
        (cx - radius // 3, cy - radius // 3),
    ]
    draw.polygon(points, fill=fill, outline=outline)


def _repair_attention_base_pose(image, alpha, frame_index):
    draw = ImageDraw.Draw(image)
    width, height = image.size
    left, top, right, bottom = alpha

    arm_width = max(2, width // 24)
    face_bottom = _protected_face_bottom(alpha)
    shoulder_y = top + int((bottom - top) * 0.52)
    hand_x = right - max(4, width // 14)
    hand_y = max(face_bottom + arm_width + 2, top + int((bottom - top) * 0.18) + (frame_index % 2))
    hand_y = min(bottom - max(4, height // 16), hand_y)
    draw.line((hand_x - 8, shoulder_y, hand_x + 3, hand_y), fill=(62, 48, 108, 255), width=arm_width)
    draw.ellipse((hand_x - 2, hand_y - 3, hand_x + 6, hand_y + 5), fill=(245, 190, 178, 255))
    return image


def _draw_attention_star(image, alpha, frame_index):
    draw = ImageDraw.Draw(image)
    width, height = image.size
    face_bottom = _protected_face_bottom(alpha)
    prop = _side_prop_rect(alpha, image.size, width_ratio=0.18, height_ratio=0.16, y_ratio=0.06)
    prop_left, prop_top, prop_right, prop_bottom = prop
    prop_height = prop_bottom - prop_top
    prop_top = max(prop_top, face_bottom + max(2, height // 32))
    prop_top = min(height - prop_height, prop_top)
    prop_bottom = prop_top + prop_height
    radius = max(5, min(prop_right - prop_left, prop_bottom - prop_top) // 2)
    center = ((prop_left + prop_right) // 2, (prop_top + prop_bottom) // 2 + (frame_index % 2))
    _draw_star(draw, center, radius, fill=(255, 220, 86, 255), outline=(64, 76, 145, 255))
    inner_radius = max(2, radius // 2)
    _draw_star(draw, center, inner_radius, fill=(255, 255, 236, 255), outline=(255, 220, 86, 255))
    return image


def _draw_attention_check_badge(image, alpha, frame_index):
    draw = ImageDraw.Draw(image)
    width, height = image.size
    face_bottom = _protected_face_bottom(alpha)
    badge = _side_prop_rect(alpha, image.size, width_ratio=0.2, height_ratio=0.16, y_ratio=0.12)
    badge_left, badge_top, badge_right, badge_bottom = badge
    badge_height = badge_bottom - badge_top
    badge_top = max(badge_top + frame_index % 2, face_bottom + max(2, height // 32))
    badge_top = min(height - badge_height, badge_top)
    badge_bottom = badge_top + badge_height
    stroke = max(2, width // 96)
    draw.rounded_rectangle(
        (badge_left, badge_top, badge_right, badge_bottom),
        radius=max(3, width // 32),
        fill=(228, 255, 232, 255),
        outline=(42, 136, 86, 255),
        width=stroke,
    )
    draw.line(
        (
            badge_left + max(3, width // 40),
            badge_top + (badge_bottom - badge_top) // 2,
            badge_left + (badge_right - badge_left) // 2,
            badge_bottom - max(3, height // 48),
            badge_right - max(3, width // 36),
            badge_top + max(3, height // 48),
        ),
        fill=(42, 136, 86, 255),
        width=stroke,
    )
    return image


def _repair_attention(frame, frame_index, recipe="small-star-side"):
    image = frame.copy()
    alpha = image.getchannel("A").getbbox()
    if not alpha:
        return image
    if not _can_draw_repair_cue(alpha, image.size):
        return image
    _repair_attention_base_pose(image, alpha, frame_index)
    if recipe == "raised-hand-only":
        return image
    if recipe == "small-star-side":
        return _draw_attention_star(image, alpha, frame_index)
    if recipe == "check-badge":
        return _draw_attention_check_badge(image, alpha, frame_index)
    raise ValueError(f"unknown attention repair recipe: {recipe}")


def _repair_notification_permission_card(image, alpha, frame_index):
    draw = ImageDraw.Draw(image)
    width, height = image.size
    left, top, right, bottom = alpha

    face_bottom = _protected_face_bottom(alpha)
    card = _side_prop_rect(alpha, image.size, width_ratio=0.28, height_ratio=0.2, y_ratio=0.26)
    card_left, card_top, card_right, card_bottom = card
    card_top = max(card_top + frame_index % 2, face_bottom + max(2, height // 32))
    card_bottom = max(card_bottom + frame_index % 2, card_top + max(8, int(height * 0.2)))
    card_bottom = min(height - 1, card_bottom)
    draw.rounded_rectangle(
        (card_left, card_top, card_right, card_bottom),
        radius=max(3, width // 32),
        fill=(250, 236, 174, 255),
        outline=(70, 105, 168, 255),
        width=max(2, width // 96),
    )

    button_y = card_top + int((card_bottom - card_top) * 0.68)
    button_radius = max(2, (card_bottom - card_top) // 8)
    left_button_x = card_left + int((card_right - card_left) * 0.35)
    right_button_x = card_left + int((card_right - card_left) * 0.65)
    draw.ellipse(
        (
            left_button_x - button_radius,
            button_y - button_radius,
            left_button_x + button_radius,
            button_y + button_radius,
        ),
        fill=(78, 174, 110, 255),
    )
    draw.ellipse(
        (
            right_button_x - button_radius,
            button_y - button_radius,
            right_button_x + button_radius,
            button_y + button_radius,
        ),
        fill=(214, 86, 96, 255),
    )

    bubble_tail = [
        (card_left + max(2, width // 64), card_bottom - max(2, height // 80)),
        (max(0, right - max(2, width // 64)), min(bottom, card_bottom + max(4, height // 32))),
        (card_left + max(6, width // 24), card_bottom - max(2, height // 80)),
    ]
    draw.polygon(bubble_tail, fill=(250, 236, 174, 255), outline=(70, 105, 168, 255))
    return image


def _repair_notification_message_bubble(image, alpha, frame_index):
    draw = ImageDraw.Draw(image)
    width, height = image.size
    left, top, right, bottom = alpha
    face_bottom = _protected_face_bottom(alpha)
    bubble = _side_prop_rect(alpha, image.size, width_ratio=0.3, height_ratio=0.18, y_ratio=0.3)
    bubble_left, bubble_top, bubble_right, bubble_bottom = bubble
    bubble_top = max(bubble_top + frame_index % 2, face_bottom + max(2, height // 32))
    bubble_bottom = min(height - 1, max(bubble_bottom + frame_index % 2, bubble_top + max(8, int(height * 0.18))))
    stroke = max(2, width // 96)
    draw.rounded_rectangle(
        (bubble_left, bubble_top, bubble_right, bubble_bottom),
        radius=max(3, width // 28),
        fill=(232, 246, 255, 255),
        outline=(54, 112, 178, 255),
        width=stroke,
    )
    dot_y = bubble_top + (bubble_bottom - bubble_top) // 2
    dot_radius = max(1, (bubble_bottom - bubble_top) // 10)
    for fraction in (0.35, 0.5, 0.65):
        dot_x = bubble_left + int((bubble_right - bubble_left) * fraction)
        draw.ellipse(
            (dot_x - dot_radius, dot_y - dot_radius, dot_x + dot_radius, dot_y + dot_radius),
            fill=(54, 112, 178, 255),
        )
    tail = [
        (bubble_left + max(3, width // 56), bubble_bottom - max(2, height // 80)),
        (max(0, right - max(2, width // 64)), min(bottom, bubble_bottom + max(4, height // 32))),
        (bubble_left + max(8, width // 24), bubble_bottom - max(2, height // 80)),
    ]
    draw.polygon(tail, fill=(232, 246, 255, 255), outline=(54, 112, 178, 255))
    return image


def _repair_notification_bell_side(image, alpha, frame_index):
    draw = ImageDraw.Draw(image)
    width, height = image.size
    face_bottom = _protected_face_bottom(alpha)
    bell = _side_prop_rect(alpha, image.size, width_ratio=0.22, height_ratio=0.2, y_ratio=0.28)
    bell_left, bell_top, bell_right, bell_bottom = bell
    bell_top = max(bell_top + frame_index % 2, face_bottom + max(2, height // 32))
    bell_bottom = min(height - 1, max(bell_bottom + frame_index % 2, bell_top + max(8, int(height * 0.18))))
    stroke = max(2, width // 96)
    center_x = (bell_left + bell_right) // 2
    dome_top = bell_top + max(2, height // 64)
    body_bottom = bell_bottom - max(3, height // 48)
    draw.pieslice(
        (bell_left, dome_top, bell_right, body_bottom + max(4, height // 32)),
        180,
        360,
        fill=(255, 218, 86, 255),
        outline=(78, 88, 150, 255),
        width=stroke,
    )
    draw.rectangle(
        (bell_left, dome_top + (body_bottom - dome_top) // 2, bell_right, body_bottom),
        fill=(255, 218, 86, 255),
        outline=(78, 88, 150, 255),
        width=stroke,
    )
    clapper_radius = max(2, (bell_right - bell_left) // 8)
    draw.ellipse(
        (center_x - clapper_radius, body_bottom - 1, center_x + clapper_radius, body_bottom + clapper_radius * 2),
        fill=(78, 88, 150, 255),
    )
    return image


def _repair_notification(frame, frame_index, recipe="permission-card"):
    image = frame.copy()
    alpha = image.getchannel("A").getbbox()
    if not alpha:
        return image
    if not _can_draw_repair_cue(alpha, image.size):
        return image
    if recipe == "permission-card":
        return _repair_notification_permission_card(image, alpha, frame_index)
    if recipe == "message-bubble":
        return _repair_notification_message_bubble(image, alpha, frame_index)
    if recipe == "bell-side":
        return _repair_notification_bell_side(image, alpha, frame_index)
    raise ValueError(f"unknown notification repair recipe: {recipe}")


def _draw_error_lower_x(image, alpha, frame_index):
    draw = ImageDraw.Draw(image)
    width, height = image.size
    left, top, right, bottom = alpha
    face_bottom = _protected_face_bottom(alpha)

    x_size = max(10, width // 5)
    x_left = max(0, min(width - x_size - 1, left + max(2, width // 16)))
    x_top = max(face_bottom + max(2, height // 32), top + int((bottom - top) * 0.58) + (frame_index % 2))
    x_top = min(height - x_size - 1, x_top)
    stroke = max(2, width // 96)
    draw.line((x_left, x_top, x_left + x_size, x_top + x_size), fill=(218, 54, 64, 255), width=stroke)
    draw.line((x_left + x_size, x_top, x_left, x_top + x_size), fill=(218, 54, 64, 255), width=stroke)
    return image


def _draw_error_broken_card(image, alpha):
    draw = ImageDraw.Draw(image)
    width, height = image.size
    face_bottom = _protected_face_bottom(alpha)
    stroke = max(2, width // 96)
    prop = _side_prop_rect(alpha, image.size, width_ratio=0.22, height_ratio=0.16, y_ratio=0.58)
    prop_left, prop_top, prop_right, prop_bottom = prop
    prop_top = max(prop_top, face_bottom + max(2, height // 32))
    draw.rounded_rectangle(
        (prop_left, prop_top, prop_right, prop_bottom),
        radius=max(2, width // 48),
        fill=(70, 74, 92, 255),
        outline=(218, 54, 64, 255),
        width=stroke,
    )
    crack_x = (prop_left + prop_right) // 2
    draw.line(
        (crack_x, prop_top + 2, crack_x - 3, prop_top + 7, crack_x + 2, prop_top + 12),
        fill=(245, 226, 170, 255),
        width=max(1, stroke - 1),
    )
    return image


def _draw_error_alert_panel(image, alpha, frame_index):
    draw = ImageDraw.Draw(image)
    width, height = image.size
    face_bottom = _protected_face_bottom(alpha)
    panel = _side_prop_rect(alpha, image.size, width_ratio=0.24, height_ratio=0.18, y_ratio=0.56)
    panel_left, panel_top, panel_right, panel_bottom = panel
    panel_top = max(panel_top + frame_index % 2, face_bottom + max(2, height // 32))
    panel_bottom = min(height - 1, max(panel_bottom + frame_index % 2, panel_top + max(8, int(height * 0.16))))
    stroke = max(2, width // 96)
    draw.rounded_rectangle(
        (panel_left, panel_top, panel_right, panel_bottom),
        radius=max(2, width // 48),
        fill=(84, 50, 62, 255),
        outline=(218, 54, 64, 255),
        width=stroke,
    )
    center_x = (panel_left + panel_right) // 2
    mark_top = panel_top + max(3, height // 48)
    mark_bottom = panel_bottom - max(4, height // 40)
    draw.line((center_x, mark_top, center_x, mark_bottom), fill=(255, 228, 120, 255), width=stroke)
    dot_radius = max(1, stroke)
    draw.ellipse(
        (center_x - dot_radius, panel_bottom - dot_radius * 3, center_x + dot_radius, panel_bottom - dot_radius),
        fill=(255, 228, 120, 255),
    )
    return image


def _repair_error(frame, frame_index, recipe="broken-card-lower"):
    image = frame.copy()
    alpha = image.getchannel("A").getbbox()
    if not alpha:
        return image
    if not _can_draw_repair_cue(alpha, image.size):
        return image
    _draw_error_lower_x(image, alpha, frame_index)
    if recipe == "lower-x-only":
        return image
    if recipe == "broken-card-lower":
        return _draw_error_broken_card(image, alpha)
    if recipe == "alert-panel-lower":
        return _draw_error_alert_panel(image, alpha, frame_index)
    raise ValueError(f"unknown error repair recipe: {recipe}")


def _scale_visible_content(frame, factor):
    alpha_bbox = frame.getchannel("A").getbbox()
    if not alpha_bbox:
        return frame.copy()
    content = frame.crop(alpha_bbox)
    new_size = (
        max(1, min(frame.width, int(round(content.width * factor)))),
        max(1, min(frame.height, int(round(content.height * factor)))),
    )
    scaled = content.resize(new_size, hq._resample_filter())
    output = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    center_x = (alpha_bbox[0] + alpha_bbox[2]) // 2
    bottom = alpha_bbox[3]
    left = max(0, min(frame.width - scaled.width, center_x - scaled.width // 2))
    top = max(0, min(frame.height - scaled.height, bottom - scaled.height))
    output.alpha_composite(scaled, (left, top))
    return output


def _repair_sleeping(frame, frame_index):
    image = _scale_visible_content(frame, 0.86)
    draw = ImageDraw.Draw(image)
    alpha = image.getchannel("A").getbbox()
    if not alpha:
        return image
    left, top, right, bottom = alpha
    z_left = max(left + 1, right - max(10, image.width // 3))
    z_top = max(0, top + 2 + frame_index % 2)
    draw.line(
        (z_left, z_top, z_left + 7, z_top, z_left, z_top + 7, z_left + 7, z_top + 7), fill=(80, 84, 190, 255), width=2
    )
    z2_left = max(left, z_left - 6)
    z2_top = min(bottom - 8, z_top + 7)
    draw.line(
        (z2_left, z2_top, z2_left + 5, z2_top, z2_left, z2_top + 5, z2_left + 5, z2_top + 5),
        fill=(80, 84, 190, 230),
        width=1,
    )
    return image


def _repair_frames(state, frames, repair_recipes=None):
    repair_recipes = resolve_repair_recipes(repair_recipes)
    if state == "attention":
        return [_repair_attention(frame, index, repair_recipes[state]) for index, frame in enumerate(frames)]
    if state == "error":
        return [_repair_error(frame, index, repair_recipes[state]) for index, frame in enumerate(frames)]
    if state == "notification":
        return [_repair_notification(frame, index, repair_recipes[state]) for index, frame in enumerate(frames)]
    if state == "sleeping":
        return [_repair_sleeping(frame, index) for index, frame in enumerate(frames)]
    return [frame.copy() for frame in frames]


def _write_repaired_masters(source_theme, masters_dir, repair_recipes=None):
    source_theme = Path(source_theme)
    masters_dir = Path(masters_dir)
    repair_recipes = resolve_repair_recipes(repair_recipes)
    states = {}
    for state in hq.CORE_STATES:
        source_runtime = source_theme / "assets" / f"akari-{state}.apng"
        frames = _display_frames(source_runtime)
        repaired = _repair_frames(state, frames, repair_recipes)
        _save_frames(repaired, masters_dir / state)
        states[state] = {
            "repairRole": "state-local-repair" if state in REPAIR_TARGETS else "copied-unchanged",
            "sourceRuntime": source_runtime.as_posix(),
            "sourceRuntimeSha256": hq.sha256_file(source_runtime),
        }
        if state in repair_recipes:
            states[state]["repairRecipe"] = repair_recipes[state]
    return states


def _runtime_hashes(theme_dir):
    return {state: hq.sha256_file(Path(theme_dir) / "assets" / f"akari-{state}.apng") for state in hq.CORE_STATES}


def _build_state_validation(source_theme, repaired_theme, master_states):
    before = _runtime_hashes(source_theme)
    after = _runtime_hashes(repaired_theme)
    rationales = {
        "attention": "Raised-hand pose plus large blue attention mark keep attention distinct without red artifact noise.",
        "error": "Red X and gloom cue add a non-face error signal while preserving Akari identity.",
        "notification": "Horizontal message bubble plus open expression creates inspectable notification cue without a vertical side artifact.",
        "sleeping": "Sleeping footprint is visibly resized with stronger Z cues while preserving sleeping pose and identity.",
    }
    states = {}
    for state in hq.CORE_STATES:
        role = master_states[state]["repairRole"]
        data = {
            "afterRuntimeSha256": after[state],
            "beforeRuntimeSha256": before[state],
            "repairRole": role,
        }
        if role == "copied-unchanged":
            data["copiedFromRuntimeSha256"] = before[state]
        else:
            data["repairRationale"] = rationales[state]
            if "repairRecipe" in master_states[state]:
                data["repairRecipe"] = master_states[state]["repairRecipe"]
        states[state] = data
    return states


def _write_validation(
    *,
    validation_json,
    source_theme,
    source_evidence_path,
    source_evidence,
    repaired_theme,
    clawd_result,
    repair_recipes,
    states,
):
    build_manifest = Path(repaired_theme) / "qa" / "build-manifest.json"
    data = {
        "boundaryStatement": "Compatibility-only repaired candidate evidence; visual acceptance remains Phase 4 recognition gated.",
        "buildManifest": build_manifest.as_posix(),
        "clawdValidator": {
            "command": clawd_result.command,
            "evidenceRole": "compatibility-only",
            "exitCode": clawd_result.exit_code,
            "status": clawd_result.status,
            "stderr": clawd_result.stderr,
            "stdout": clawd_result.stdout,
        },
        "phase": "04-pet-size-visual-recognition-gate",
        "phase4Required": True,
        "releasePackageAccepted": False,
        "repairRecipes": repair_recipes,
        "repairTargets": list(REPAIR_TARGETS),
        "requirementsCovered": ["VQA-01", "VQA-02", "VQA-03", "VQA-04"],
        "schemaVersion": 1,
        "sourcePhase4Evidence": {
            "path": Path(source_evidence_path).as_posix(),
            "sha256": hq.sha256_file(source_evidence_path),
            "status": source_evidence.get("recognition", {}).get("status"),
            "visualAcceptance": source_evidence.get("visualAcceptance"),
        },
        "sourceTheme": {
            "path": Path(source_theme).as_posix(),
            "buildManifestSha256": hq.sha256_file(Path(source_theme) / "qa" / "build-manifest.json"),
        },
        "states": states,
        "themeDir": Path(repaired_theme).as_posix(),
        "validationRole": "compatibility-only",
        "visualAcceptance": False,
    }
    return write_json(validation_json, data)


def build_phase4_gap_repair(
    *,
    source_theme=DEFAULT_SOURCE_THEME,
    source_phase4_evidence=DEFAULT_SOURCE_PHASE4_EVIDENCE,
    run_dir=DEFAULT_RUN_DIR,
    clawd_validator=phase3.DEFAULT_CLAWD_VALIDATOR,
    repair_recipes=None,
):
    source_theme = Path(source_theme)
    source_phase4_evidence = Path(source_phase4_evidence)
    run_dir = Path(run_dir)
    masters_dir = run_dir / "masters"
    theme_dir = run_dir / "theme"
    qa_dir = ensure_dir(run_dir / "qa")
    visual_qa_dir = run_dir / "phase4-visual-recognition" / "qa"
    validation_json = qa_dir / "phase4-gap-repair-validation.json"
    repair_recipes = resolve_repair_recipes(repair_recipes)

    source_evidence = _validate_source_evidence(source_phase4_evidence)
    phase3_validation = _source_phase3_validation(source_evidence)
    source_paths = vr.validate_phase3_inputs(source_theme, phase3_validation)
    motion_contract = _motion_contract_from_manifest(source_paths["manifest"])

    if masters_dir.exists():
        shutil.rmtree(masters_dir)
    if theme_dir.exists():
        shutil.rmtree(theme_dir)
    if visual_qa_dir.exists():
        shutil.rmtree(visual_qa_dir)

    master_states = _write_repaired_masters(source_theme, masters_dir, repair_recipes)
    hq.export_theme(masters_dir, theme_dir, include_ultra=False, motion_contract=motion_contract)
    hq.validate_lineage(theme_dir)
    hq.validate_theme_assets(theme_dir, motion_contract=motion_contract)
    clawd_result = phase3.run_clawd_validator(theme_dir, clawd_validator)
    states = _build_state_validation(source_theme, theme_dir, master_states)
    _write_validation(
        validation_json=validation_json,
        source_theme=source_theme,
        source_evidence_path=source_phase4_evidence,
        source_evidence=source_evidence,
        repaired_theme=theme_dir,
        clawd_result=clawd_result,
        repair_recipes=repair_recipes,
        states=states,
    )
    if clawd_result.exit_code != 0:
        raise ValueError("Clawd validator failed")

    visual = vr.build_phase4_visual_recognition(
        theme_dir=theme_dir,
        phase3_validation=validation_json,
        qa_dir=visual_qa_dir,
    )
    return GapRepairResult(
        run_dir=run_dir,
        masters_dir=masters_dir,
        theme_dir=theme_dir,
        validation_json=validation_json,
        visual_qa_dir=visual_qa_dir,
        visual_recognition_json=visual.evidence_json,
    )


def _build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build repaired Phase 4 candidate")
    build.add_argument("--source-theme", type=Path, default=DEFAULT_SOURCE_THEME)
    build.add_argument("--source-phase4-evidence", type=Path, default=DEFAULT_SOURCE_PHASE4_EVIDENCE)
    build.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    build.add_argument("--clawd-validator", type=Path, default=phase3.DEFAULT_CLAWD_VALIDATOR)
    build.add_argument("--attention-recipe", choices=REPAIR_RECIPES["attention"], default=None)
    build.add_argument("--notification-recipe", choices=REPAIR_RECIPES["notification"], default=None)
    build.add_argument("--error-recipe", choices=REPAIR_RECIPES["error"], default=None)
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    if args.command == "build":
        result = build_phase4_gap_repair(
            source_theme=args.source_theme,
            source_phase4_evidence=args.source_phase4_evidence,
            run_dir=args.run_dir,
            clawd_validator=args.clawd_validator,
            repair_recipes={
                state: recipe
                for state, recipe in {
                    "attention": args.attention_recipe,
                    "notification": args.notification_recipe,
                    "error": args.error_recipe,
                }.items()
                if recipe is not None
            },
        )
        print(f"wrote {result.validation_json}")


if __name__ == "__main__":
    main()
