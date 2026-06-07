from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "sort_nds_us_roms.py"
SPEC = importlib.util.spec_from_file_location("sort_nds_us_roms", SCRIPT_PATH)
assert SPEC is not None
sort_nds_us_roms = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = sort_nds_us_roms
SPEC.loader.exec_module(sort_nds_us_roms)


def fake_nds_header(destination_code: str) -> bytes:
    return b"FAKE GAME   ABC" + destination_code.encode("ascii") + b"\0" * 32


def write_zipped_rom(path: Path, destination_code: str) -> None:
    with zipfile.ZipFile(path, "w") as zip_file:
        zip_file.writestr("game.nds", fake_nds_header(destination_code))


class SortNdsUsRomsTests(unittest.TestCase):
    def test_classifies_us_filename_marker(self) -> None:
        result = sort_nds_us_roms.classify_rom(Path("Mario Kart DS (USA).nds"))

        self.assertEqual(result.decision, sort_nds_us_roms.RegionDecision.US)

    def test_classifies_non_us_filename_marker(self) -> None:
        result = sort_nds_us_roms.classify_rom(Path("Mario Kart DS (Europe).nds"))

        self.assertEqual(result.decision, sort_nds_us_roms.RegionDecision.NON_US)

    def test_falls_back_to_nds_header_destination_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rom = Path(tmp) / "unmarked.nds"
            rom.write_bytes(fake_nds_header("E"))

            result = sort_nds_us_roms.classify_rom(rom)

        self.assertEqual(result.decision, sort_nds_us_roms.RegionDecision.US)

    def test_inspects_nds_header_inside_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "unmarked.zip"
            write_zipped_rom(archive, "J")

            result = sort_nds_us_roms.classify_rom(archive)

        self.assertEqual(result.decision, sort_nds_us_roms.RegionDecision.NON_US)

    def test_folder_of_zip_archives_moves_non_us_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            us_zip = root / "kept.zip"
            non_us_zip = root / "discarded.zip"
            write_zipped_rom(us_zip, "E")
            write_zipped_rom(non_us_zip, "J")

            roms = sort_nds_us_roms.iter_roms(
                [root],
                recursive=True,
                discard_dir_name=sort_nds_us_roms.DEFAULT_DISCARD_DIR,
            )
            actions = sort_nds_us_roms.plan_actions(
                roms,
                sources=[root],
                discard_dir=None,
                keep_unknown=False,
                delete=False,
            )
            for action in actions:
                sort_nds_us_roms.apply_action(action, dry_run=False)

            self.assertTrue(us_zip.exists())
            self.assertFalse(non_us_zip.exists())
            self.assertTrue((root / "discarded_non_us" / non_us_zip.name).exists())

    def test_plan_moves_unknown_roms_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "unmarked.nds"
            rom.write_bytes(b"not a real header")

            actions = sort_nds_us_roms.plan_actions(
                [rom],
                sources=[root],
                discard_dir=None,
                keep_unknown=False,
                delete=False,
            )

        self.assertEqual(actions[0].action, "move")
        self.assertEqual(actions[0].destination.name, "unmarked.nds")
        self.assertEqual(actions[0].destination.parent.name, "discarded_non_us")

    def test_apply_action_moves_non_us_rom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rom = root / "game (Japan).nds"
            rom.write_bytes(fake_nds_header("J"))
            destination = root / "discarded_non_us" / rom.name
            action = sort_nds_us_roms.PlannedAction(
                rom,
                sort_nds_us_roms.classify_rom(rom),
                "move",
                destination,
            )

            sort_nds_us_roms.apply_action(action, dry_run=False)

            self.assertFalse(rom.exists())
            self.assertTrue(destination.exists())

    def test_format_action_for_dry_run_move(self) -> None:
        source = Path("/roms/game.zip")
        destination = Path("/roms/discarded_non_us/game.zip")
        action = sort_nds_us_roms.PlannedAction(
            source,
            sort_nds_us_roms.Classification(
                sort_nds_us_roms.RegionDecision.NON_US,
                "zip member 'game.nds' header destination code J (Japan)",
            ),
            "move",
            destination,
        )

        formatted = sort_nds_us_roms.format_action(action, dry_run=True)

        self.assertIn("WOULD MOVE", formatted)
        self.assertIn(str(source), formatted)
        self.assertIn(str(destination), formatted)


if __name__ == "__main__":
    unittest.main()
