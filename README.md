# Nintendo DS US ROM Sorter

This repository contains a native macOS app that scans Nintendo DS ROM ZIP
archives and discards any archives that are not identified as US releases.

The app supports:

- `.zip` archives containing an `.nds` or `.srl` file, without extracting them
- loose `.nds` and `.srl` ROM files, if you ever have any
- common filename markers such as `(USA)`, `(U)`, `(Europe)`, and `(Japan)`
- Nintendo DS header destination codes when a filename has no region marker

## Requirements

- macOS 13 Ventura or newer
- Xcode 15 or newer

No third-party libraries are required. The app is written in SwiftUI and uses
the `unzip` tool that ships with macOS to inspect ZIP archives.

## Run the macOS app

1. Open `macos/NDSRomSorter/NDSRomSorter.xcodeproj` in Xcode.
2. Select the `NDSRomSorter` scheme.
3. Click **Run**.

In the app:

1. Click **Choose...** under **ROM ZIP Folder** and choose the folder containing
   your Nintendo DS ZIP archives.
2. Leave **Dry Run only** checked and click **Scan / Sort**.
3. Review the results log to confirm which ZIP archives would move.
4. Uncheck **Dry Run only** and click **Scan / Sort** again to move non-US ZIP
   archives into `discarded_non_us`.

The app also lets you choose a custom discard folder, search subfolders, keep
unknown-region ZIP archives, or delete non-US ZIP archives instead of moving
them.

## Build a standalone `.app`

In Xcode:

1. Choose **Product > Archive**.
2. When the archive opens, choose **Distribute App**.
3. Choose **Copy App** to export a standalone `NDSRomSorter.app`.

You can then move that `.app` into `/Applications`.

## Optional terminal helper

The repository still includes a Python terminal helper with the same sorting
rules. You do not need it to run the native macOS app.

### Safe preview

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
