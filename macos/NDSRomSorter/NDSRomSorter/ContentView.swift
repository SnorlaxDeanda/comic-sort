import AppKit
import SwiftUI

struct ContentView: View {
    @State private var sourceURL: URL?
    @State private var discardURL: URL?
    @State private var dryRun = true
    @State private var recursive = true
    @State private var keepUnknown = false
    @State private var deleteNonUS = false
    @State private var isRunning = false
    @State private var status = "Choose a folder of Nintendo DS ZIP archives."
    @State private var logText = """
    Tip: leave Dry Run enabled first. When the log looks right, uncheck Dry Run to move non-US ZIP archives.

    """

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            header
            folderPicker(
                title: "ROM ZIP Folder",
                path: sourceURL?.path ?? "No folder selected",
                buttonTitle: "Choose...",
                action: chooseSourceFolder
            )
            folderPicker(
                title: "Discard Folder",
                path: discardURL?.path ?? "Default: discarded_non_us inside the ROM ZIP folder",
                buttonTitle: "Choose...",
                action: chooseDiscardFolder,
                clearAction: { discardURL = nil }
            )
            options
            controls
            log
        }
        .padding(20)
        .frame(minWidth: 820, minHeight: 620)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Nintendo DS US ROM Sorter")
                .font(.largeTitle)
                .fontWeight(.semibold)
            Text("Scans ZIP archives, keeps US releases, and moves or deletes anything not identified as US.")
                .foregroundStyle(.secondary)
        }
    }

    private func folderPicker(
        title: String,
        path: String,
        buttonTitle: String,
        action: @escaping () -> Void,
        clearAction: (() -> Void)? = nil
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.headline)
            HStack {
                Text(path)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(8)
                    .background(Color(nsColor: .textBackgroundColor))
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                Button(buttonTitle, action: action)
                    .disabled(isRunning)
                if let clearAction {
                    Button("Clear", action: clearAction)
                        .disabled(isRunning)
                }
            }
        }
    }

    private var options: some View {
        GroupBox("Options") {
            Grid(alignment: .leading, horizontalSpacing: 24, verticalSpacing: 10) {
                GridRow {
                    Toggle("Dry Run only", isOn: $dryRun)
                    Toggle("Search subfolders", isOn: $recursive)
                }
                GridRow {
                    Toggle("Keep unknown-region ZIPs", isOn: $keepUnknown)
                    Toggle("Delete instead of moving", isOn: $deleteNonUS)
                }
            }
            .disabled(isRunning)
            .padding(.vertical, 4)
        }
    }

    private var controls: some View {
        HStack {
            Button {
                startSort()
            } label: {
                if isRunning {
                    ProgressView()
                        .controlSize(.small)
                } else {
                    Text("Scan / Sort")
                }
            }
            .keyboardShortcut(.defaultAction)
            .disabled(isRunning || sourceURL == nil)

            Button("Clear Log") {
                logText = ""
            }
            .disabled(isRunning)

            Spacer()

            Text(status)
                .foregroundStyle(.secondary)
        }
    }

    private var log: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Results")
                .font(.headline)
            TextEditor(text: $logText)
                .font(.system(.body, design: .monospaced))
                .textSelection(.enabled)
                .border(Color(nsColor: .separatorColor))
        }
    }

    private func chooseSourceFolder() {
        if let selected = chooseFolder(title: "Choose folder containing Nintendo DS ZIP archives") {
            sourceURL = selected
            status = "Ready to scan."
        }
    }

    private func chooseDiscardFolder() {
        if let selected = chooseFolder(title: "Choose discard folder") {
            discardURL = selected
        }
    }

    private func chooseFolder(title: String) -> URL? {
        let panel = NSOpenPanel()
        panel.title = title
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.canCreateDirectories = true
        return panel.runModal() == .OK ? panel.url : nil
    }

    private func startSort() {
        guard let sourceURL else {
            showAlert(title: "Missing folder", message: "Choose a folder containing Nintendo DS ZIP archives.")
            return
        }

        if deleteNonUS && !dryRun && !confirmDelete() {
            return
        }

        isRunning = true
        status = "Scanning..."
        appendLog("")
        appendLog("Scanning \(sourceURL.path)...")

        let options = SortOptions(
            sourceURL: sourceURL,
            discardURL: discardURL,
            dryRun: dryRun,
            deleteNonUS: deleteNonUS,
            keepUnknown: keepUnknown,
            recursive: recursive
        )

        DispatchQueue.global(qos: .userInitiated).async {
            do {
                let result = try RomSorter().run(options: options)
                let lines = result.actions.map { $0.formatted(dryRun: options.dryRun) }
                let summary = summaryText(for: result, dryRun: options.dryRun)
                DispatchQueue.main.async {
                    appendLog(lines.joined(separator: "\n"))
                    appendLog("")
                    appendLog(summary)
                    status = "Finished"
                    isRunning = false
                }
            } catch {
                DispatchQueue.main.async {
                    appendLog("")
                    appendLog("ERROR: \(error.localizedDescription)")
                    status = "Error"
                    isRunning = false
                    showAlert(title: "Sort failed", message: error.localizedDescription)
                }
            }
        }
    }

    private func appendLog(_ message: String) {
        if !logText.isEmpty && !logText.hasSuffix("\n") {
            logText += "\n"
        }
        logText += message + "\n"
    }

    private func confirmDelete() -> Bool {
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = "Permanently delete non-US ZIP archives?"
        alert.informativeText = "This cannot be undone. Run a dry run first if you have not reviewed the results."
        alert.addButton(withTitle: "Delete")
        alert.addButton(withTitle: "Cancel")
        return alert.runModal() == .alertFirstButtonReturn
    }

    private func showAlert(title: String, message: String) {
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = title
        alert.informativeText = message
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }
}

private func summaryText(for result: SortResult, dryRun: Bool) -> String {
    var summary = "Scanned \(result.actions.count) ZIP/ROM file(s): kept \(result.keptCount), discarded \(result.discardedCount)."
    if dryRun {
        summary += " Dry run only; no files were changed."
    }
    return summary
}
