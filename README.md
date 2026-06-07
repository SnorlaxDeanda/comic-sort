# Nintendo DS US ROM sorter

This repository contains a small Python utility that scans Nintendo DS ROM ZIP
archives and discards any archives that are not identified as US releases.

The script supports:

- `.zip` archives containing an `.nds` or `.srl` file, without extracting them
- loose `.nds` and `.srl` ROM files, if you ever have any
- common filename markers such as `(USA)`, `(U)`, `(Europe)`, and `(Japan)`
- Nintendo DS header destination codes when a filename has no region marker

## Requirements

- Python 3.10 or newer
- Tkinter for the GUI

No third-party packages are required. On macOS, the Python installer from
[python.org](https://www.python.org/downloads/macos/) includes Tkinter, which
the GUI uses.

## Run the GUI

On your Mac, open Terminal in this repository and run:

```sh
python3 scripts/sort_nds_us_roms_gui.py
```

In the window:

1. Click **Browse...** under **ROM ZIP folder** and choose the folder containing
   your Nintendo DS ZIP archives.
2. Leave **Dry run only** checked and click **Scan / Sort**.
3. Review the results log to confirm which ZIP archives would move.
4. Uncheck **Dry run only** and click **Scan / Sort** again to move non-US ZIP
   archives into `discarded_non_us`.

The GUI also lets you choose a custom discard folder, search subfolders, keep
unknown-region ZIP archives, or delete non-US ZIP archives instead of moving
them.

## Run from Terminal

### Safe preview

Run a dry run first so you can see exactly which ZIP archives would be moved:

```sh
python3 scripts/sort_nds_us_roms.py --dry-run "/path/to/NDS ZIPs"
```

### Move non-US ZIP archives into a discard folder

By default, non-US and unknown-region ZIP archives are moved into a
`discarded_non_us` folder next to the scanned folder:

```sh
python3 scripts/sort_nds_us_roms.py "/path/to/NDS ZIPs"
```

To choose a specific discard folder:

```sh
python3 scripts/sort_nds_us_roms.py \
  --discard-dir "/path/to/non-us-roms" \
  "/path/to/NDS ZIPs"
```

### Permanently delete non-US ZIP archives

Only use `--delete` after you have reviewed a dry run. This deletes the whole
ZIP archive for each non-US match:

```sh
python3 scripts/sort_nds_us_roms.py --delete "/path/to/NDS ZIPs"
```

### Keep unknown-region ZIP archives

The default is strict: anything that cannot be identified as US is discarded.
If you would rather keep uncertain files for manual review, add
`--keep-unknown`:

```sh
python3 scripts/sort_nds_us_roms.py --keep-unknown "/path/to/NDS ZIPs"
```

## Run tests

```sh
python3 -m unittest discover -s tests
```
