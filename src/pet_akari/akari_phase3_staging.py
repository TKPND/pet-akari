"""Stage approved Akari APNG sources as a Phase 3 Clawd-compatible theme."""

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pet_akari import akari_source_set_approval as approval
from pet_akari import clawd_hq_theme as hq

PHASE = "03-apng-export-and-clawd-contract-validation"
SOURCE_SET_ID = "seamsafe-promoted"
DEFAULT_APPROVAL = Path("outputs/akari-hq-apng-theme-seamsafe/qa/source-set-approval.json")
DEFAULT_RUN_DIR = Path("work/akari-hq-apng/phase3-staging")
DEFAULT_THEME_DIR = DEFAULT_RUN_DIR / "theme"
DEFAULT_MOTION_CONTRACT = Path("work/akari-hq-apng/full-motion-quality-seamsafe-run/motion-contract.json")
DEFAULT_VALIDATION_OUTPUT = DEFAULT_RUN_DIR / "qa" / "phase3-validation.json"
DEFAULT_VALIDATOR_OUTPUT = DEFAULT_RUN_DIR / "qa" / "clawd-validator.txt"
DEFAULT_CLAWD_VALIDATOR = Path("work/clawd-on-desk/scripts/validate-theme.js")
BOUNDARY_STATEMENT = "Clawd validator success is compatibility evidence only; visual-state acceptance remains Phase 04."

REQUIREMENTS_COVERED = ["ASSET-03", "VQA-05", "PKG-01", "PKG-02"]
DECISION_COVERAGE = [
    "D-01: Phase 3 validates source-set-approval.json before export.",
    "D-02: Stage exactly hq.CORE_STATES with no silent fallback.",
    "D-03: Preserve seamsafe-promoted as the source-set identity lock.",
    "D-04: Use tools/clawd_hq_theme.py for APNG/theme/manifest contracts.",
    "D-05: Bind runtime assets to source paths, hashes, frame counts, and timing.",
    "D-06: Fail closed on missing masters, stale lineage, invalid assets, or theme mismatch.",
    "D-07: Record Clawd validator success as compatibility-only evidence.",
    "D-08: Keep visual-state acceptance deferred to Phase 04.",
    "D-09: Do not accept a final allowlisted release package in Phase 03.",
    "D-10: Do not introduce new art generation, Path D, reactions, mini tuning, or classifiers.",
]


@dataclass(frozen=True)
class ValidatorResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    status: str


@dataclass(frozen=True)
class StageResult:
    theme_dir: Path
    validation_json: Path
    validator_text: Path
    build_manifest: Path


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


def resolve_rendered_masters(approval_data):
    roots = approval_data.get("sourceRoots")
    if not isinstance(roots, dict):
        raise ValueError("approval sourceRoots must be a JSON object")
    rendered_masters = roots.get("renderedMasters")
    if not rendered_masters:
        raise ValueError("approval sourceRoots.renderedMasters is required")
    rendered_masters = Path(rendered_masters)
    if not rendered_masters.is_dir():
        raise FileNotFoundError(rendered_masters)

    for state in hq.CORE_STATES:
        state_dir = rendered_masters / state
        if not state_dir.is_dir():
            raise FileNotFoundError(state_dir)
        if not sorted(state_dir.glob("*.png")):
            raise FileNotFoundError(f"no PNG frames in {state_dir}")
    return rendered_masters


def validate_approved_master_files(approval_data, rendered_masters):
    rendered_masters = Path(rendered_masters)
    states = approval_data.get("states")
    if not isinstance(states, dict):
        raise ValueError("approval states must be a JSON object")

    for state in hq.CORE_STATES:
        state_approval = states.get(state)
        if not isinstance(state_approval, dict):
            raise ValueError(f"{state} approval state must be a JSON object")
        approved_files = state_approval.get("sourceMasterFiles")
        if not isinstance(approved_files, list) or not approved_files:
            raise ValueError(f"{state} approval sourceMasterFiles is required")

        approved_by_name = {}
        for source in approved_files:
            if not isinstance(source, dict):
                raise ValueError(f"{state} approval sourceMasterFiles entries must be JSON objects")
            source_path = source.get("path")
            source_sha = source.get("sha256")
            if not source_path or not isinstance(source_sha, str):
                raise ValueError(f"{state} approval sourceMasterFiles path and sha256 are required")
            approved_name = Path(source_path).name
            if approved_name in approved_by_name:
                raise ValueError(f"{state} approval sourceMasterFiles contains duplicate {approved_name}")
            approved_by_name[approved_name] = source_sha

        actual_files = sorted((rendered_masters / state).glob("*.png"))
        actual_names = {path.name for path in actual_files}
        approved_names = set(approved_by_name)
        if actual_names != approved_names:
            raise ValueError(f"{state} approved master file set mismatch")

        for path in actual_files:
            expected_sha = approved_by_name[path.name]
            if hq.sha256_file(path) != expected_sha:
                raise ValueError(f"{state} approved master hash mismatch: {path}")
    return True


def validate_phase3_runtime_asset_set(theme_dir):
    theme_dir = Path(theme_dir)
    expected_assets = {f"akari-{state}.apng" for state in hq.CORE_STATES}
    assets_dir = theme_dir / "assets"
    if not assets_dir.is_dir():
        raise FileNotFoundError(assets_dir)
    actual_assets = {path.name for path in assets_dir.glob("*.apng")}
    if actual_assets != expected_assets:
        raise ValueError("Phase 3 staged assets must contain exactly approved runtime assets")
    if (theme_dir / "assets-ultra").exists():
        raise ValueError("Phase 3 staging must not retain assets-ultra output")
    return True


def load_motion_contract(path):
    return hq.load_motion_contract(path)


def run_clawd_validator(theme_dir, validator_script=DEFAULT_CLAWD_VALIDATOR):
    theme_dir = Path(theme_dir)
    validator_script = Path(validator_script)
    if not validator_script.is_file():
        raise FileNotFoundError(validator_script)
    command = ["node", validator_script.as_posix(), theme_dir.as_posix()]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        shell=False,
    )
    return ValidatorResult(
        command=command,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        status="pass" if completed.returncode == 0 else "fail",
    )


def _write_validator_text(path, result):
    lines = [
        f"command: {' '.join(result.command)}",
        f"exitCode: {result.exit_code}",
        "",
        "[stdout]",
        result.stdout.rstrip(),
        "",
        "[stderr]",
        result.stderr.rstrip(),
        "",
    ]
    path = Path(path)
    ensure_dir(path.parent)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _phase3_state_evidence(manifest):
    states = {}
    for state in hq.CORE_STATES:
        state_manifest = manifest["states"][state]
        states[state] = {
            "durationMs": state_manifest["durationMs"],
            "encodedFrames": state_manifest["encodedFrames"],
            "inbetweens": state_manifest["inbetweens"],
            "runtimeAsset": state_manifest["runtimeAsset"],
            "runtimeSha256": state_manifest["runtimeSha256"],
            "sourceMasterFiles": state_manifest["sourceMasterFiles"],
            "trueSourceFrames": state_manifest["trueSourceFrames"],
        }
    return states


def build_validation_evidence(
    *,
    approval_path,
    approval_data,
    theme_dir,
    build_manifest,
    motion_contract_path,
    validator_result,
    validator_output,
):
    manifest = load_json(build_manifest)
    return {
        "approval": {
            "approved": approval_data.get("approved"),
            "approvedForPhase3": approval_data.get("approvedForPhase3"),
            "path": Path(approval_path).as_posix(),
        },
        "boundaryStatement": BOUNDARY_STATEMENT,
        "buildManifest": Path(build_manifest).as_posix(),
        "clawdValidator": {
            "command": validator_result.command,
            "evidenceRole": "compatibility-only",
            "exitCode": validator_result.exit_code,
            "status": validator_result.status,
        },
        "decisionCoverage": list(DECISION_COVERAGE),
        "finalAllowlistedPackage": None,
        "motionContract": Path(motion_contract_path).as_posix(),
        "phase": PHASE,
        "phase4Required": True,
        "releasePackageAccepted": False,
        "requirementsCovered": list(REQUIREMENTS_COVERED),
        "schemaVersion": 1,
        "sourceRoots": {
            "renderedMasters": approval_data["sourceRoots"]["renderedMasters"],
        },
        "sourceSetId": SOURCE_SET_ID,
        "states": _phase3_state_evidence(manifest),
        "themeDir": Path(theme_dir).as_posix(),
        "validationRole": "compatibility-only",
        "validatorOutput": Path(validator_output).as_posix(),
        "visualAcceptance": False,
    }


def stage_theme(
    *,
    approval_path=DEFAULT_APPROVAL,
    run_dir=DEFAULT_RUN_DIR,
    theme_dir=None,
    motion_contract_path=DEFAULT_MOTION_CONTRACT,
    validation_output=None,
    validator_output=None,
    clawd_validator=DEFAULT_CLAWD_VALIDATOR,
):
    approval_path = Path(approval_path)
    run_dir = Path(run_dir)
    theme_dir = Path(theme_dir) if theme_dir is not None else run_dir / "theme"
    validation_output = (
        Path(validation_output) if validation_output is not None else run_dir / "qa" / "phase3-validation.json"
    )
    validator_output = (
        Path(validator_output) if validator_output is not None else run_dir / "qa" / "clawd-validator.txt"
    )
    motion_contract_path = Path(motion_contract_path)

    approval.validate_source_set_approval(approval_path)
    approval_data = load_json(approval_path)
    if approval_data.get("sourceSetId") != SOURCE_SET_ID:
        raise ValueError("Phase 3 sourceSetId must be seamsafe-promoted")

    masters_dir = resolve_rendered_masters(approval_data)
    validate_approved_master_files(approval_data, masters_dir)
    motion_contract = load_motion_contract(motion_contract_path)
    hq.assert_no_exporter_inbetweens(motion_contract)
    hq.export_theme(
        masters_dir,
        theme_dir,
        include_ultra=False,
        motion_contract=motion_contract,
    )
    build_manifest = theme_dir / "qa" / "build-manifest.json"
    validate_phase3_runtime_asset_set(theme_dir)
    hq.validate_lineage(theme_dir)
    hq.validate_theme_assets(theme_dir, motion_contract=motion_contract)

    validator_result = run_clawd_validator(theme_dir, clawd_validator)
    _write_validator_text(validator_output, validator_result)
    evidence = build_validation_evidence(
        approval_path=approval_path,
        approval_data=approval_data,
        theme_dir=theme_dir,
        build_manifest=build_manifest,
        motion_contract_path=motion_contract_path,
        validator_result=validator_result,
        validator_output=validator_output,
    )
    write_json(validation_output, evidence)
    if validator_result.exit_code != 0:
        raise ValueError("Clawd validator failed")
    return StageResult(
        theme_dir=theme_dir,
        validation_json=validation_output,
        validator_text=validator_output,
        build_manifest=build_manifest,
    )


def _build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    stage = subparsers.add_parser("stage", help="stage Phase 3 Clawd-compatible theme evidence")
    stage.add_argument("--approval", type=Path, default=DEFAULT_APPROVAL)
    stage.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    stage.add_argument("--theme-dir", type=Path, default=None)
    stage.add_argument("--motion-contract", type=Path, default=DEFAULT_MOTION_CONTRACT)
    stage.add_argument("--validation-output", type=Path, default=None)
    stage.add_argument("--validator-output", type=Path, default=None)
    stage.add_argument("--clawd-validator", type=Path, default=DEFAULT_CLAWD_VALIDATOR)
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    if args.command == "stage":
        result = stage_theme(
            approval_path=args.approval,
            run_dir=args.run_dir,
            theme_dir=args.theme_dir,
            motion_contract_path=args.motion_contract,
            validation_output=args.validation_output,
            validator_output=args.validator_output,
            clawd_validator=args.clawd_validator,
        )
        print(f"wrote {result.validation_json}")


if __name__ == "__main__":
    main()
