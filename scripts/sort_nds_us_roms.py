#!/usr/bin/env python3
"""Keep Nintendo DS ROMs that are identified as US releases.

By default this script moves ROM files that are not identified as US releases
into a ``discarded_non_us`` folder next to the scanned folder. Use ``--dry-run``
first to preview changes.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re
import shutil
import sys
import zipfile


SUPPORTED_SUFFIXES = {".nds", ".srl", ".zip"}
DEFAULT_DISCARD_DIR = "discarded_non_us"

US_REGION_MARKERS = {
    "u",
    "us",
    "usa",
    "united states",
    "united states of america",
}

NON_US_REGION_MARKERS = {
    "australia",
    "brazil",
    "canada",
    "china",
    "chinese",
    "e",
    "europe",
    "eur",
    "france",
    "germany",
    "italy",
    "j",
    "japan",
    "japanese",
    "korea",
    "korean",
    "netherlands",
    "p",
    "spain",
    "uk",
    "united kingdom",
    "world",
}

# The fourth character in a Nintendo DS game code is the destination/language
# code used by product IDs such as NTR-ABCE-USA. E is the common US code.
NDS_DESTINATION_CODES = {
    "E": "United States",
    "P": "Europe",
    "J": "Japan",
    "K": "Korea",
    "C": "China",
    "D": "Germany",
    "F": "France",
    "I": "Italy",
    "S": "Spain",
    "H": "Netherlands",
    "U": "Australia",
}


class RegionDecision(Enum):
    US = "us"
    NON_US = "non_us"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Classification:
    decision: RegionDecision
    reason: str


@dataclass(frozen=True)
class PlannedAction:
    path: Path
    classification: Classification
    action: str
    destination: Path | None = None


def normalize_marker(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def split_region_markers(value: str) -> list[str]:
    return [
        normalize_marker(piece)
        for piece in re.split(r"[,;/+&|]", value)
        if normalize_marker(piece)
    ]


def bracketed_filename_markers(path: Path) -> list[str]:
    markers: list[str] = []
    for match in re.findall(r"[\(\[\{]([^\)\]\}]+)[\)\]\}]", path.stem):
        markers.extend(split_region_markers(match))
    return markers


def classify_from_filename(path: Path) -> Classification:
    markers = bracketed_filename_markers(path)
    for marker in markers:
        if marker in US_REGION_MARKERS:
            return Classification(RegionDecision.US, f"filename marker '{marker}'")

    for marker in markers:
        if marker in NON_US_REGION_MARKERS:
            return Classification(RegionDecision.NON_US, f"filename marker '{marker}'")

    normalized_name = normalize_marker(path.stem.replace("_", " ").replace("-", " "))
    for marker in sorted(US_REGION_MARKERS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(marker)}\b", normalized_name):
            return Classification(RegionDecision.US, f"filename contains '{marker}'")

    for marker in sorted(NON_US_REGION_MARKERS, key=len, reverse=True):
        if len(marker) == 1:
            continue
        if re.search(rf"\b{re.escape(marker)}\b", normalized_name):
            return Classification(RegionDecision.NON_US, f"filename contains '{marker}'")

    return Classification(RegionDecision.UNKNOWN, "no filename region marker")


def classify_from_header_bytes(header: bytes) -> Classification:
    if len(header) < 16:
        return Classification(RegionDecision.UNKNOWN, "ROM header is too short")

    game_code = header[12:16]
    try:
        game_code_text = game_code.decode("ascii")
    except UnicodeDecodeError:
        return Classification(RegionDecision.UNKNOWN, "ROM header game code is not ASCII")

    if not re.fullmatch(r"[A-Z0-9]{4}", game_code_text):
        return Classification(RegionDecision.UNKNOWN, "ROM header game code is not recognized")

    destination_code = game_code_text[-1]
    destination = NDS_DESTINATION_CODES.get(destination_code)
    if destination_code == "E":
        return Classification(RegionDecision.US, f"header destination code E ({destination})")
    if destination:
        return Classification(
            RegionDecision.NON_US,
            f"header destination code {destination_code} ({destination})",
        )

    return Classification(
        RegionDecision.UNKNOWN,
        f"header destination code {destination_code} is not recognized",
    )


def classify_from_nds_file(path: Path) -> Classification:
    try:
        with path.open("rb") as rom:
            return classify_from_header_bytes(rom.read(16))
    except OSError as exc:
        return Classification(RegionDecision.UNKNOWN, f"could not read ROM header: {exc}")


def classify_from_zip(path: Path) -> Classification:
    try:
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                if Path(member.filename).suffix.lower() not in {".nds", ".srl"}:
                    continue
                with archive.open(member) as rom:
                    result = classify_from_header_bytes(rom.read(16))
                return Classification(
                    result.decision,
                    f"zip member '{member.filename}' {result.reason}",
                )
    except (OSError, zipfile.BadZipFile) as exc:
        return Classification(RegionDecision.UNKNOWN, f"could not inspect zip: {exc}")

    return Classification(RegionDecision.UNKNOWN, "zip does not contain an NDS ROM")


def classify_rom(path: Path) -> Classification:
    filename_result = classify_from_filename(path)
    if filename_result.decision is not RegionDecision.UNKNOWN:
        return filename_result

    suffix = path.suffix.lower()
    if suffix in {".nds", ".srl"}:
        return classify_from_nds_file(path)
    if suffix == ".zip":
        return classify_from_zip(path)

    return Classification(RegionDecision.UNKNOWN, "unsupported file type")


def iter_roms(paths: list[Path], recursive: bool, discard_dir_name: str) -> list[Path]:
    roms: list[Path] = []
    for source in paths:
        if source.is_file():
            if source.suffix.lower() in SUPPORTED_SUFFIXES:
                roms.append(source)
            continue

        if not source.is_dir():
            print(f"WARNING: {source} does not exist or is not readable", file=sys.stderr)
            continue

        iterator = source.rglob("*") if recursive else source.glob("*")
        for candidate in iterator:
            if not candidate.is_file():
                continue
            if discard_dir_name in candidate.relative_to(source).parts:
                continue
            if candidate.suffix.lower() in SUPPORTED_SUFFIXES:
                roms.append(candidate)

    return sorted(set(roms))


def default_discard_dir_for(path: Path, discard_dir_name: str) -> Path:
    if path.is_dir():
        return path / discard_dir_name
    return path.parent / discard_dir_name


def unique_destination(destination: Path, reserved: set[Path] | None = None) -> Path:
    reserved = reserved or set()
    if not destination.exists() and destination not in reserved:
        return destination

    stem = destination.stem
    suffix = destination.suffix
    parent = destination.parent
    counter = 1
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists() and candidate not in reserved:
            return candidate
        counter += 1


def destination_for(
    path: Path,
    sources: list[Path],
    discard_dir: Path | None,
    reserved: set[Path],
) -> Path:
    if discard_dir is not None:
        base = discard_dir
    else:
        owning_sources = [source for source in sources if source.is_dir() and path.is_relative_to(source)]
        root = max(owning_sources, key=lambda item: len(item.parts)) if owning_sources else path.parent
        base = default_discard_dir_for(root, DEFAULT_DISCARD_DIR)

    return unique_destination(base / path.name, reserved)


def plan_actions(
    roms: list[Path],
    sources: list[Path],
    discard_dir: Path | None,
    keep_unknown: bool,
    delete: bool,
) -> list[PlannedAction]:
    actions: list[PlannedAction] = []
    reserved_destinations: set[Path] = set()
    for rom in roms:
        classification = classify_rom(rom)
        if classification.decision is RegionDecision.US:
            actions.append(PlannedAction(rom, classification, "keep"))
            continue
        if classification.decision is RegionDecision.UNKNOWN and keep_unknown:
            actions.append(PlannedAction(rom, classification, "keep"))
            continue

        if delete:
            actions.append(PlannedAction(rom, classification, "delete"))
        else:
            destination = destination_for(rom, sources, discard_dir, reserved_destinations)
            reserved_destinations.add(destination)
            actions.append(PlannedAction(rom, classification, "move", destination))

    return actions


def apply_action(action: PlannedAction, dry_run: bool) -> None:
    if dry_run or action.action == "keep":
        return

    if action.action == "delete":
        action.path.unlink()
        return

    if action.action == "move":
        if action.destination is None:
            raise ValueError("move action is missing a destination")
        action.destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(action.path), str(action.destination))
        return

    raise ValueError(f"unknown action {action.action!r}")


def print_action(action: PlannedAction, dry_run: bool) -> None:
    prefix = "WOULD " if dry_run and action.action != "keep" else ""
    reason = action.classification.reason
    if action.action == "keep":
        print(f"KEEP    {action.path} ({reason})")
    elif action.action == "delete":
        print(f"{prefix}DELETE  {action.path} ({reason})")
    elif action.action == "move":
        print(f"{prefix}MOVE    {action.path} -> {action.destination} ({reason})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Move or delete Nintendo DS ROMs that are not identified as US releases.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="ROM files or folders to scan. Supports .nds, .srl, and .zip files.",
    )
    parser.add_argument(
        "--discard-dir",
        type=Path,
        help=(
            "Folder for non-US ROMs. Defaults to a discarded_non_us folder next "
            "to each scanned folder."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without moving or deleting files.",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Permanently delete non-US ROMs instead of moving them.",
    )
    parser.add_argument(
        "--keep-unknown",
        action="store_true",
        help="Keep ROMs whose region cannot be identified.",
    )
    parser.add_argument(
        "--non-recursive",
        action="store_true",
        help="Only scan the top level of each folder.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    sources = [path.expanduser().resolve() for path in args.paths]
    discard_dir = args.discard_dir.expanduser().resolve() if args.discard_dir else None
    roms = iter_roms(sources, recursive=not args.non_recursive, discard_dir_name=DEFAULT_DISCARD_DIR)
    actions = plan_actions(
        roms,
        sources=sources,
        discard_dir=discard_dir,
        keep_unknown=args.keep_unknown,
        delete=args.delete,
    )

    for action in actions:
        print_action(action, dry_run=args.dry_run)
        try:
            apply_action(action, dry_run=args.dry_run)
        except OSError as exc:
            print(f"ERROR: could not {action.action} {action.path}: {exc}", file=sys.stderr)
            return 1

    kept = sum(1 for action in actions if action.action == "keep")
    discarded = len(actions) - kept
    print(f"\nScanned {len(roms)} ROM file(s): kept {kept}, discarded {discarded}.")
    if args.dry_run:
        print("Dry run only; no files were changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
