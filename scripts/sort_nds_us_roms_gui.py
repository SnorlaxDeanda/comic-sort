#!/usr/bin/env python3
"""Graphical front end for the US ROM ZIP sorter."""

from __future__ import annotations

from pathlib import Path
import queue
import sys
import threading
import traceback
from typing import Any

import sort_nds_us_roms


def import_tkinter() -> tuple[Any, Any, Any, Any, Any]:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, scrolledtext, ttk
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Tkinter is not installed for this Python. On macOS, install Python "
            "from python.org or use a Python build with Tk support, then run "
            "this script again."
        ) from exc

    return tk, filedialog, messagebox, scrolledtext, ttk


class SorterGui:
    def __init__(self, root: Any, tk_modules: tuple[Any, Any, Any, Any, Any]) -> None:
        self.root = root
        self.tk, self.filedialog, self.messagebox, self.scrolledtext, self.ttk = tk_modules
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.worker: threading.Thread | None = None

        self.source_path = self.tk.StringVar()
        self.discard_path = self.tk.StringVar()
        self.dry_run = self.tk.BooleanVar(value=True)
        self.delete = self.tk.BooleanVar(value=False)
        self.keep_unknown = self.tk.BooleanVar(value=False)
        self.recursive = self.tk.BooleanVar(value=True)
        self.status = self.tk.StringVar(value="Choose a folder of ROM ZIP archives.")

        self.root.title("US ROM Sorter")
        self.root.minsize(760, 520)
        self._build()
        self._poll_events()

    def _build(self) -> None:
        padding = {"padx": 10, "pady": 6}
        main = self.ttk.Frame(self.root)
        main.pack(fill=self.tk.BOTH, expand=True)

        source_frame = self.ttk.LabelFrame(main, text="ROM ZIP folder")
        source_frame.pack(fill=self.tk.X, **padding)
        self.ttk.Entry(source_frame, textvariable=self.source_path).pack(
            side=self.tk.LEFT,
            fill=self.tk.X,
            expand=True,
            padx=(10, 6),
            pady=10,
        )
        self.ttk.Button(source_frame, text="Browse...", command=self.choose_source).pack(
            side=self.tk.LEFT,
            padx=(0, 10),
            pady=10,
        )

        discard_frame = self.ttk.LabelFrame(main, text="Discard folder (optional)")
        discard_frame.pack(fill=self.tk.X, **padding)
        self.ttk.Entry(discard_frame, textvariable=self.discard_path).pack(
            side=self.tk.LEFT,
            fill=self.tk.X,
            expand=True,
            padx=(10, 6),
            pady=10,
        )
        self.ttk.Button(discard_frame, text="Browse...", command=self.choose_discard).pack(
            side=self.tk.LEFT,
            padx=(0, 6),
            pady=10,
        )
        self.ttk.Button(discard_frame, text="Clear", command=lambda: self.discard_path.set("")).pack(
            side=self.tk.LEFT,
            padx=(0, 10),
            pady=10,
        )

        options = self.ttk.LabelFrame(main, text="Options")
        options.pack(fill=self.tk.X, **padding)
        self.ttk.Checkbutton(options, text="Dry run only", variable=self.dry_run).grid(
            row=0,
            column=0,
            sticky=self.tk.W,
            padx=10,
            pady=6,
        )
        self.ttk.Checkbutton(options, text="Search subfolders", variable=self.recursive).grid(
            row=0,
            column=1,
            sticky=self.tk.W,
            padx=10,
            pady=6,
        )
        self.ttk.Checkbutton(options, text="Keep unknown-region ZIPs", variable=self.keep_unknown).grid(
            row=1,
            column=0,
            sticky=self.tk.W,
            padx=10,
            pady=6,
        )
        self.ttk.Checkbutton(options, text="Delete instead of moving", variable=self.delete).grid(
            row=1,
            column=1,
            sticky=self.tk.W,
            padx=10,
            pady=6,
        )

        buttons = self.ttk.Frame(main)
        buttons.pack(fill=self.tk.X, **padding)
        self.run_button = self.ttk.Button(buttons, text="Scan / Sort", command=self.start_sort)
        self.run_button.pack(side=self.tk.LEFT, padx=(0, 8))
        self.clear_button = self.ttk.Button(buttons, text="Clear Log", command=self.clear_log)
        self.clear_button.pack(side=self.tk.LEFT)
        self.ttk.Label(buttons, textvariable=self.status).pack(side=self.tk.RIGHT)

        log_frame = self.ttk.LabelFrame(main, text="Results")
        log_frame.pack(fill=self.tk.BOTH, expand=True, **padding)
        self.log = self.scrolledtext.ScrolledText(log_frame, height=16, wrap=self.tk.WORD)
        self.log.pack(fill=self.tk.BOTH, expand=True, padx=10, pady=10)

        note = (
            "Tip: leave Dry run enabled first. When the log looks right, uncheck "
            "Dry run to move non-US ZIP archives."
        )
        self.write_log(note)

    def choose_source(self) -> None:
        selected = self.filedialog.askdirectory(title="Choose folder containing ROM ZIP archives")
        if selected:
            self.source_path.set(selected)

    def choose_discard(self) -> None:
        selected = self.filedialog.askdirectory(title="Choose discard folder")
        if selected:
            self.discard_path.set(selected)

    def clear_log(self) -> None:
        self.log.delete("1.0", self.tk.END)

    def write_log(self, message: str) -> None:
        self.log.insert(self.tk.END, message.rstrip() + "\n")
        self.log.see(self.tk.END)

    def start_sort(self) -> None:
        if self.worker and self.worker.is_alive():
            return

        source = self.source_path.get().strip()
        if not source:
            self.messagebox.showerror("Missing folder", "Choose a folder of ROM ZIP archives.")
            return

        source_path = Path(source).expanduser()
        if not source_path.is_dir():
            self.messagebox.showerror("Invalid folder", f"{source_path} is not a readable folder.")
            return

        if self.delete.get() and not self.dry_run.get():
            confirmed = self.messagebox.askyesno(
                "Confirm delete",
                "This will permanently delete non-US ZIP archives. Continue?",
                icon=self.messagebox.WARNING,
            )
            if not confirmed:
                return

        discard_text = self.discard_path.get().strip()
        discard_path = Path(discard_text).expanduser() if discard_text else None

        self.run_button.configure(state=self.tk.DISABLED)
        self.status.set("Scanning...")
        self.write_log("")
        self.write_log(f"Scanning {source_path}...")

        self.worker = threading.Thread(
            target=self._run_sort,
            kwargs={
                "source_path": source_path,
                "discard_path": discard_path,
                "dry_run": self.dry_run.get(),
                "delete": self.delete.get(),
                "keep_unknown": self.keep_unknown.get(),
                "recursive": self.recursive.get(),
            },
            daemon=True,
        )
        self.worker.start()

    def _run_sort(
        self,
        source_path: Path,
        discard_path: Path | None,
        dry_run: bool,
        delete: bool,
        keep_unknown: bool,
        recursive: bool,
    ) -> None:
        try:
            source = source_path.resolve()
            discard = discard_path.resolve() if discard_path else None
            roms = sort_nds_us_roms.iter_roms(
                [source],
                recursive=recursive,
                discard_dir_name=sort_nds_us_roms.DEFAULT_DISCARD_DIR,
            )
            actions = sort_nds_us_roms.plan_actions(
                roms,
                sources=[source],
                discard_dir=discard,
                keep_unknown=keep_unknown,
                delete=delete,
            )

            for action in actions:
                self.events.put(("log", sort_nds_us_roms.format_action(action, dry_run)))
                sort_nds_us_roms.apply_action(action, dry_run=dry_run)

            kept = sum(1 for action in actions if action.action == "keep")
            discarded = len(actions) - kept
            summary = f"Scanned {len(roms)} ZIP/ROM file(s): kept {kept}, discarded {discarded}."
            if dry_run:
                summary += " Dry run only; no files were changed."
            self.events.put(("done", summary))
        except Exception:
            self.events.put(("error", traceback.format_exc()))

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self.write_log(payload)
                elif kind == "done":
                    self.write_log("")
                    self.write_log(payload)
                    self.status.set("Finished")
                    self.run_button.configure(state=self.tk.NORMAL)
                elif kind == "error":
                    self.write_log(payload)
                    self.status.set("Error")
                    self.run_button.configure(state=self.tk.NORMAL)
                    self.messagebox.showerror("Sort failed", "The sort failed. See the results log.")
        except queue.Empty:
            pass

        self.root.after(100, self._poll_events)


def main() -> int:
    try:
        tk_modules = import_tkinter()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    tk = tk_modules[0]
    root = tk.Tk()
    SorterGui(root, tk_modules)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
