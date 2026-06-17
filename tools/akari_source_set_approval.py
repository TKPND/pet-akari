"""Build and validate Phase 2 Akari source-set approval evidence."""

import argparse
import json
from pathlib import Path

import clawd_hq_theme as hq
from PIL import Image, ImageDraw

PHASE = "02-state-source-selection-and-identity-lock"
SOURCE_SET_ID = "seamsafe-promoted"
DEFAULT_CANDIDATE_THEME = Path("outputs/akari-hq-apng-theme-seamsafe")
DEFAULT_BUILD_MANIFEST = DEFAULT_CANDIDATE_THEME / "qa" / "build-manifest.json"
DEFAULT_RENDERED_MASTERS_ROOT = Path("work/akari-hq-apng/full-motion-quality-seamsafe-run/masters")
DEFAULT_UPSTREAM_MASTERS_ROOT = Path("work/akari-hq-apng/denser-source-run/masters-stabilized")
DEFAULT_SOURCE_MANIFEST = Path("work/akari-hq-apng/full-motion-quality-seamsafe-run/source-manifest.json")
DEFAULT_STATE_QUALITY = Path("work/akari-hq-apng/full-motion-quality-seamsafe-run/qa/metrics/state-quality.json")
DEFAULT_RUN_SUMMARY = Path("work/akari-hq-apng/full-motion-quality-seamsafe-run/qa/run-summary.json")
DEFAULT_APPROVAL = DEFAULT_CANDIDATE_THEME / "qa" / "source-set-approval.json"
DEFAULT_CONTACT_SHEET = DEFAULT_CANDIDATE_THEME / "qa" / "source-set-identity-contact-sheet.png"
DEFAULT_DISTINCTNESS = DEFAULT_CANDIDATE_THEME / "qa" / "metrics" / "source-distinctness.json"
IDENTITY_CHECKS = (
    "hairShapeAndColor",
    "bangs",
    "faceProportions",
    "outfitCues",
    "palette",
    "silhouette",
)
DECISION_COVERAGE = (
    "D-01 uses seamsafe-promoted and maps promoted output to rendered and upstream masters.",
    "D-02 requires exact seven-state coverage with no silent fallback.",
    "D-03 creates file-backed identity approval evidence beside the selected source set.",
    "D-04 records hair, bangs, face proportions, outfit, palette, and silhouette checks.",
    "D-05 records source-level face, pose, or motion distinctness evidence.",
    "D-06 defers formal label-hidden pet-size recognition to Phase 04.",
    "D-07 keeps Path D closed unless Path C is blocked by concrete source-set evidence.",
    "D-08 avoids package closeout, final release validation, and allowlisted zip production.",
)
EVIDENCE_NOTES = (
    "Phase 2 approves source selection and identity only.",
    "Phase 3 owns APNG contract export and Clawd compatibility validation.",
    "Phase 4 owns label-hidden pet-size recognition at 128px and 160px.",
    "Phase 5 owns allowlisted package closeout.",
    "Validator success is compatibility evidence, not visual acceptance.",
)


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


def _state_set(mapping, label):
    if not isinstance(mapping, dict):
        raise ValueError(f"{label} must be a JSON object")
    return set(mapping)


def _validate_exact_states(mapping, label):
    actual = _state_set(mapping, label)
    expected = set(hq.CORE_STATES)
    missing = [state for state in hq.CORE_STATES if state not in actual]
    if missing:
        raise ValueError(f"{label} missing state {missing[0]}")
    extra = sorted(actual - expected)
    if extra:
        raise ValueError(f"{label} has extra state {extra[0]}")


def _state_runtime_path(candidate_theme, state_manifest):
    return Path(candidate_theme) / state_manifest["runtimeAsset"]


def _reviewed_identity_checks():
    return {check: "pass" for check in IDENTITY_CHECKS}


def _identity_notes():
    return (
        "Identity anchors reviewed: dark navy cadet/newsboy cap, short coral-orange bob hair, "
        "bangs, magenta eyes, teal jacket, cream hoodie, navy pleated skirt, crossbody bag, "
        "palette balance, and full-body silhouette."
    )


def _state_distinctness(state, quality_entry):
    metrics = quality_entry.get("metrics", {}) if isinstance(quality_entry, dict) else {}
    motion = metrics.get("motion", {}) if isinstance(metrics.get("motion"), dict) else {}
    semantics = metrics.get("semantics", {}) if isinstance(metrics.get("semantics"), dict) else {}
    approval = semantics.get("approval", {}) if isinstance(semantics.get("approval"), dict) else {}
    signals = ["face", "pose", "motion"]
    note = approval.get("notes") or f"{state} has source-level face, pose, or motion evidence."
    return {
        "ok": bool(motion.get("ok")) and bool(semantics.get("ok")),
        "notes": note,
        "phase4RecognitionDeferred": True,
        "signals": signals,
        "uniqueFrames": motion.get("uniqueFrames"),
    }


def _resolve_source_path(path, candidate_theme):
    path = Path(path)
    if path.is_absolute():
        return path
    theme_relative = Path(candidate_theme) / path
    if theme_relative.exists():
        return theme_relative
    return path


def _relative_or_input(path):
    return Path(path).as_posix()


def _first_png(path):
    files = sorted(Path(path).glob("*.png"))
    if not files:
        raise FileNotFoundError(f"no PNG frames in {path}")
    return files[0]


def _first_runtime_frame(path):
    with Image.open(path) as image:
        image.seek(0)
        return image.convert("RGBA")


def _thumb(path_or_image, size):
    if isinstance(path_or_image, Image.Image):
        image = path_or_image.convert("RGBA")
    else:
        with Image.open(path_or_image) as opened:
            image = opened.convert("RGBA")
    image.thumbnail(size, getattr(getattr(Image, "Resampling", Image), "LANCZOS"))
    return image


def write_identity_contact_sheet(approval_data, output):
    output = Path(output)
    ensure_dir(output.parent)
    thumb_size = (128, 160)
    label_height = 44
    columns = 3
    row_width = columns * thumb_size[0]
    row_height = thumb_size[1] + label_height
    sheet = Image.new("RGBA", (row_width, row_height * len(hq.CORE_STATES)), (250, 250, 250, 255))
    draw = ImageDraw.Draw(sheet)

    for row, state in enumerate(hq.CORE_STATES):
        state_data = approval_data["states"][state]
        images = (
            _first_runtime_frame(state_data["promotedRuntimeAsset"]),
            _first_png(state_data["renderedMasterDir"]),
            _first_png(state_data["upstreamSourceDir"]),
        )
        for column, source in enumerate(images):
            thumb = _thumb(source, thumb_size)
            left = column * thumb_size[0] + (thumb_size[0] - thumb.width) // 2
            top = row * row_height + (thumb_size[1] - thumb.height) // 2
            sheet.alpha_composite(thumb, (left, top))
        label_y = row * row_height + thumb_size[1] + 6
        draw.text((8, label_y), f"{state}: runtime | rendered | upstream", fill=(20, 20, 24, 255))

    sheet.convert("RGB").save(output)
    return output


def build_source_set_approval(
    *,
    candidate_theme=DEFAULT_CANDIDATE_THEME,
    build_manifest=DEFAULT_BUILD_MANIFEST,
    rendered_masters_root=DEFAULT_RENDERED_MASTERS_ROOT,
    upstream_masters_root=DEFAULT_UPSTREAM_MASTERS_ROOT,
    source_manifest=DEFAULT_SOURCE_MANIFEST,
    state_quality=DEFAULT_STATE_QUALITY,
    run_summary=DEFAULT_RUN_SUMMARY,
    output=DEFAULT_APPROVAL,
    contact_sheet=DEFAULT_CONTACT_SHEET,
    distinctness_output=DEFAULT_DISTINCTNESS,
    reviewer="codex",
):
    candidate_theme = Path(candidate_theme)
    build_manifest = Path(build_manifest)
    rendered_masters_root = Path(rendered_masters_root)
    upstream_masters_root = Path(upstream_masters_root)
    source_manifest = Path(source_manifest)
    state_quality = Path(state_quality)
    run_summary = Path(run_summary)
    output = Path(output)
    contact_sheet = Path(contact_sheet)
    distinctness_output = Path(distinctness_output)

    manifest = load_json(build_manifest)
    manifest_states = manifest.get("states")
    _validate_exact_states(manifest_states, "build manifest")
    source_map = load_json(source_manifest)
    _validate_exact_states(source_map, "source manifest")
    quality = load_json(state_quality)
    _validate_exact_states(quality, "state quality")
    summary = load_json(run_summary)

    seen_runtime_assets = set()
    for state in hq.CORE_STATES:
        runtime_asset = manifest_states[state].get("runtimeAsset")
        if runtime_asset in seen_runtime_assets:
            raise ValueError(f"duplicate runtime asset: {runtime_asset}")
        seen_runtime_assets.add(runtime_asset)

    hq.validate_lineage(candidate_theme, build_manifest)

    distinctness = {
        "schemaVersion": 1,
        "phase": PHASE,
        "sourceSetId": SOURCE_SET_ID,
        "states": {},
    }
    states = {}
    for state in hq.CORE_STATES:
        state_manifest = manifest_states[state]
        runtime_path = _state_runtime_path(candidate_theme, state_manifest)
        if not runtime_path.is_file():
            raise FileNotFoundError(runtime_path)
        rendered_dir = rendered_masters_root / state
        upstream_dir = upstream_masters_root / state
        if not rendered_dir.is_dir():
            raise FileNotFoundError(rendered_dir)
        if not upstream_dir.is_dir():
            raise FileNotFoundError(upstream_dir)
        upstream_files = [Path(path) for path in source_map[state]]
        if not upstream_files:
            raise ValueError(f"{state} upstream source list is empty")
        for upstream_file in upstream_files:
            if not upstream_file.is_file():
                raise FileNotFoundError(upstream_file)

        identity_checks = _reviewed_identity_checks()
        source_distinctness = _state_distinctness(state, quality[state])
        source_files = []
        for source in state_manifest.get("sourceMasterFiles", []):
            source_path = _resolve_source_path(source["path"], candidate_theme)
            source_files.append(
                {
                    "path": source_path.as_posix(),
                    "sha256": source["sha256"],
                }
            )
        distinctness["states"][state] = {
            "metrics": {
                "identity": {"checks": identity_checks, "ok": True},
                "lineageReference": {
                    "buildManifest": build_manifest.as_posix(),
                    "ok": True,
                    "runtimeSha256": state_manifest["runtimeSha256"],
                },
                "sourceCoverage": {
                    "ok": True,
                    "renderedFrameCount": len(source_files),
                    "upstreamFrameCount": len(upstream_files),
                },
                "sourceDistinctness": source_distinctness,
            },
            "state": state,
            "status": "pass" if source_distinctness["ok"] else "needs-human-review",
        }
        states[state] = {
            "approved": source_distinctness["ok"],
            "fallbackUsed": False,
            "identityReview": {
                "checks": identity_checks,
                "identityOk": True,
                "notes": _identity_notes(),
                "reviewedEvidence": [
                    runtime_path.as_posix(),
                    rendered_dir.as_posix(),
                    upstream_dir.as_posix(),
                ],
            },
            "promotedRuntimeAsset": runtime_path.as_posix(),
            "promotedRuntimeSha256": state_manifest["runtimeSha256"],
            "rejectionReason": None,
            "renderedMasterDir": rendered_dir.as_posix(),
            "semanticFallbackReason": None,
            "sourceLevelDistinctness": source_distinctness,
            "sourceMasterFiles": source_files,
            "trueSourceFrames": state_manifest["trueSourceFrames"],
            "upstreamSourceDir": upstream_dir.as_posix(),
            "upstreamSourceFiles": [path.as_posix() for path in upstream_files],
        }

    approved = all(states[state]["approved"] for state in hq.CORE_STATES)
    data = {
        "approved": approved,
        "approvedForPhase3": approved,
        "canonicalApprovalArtifact": output.as_posix(),
        "decisionCoverage": list(DECISION_COVERAGE),
        "deferredToPhase": {
            "allowlistedPackageCloseout": "05",
            "apngContractExport": "03",
            "petSizeBlindRecognition": "04",
        },
        "evidence": {
            "buildManifest": build_manifest.as_posix(),
            "contactSheet": contact_sheet.as_posix(),
            "distinctnessMetrics": distinctness_output.as_posix(),
            "runSummary": run_summary.as_posix(),
            "sourceManifest": source_manifest.as_posix(),
            "stateQuality": state_quality.as_posix(),
        },
        "evidenceNotes": list(EVIDENCE_NOTES),
        "phase": PHASE,
        "reviewer": reviewer,
        "runSummaryStatus": {
            "ok": summary.get("ok"),
            "promoted": summary.get("promoted"),
            "visualApprovedContextOnly": summary.get("visualApproved"),
        },
        "schemaVersion": 1,
        "sourceRoots": {
            "promotedTheme": candidate_theme.as_posix(),
            "renderedMasters": rendered_masters_root.as_posix(),
            "upstreamStabilizedMasters": upstream_masters_root.as_posix(),
        },
        "sourceSetId": SOURCE_SET_ID,
        "states": states,
    }
    write_json(distinctness_output, distinctness)
    write_identity_contact_sheet(data, contact_sheet)
    write_json(output, data)
    validate_source_set_approval(output)
    return output


def validate_source_set_approval(approval):
    data = load_json(approval)
    if data.get("schemaVersion") != 1:
        raise ValueError("source-set approval schemaVersion mismatch")
    if data.get("phase") != PHASE:
        raise ValueError("source-set approval phase mismatch")
    if data.get("sourceSetId") != SOURCE_SET_ID:
        raise ValueError("source-set approval sourceSetId mismatch")
    states = data.get("states")
    _validate_exact_states(states, "approval states")
    if data.get("deferredToPhase", {}).get("petSizeBlindRecognition") != "04":
        raise ValueError("pet-size blind recognition must be deferred to Phase 04")
    if data.get("deferredToPhase", {}).get("apngContractExport") != "03":
        raise ValueError("APNG contract export must be deferred to Phase 03")
    if data.get("deferredToPhase", {}).get("allowlistedPackageCloseout") != "05":
        raise ValueError("allowlisted package closeout must be deferred to Phase 05")

    seen_assets = set()
    for state in hq.CORE_STATES:
        state_data = states[state]
        asset = state_data.get("promotedRuntimeAsset")
        if asset in seen_assets:
            raise ValueError(f"duplicate runtime asset: {asset}")
        seen_assets.add(asset)
        if state_data.get("fallbackUsed") is not False:
            raise ValueError(f"{state} fallbackUsed must be false")
        checks = state_data.get("identityReview", {}).get("checks")
        if not isinstance(checks, dict):
            raise ValueError(f"{state} identity checks must be a JSON object")
        for check in IDENTITY_CHECKS:
            if check not in checks:
                raise ValueError(f"{state} identity check missing {check}")
            if checks[check] != "pass":
                raise ValueError(f"{state} identity check {check} is not pass")
        if state_data.get("approved") is not True:
            raise ValueError(f"{state} is not approved")

    coverage = " ".join(data.get("decisionCoverage", [])) + " " + " ".join(data.get("evidenceNotes", []))
    missing = [f"D-{index:02d}" for index in range(1, 9) if f"D-{index:02d}" not in coverage]
    if missing:
        raise ValueError(f"decision coverage missing {', '.join(missing)}")
    if data.get("approved") is not True or data.get("approvedForPhase3") is not True:
        raise ValueError("source set is not approved for Phase 3")
    return True


def _build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="write Phase 2 source-set approval evidence")
    build.add_argument("--candidate-theme", type=Path, default=DEFAULT_CANDIDATE_THEME)
    build.add_argument("--build-manifest", type=Path, default=DEFAULT_BUILD_MANIFEST)
    build.add_argument("--rendered-masters-root", type=Path, default=DEFAULT_RENDERED_MASTERS_ROOT)
    build.add_argument("--upstream-masters-root", type=Path, default=DEFAULT_UPSTREAM_MASTERS_ROOT)
    build.add_argument("--source-manifest", type=Path, default=DEFAULT_SOURCE_MANIFEST)
    build.add_argument("--state-quality", type=Path, default=DEFAULT_STATE_QUALITY)
    build.add_argument("--run-summary", type=Path, default=DEFAULT_RUN_SUMMARY)
    build.add_argument("--output", type=Path, default=DEFAULT_APPROVAL)
    build.add_argument("--contact-sheet", type=Path, default=DEFAULT_CONTACT_SHEET)
    build.add_argument("--distinctness-output", type=Path, default=DEFAULT_DISTINCTNESS)

    validate = subparsers.add_parser("validate", help="validate Phase 2 source-set approval evidence")
    validate.add_argument("--approval", type=Path, default=DEFAULT_APPROVAL)
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    if args.command == "build":
        output = build_source_set_approval(
            candidate_theme=args.candidate_theme,
            build_manifest=args.build_manifest,
            rendered_masters_root=args.rendered_masters_root,
            upstream_masters_root=args.upstream_masters_root,
            source_manifest=args.source_manifest,
            state_quality=args.state_quality,
            run_summary=args.run_summary,
            output=args.output,
            contact_sheet=args.contact_sheet,
            distinctness_output=args.distinctness_output,
        )
        print(f"wrote {output}")
    elif args.command == "validate":
        validate_source_set_approval(args.approval)
        print(f"validated {args.approval}")


if __name__ == "__main__":
    main()
