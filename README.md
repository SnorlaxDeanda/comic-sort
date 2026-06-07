# Nintendo DS US ROM sorter

This repository contains a small Python utility that scans Nintendo DS ROMs and
discards files that are not identified as US releases.

The script supports:

- `.nds` and `.srl` ROM files
- `.zip` archives containing an `.nds` or `.srl` file
- common filename markers such as `(USA)`, `(U)`, `(Europe)`, and `(Japan)`
- Nintendo DS header destination codes when a filename has no region marker

## Requirements

- Python 3.10 or newer

No third-party packages are required, so it works on Apple Silicon Macs as long
as `python3` is available.

## Safe preview

Run a dry run first so you can see exactly what would be moved:

```sh
python3 scripts/sort_nds_us_roms.py --dry-run "/path/to/NDS ROMs"
```

## Move non-US ROMs into a discard folder

By default, non-US and unknown-region ROMs are moved into a
`discarded_non_us` folder next to the scanned folder:

```sh
python3 scripts/sort_nds_us_roms.py "/path/to/NDS ROMs"
```

To choose a specific discard folder:

```sh
python3 scripts/sort_nds_us_roms.py \
  --discard-dir "/path/to/non-us-roms" \
  "/path/to/NDS ROMs"
```

## Permanently delete non-US ROMs

Only use `--delete` after you have reviewed a dry run:

```sh
python3 scripts/sort_nds_us_roms.py --delete "/path/to/NDS ROMs"
```

## Keep unknown-region ROMs

The default is strict: anything that cannot be identified as US is discarded.
If you would rather keep uncertain files for manual review, add
`--keep-unknown`:

```sh
python3 scripts/sort_nds_us_roms.py --keep-unknown "/path/to/NDS ROMs"
```

## Run tests

```sh
python3 -m unittest discover -s tests
```
