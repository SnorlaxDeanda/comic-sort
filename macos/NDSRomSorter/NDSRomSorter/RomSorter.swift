import Foundation

enum RegionDecision {
    case us
    case nonUS
    case unknown
}

struct Classification {
    let decision: RegionDecision
    let reason: String
}

enum PlannedActionKind {
    case keep
    case move
    case delete
}

struct PlannedAction: Identifiable {
    let id = UUID()
    let url: URL
    let classification: Classification
    let kind: PlannedActionKind
    let destination: URL?

    func formatted(dryRun: Bool) -> String {
        let prefix = dryRun && kind != .keep ? "WOULD " : ""
        switch kind {
        case .keep:
            return "KEEP    \(url.path) (\(classification.reason))"
        case .delete:
            return "\(prefix)DELETE  \(url.path) (\(classification.reason))"
        case .move:
            return "\(prefix)MOVE    \(url.path) -> \(destination?.path ?? "(missing destination)") (\(classification.reason))"
        }
    }
}

struct SortOptions {
    let sourceURL: URL
    let discardURL: URL?
    let dryRun: Bool
    let deleteNonUS: Bool
    let keepUnknown: Bool
    let recursive: Bool
}

struct SortResult {
    let actions: [PlannedAction]

    var keptCount: Int {
        actions.filter { $0.kind == .keep }.count
    }

    var discardedCount: Int {
        actions.count - keptCount
    }
}

enum SorterError: LocalizedError {
    case missingDestination(URL)
    case shellFailed(String)

    var errorDescription: String? {
        switch self {
        case .missingDestination(let url):
            return "Move action for \(url.path) did not have a destination."
        case .shellFailed(let message):
            return message
        }
    }
}

final class RomSorter {
    private let supportedExtensions = Set(["zip", "nds", "srl"])
    private let defaultDiscardFolderName = "discarded_non_us"
    private let usRegionMarkers = Set([
        "u",
        "us",
        "usa",
        "united states",
        "united states of america",
    ])
    private let nonUSRegionMarkers = Set([
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
    ])
    private let destinationCodes = [
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
    ]

    func run(options: SortOptions) throws -> SortResult {
        let roms = try findROMs(in: options.sourceURL, recursive: options.recursive)
        let actions = planActions(
            roms: roms,
            sourceURL: options.sourceURL,
            discardURL: options.discardURL,
            keepUnknown: options.keepUnknown,
            deleteNonUS: options.deleteNonUS
        )

        for action in actions {
            try apply(action: action, dryRun: options.dryRun)
        }

        return SortResult(actions: actions)
    }

    func findROMs(in sourceURL: URL, recursive: Bool) throws -> [URL] {
        let fileManager = FileManager.default
        let keys: [URLResourceKey] = [.isRegularFileKey, .isDirectoryKey]
        let isDirectory = (try? sourceURL.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true

        if isDirectory {
            let candidates: [URL]
            if recursive {
                let enumerator = fileManager.enumerator(
                    at: sourceURL,
                    includingPropertiesForKeys: keys,
                    options: [.skipsHiddenFiles, .skipsPackageDescendants]
                )
                candidates = (enumerator?.compactMap { $0 as? URL }) ?? []
            } else {
                candidates = try fileManager.contentsOfDirectory(
                    at: sourceURL,
                    includingPropertiesForKeys: keys,
                    options: [.skipsHiddenFiles]
                )
            }

            return candidates
                .filter { isSupportedROMURL($0, under: sourceURL) }
                .sorted { $0.path.localizedStandardCompare($1.path) == .orderedAscending }
        }

        return isSupportedROMURL(sourceURL, under: sourceURL.deletingLastPathComponent()) ? [sourceURL] : []
    }

    private func isSupportedROMURL(_ url: URL, under sourceURL: URL) -> Bool {
        guard (try? url.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true else {
            return false
        }
        let relativePath = url.path.replacingOccurrences(of: sourceURL.path, with: "")
        if relativePath.split(separator: "/").contains(Substring(defaultDiscardFolderName)) {
            return false
        }
        return supportedExtensions.contains(url.pathExtension.lowercased())
    }

    private func planActions(
        roms: [URL],
        sourceURL: URL,
        discardURL: URL?,
        keepUnknown: Bool,
        deleteNonUS: Bool
    ) -> [PlannedAction] {
        var actions: [PlannedAction] = []
        var reservedDestinations = Set<String>()

        for rom in roms {
            let classification = classify(rom)
            if classification.decision == .us {
                actions.append(PlannedAction(url: rom, classification: classification, kind: .keep, destination: nil))
                continue
            }

            if classification.decision == .unknown && keepUnknown {
                actions.append(PlannedAction(url: rom, classification: classification, kind: .keep, destination: nil))
                continue
            }

            if deleteNonUS {
                actions.append(PlannedAction(url: rom, classification: classification, kind: .delete, destination: nil))
            } else {
                let destination = uniqueDestination(
                    for: rom,
                    sourceURL: sourceURL,
                    discardURL: discardURL,
                    reservedDestinations: &reservedDestinations
                )
                actions.append(PlannedAction(url: rom, classification: classification, kind: .move, destination: destination))
            }
        }

        return actions
    }

    private func classify(_ url: URL) -> Classification {
        let filenameResult = classifyFromFilename(url)
        if filenameResult.decision != .unknown {
            return filenameResult
        }

        switch url.pathExtension.lowercased() {
        case "nds", "srl":
            return classifyLooseROM(url)
        case "zip":
            return classifyZip(url)
        default:
            return Classification(decision: .unknown, reason: "unsupported file type")
        }
    }

    private func classifyFromFilename(_ url: URL) -> Classification {
        let name = url.deletingPathExtension().lastPathComponent
        let markers = bracketedMarkers(in: name)

        for marker in markers where usRegionMarkers.contains(marker) {
            return Classification(decision: .us, reason: "filename marker '\(marker)'")
        }
        for marker in markers where nonUSRegionMarkers.contains(marker) {
            return Classification(decision: .nonUS, reason: "filename marker '\(marker)'")
        }

        let normalizedName = normalize(
            name
                .replacingOccurrences(of: "_", with: " ")
                .replacingOccurrences(of: "-", with: " ")
        )

        for marker in usRegionMarkers.sorted(by: { $0.count > $1.count }) {
            if containsWord(marker, in: normalizedName) {
                return Classification(decision: .us, reason: "filename contains '\(marker)'")
            }
        }

        for marker in nonUSRegionMarkers.sorted(by: { $0.count > $1.count }) where marker.count > 1 {
            if containsWord(marker, in: normalizedName) {
                return Classification(decision: .nonUS, reason: "filename contains '\(marker)'")
            }
        }

        return Classification(decision: .unknown, reason: "no filename region marker")
    }

    private func bracketedMarkers(in name: String) -> [String] {
        let pattern = #"[\(\[\{]([^\)\]\}]+)[\)\]\}]"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else {
            return []
        }
        let range = NSRange(name.startIndex..<name.endIndex, in: name)
        return regex.matches(in: name, range: range).flatMap { match -> [String] in
            guard let markerRange = Range(match.range(at: 1), in: name) else {
                return []
            }
            return splitRegionMarkers(String(name[markerRange]))
        }
    }

    private func splitRegionMarkers(_ value: String) -> [String] {
        value
            .components(separatedBy: CharacterSet(charactersIn: ",;/+&|"))
            .map(normalize)
            .filter { !$0.isEmpty }
    }

    private func normalize(_ value: String) -> String {
        value
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
    }

    private func containsWord(_ marker: String, in value: String) -> Bool {
        let pattern = #"\b"# + NSRegularExpression.escapedPattern(for: marker) + #"\b"#
        return value.range(of: pattern, options: .regularExpression) != nil
    }

    private func classifyLooseROM(_ url: URL) -> Classification {
        do {
            let handle = try FileHandle(forReadingFrom: url)
            defer { try? handle.close() }
            let header = try handle.read(upToCount: 16) ?? Data()
            return classifyHeader(header)
        } catch {
            return Classification(decision: .unknown, reason: "could not read ROM header: \(error.localizedDescription)")
        }
    }

    private func classifyZip(_ url: URL) -> Classification {
        do {
            let members = try zipMembers(in: url)
            guard let romMember = members.first(where: { member in
                let ext = URL(fileURLWithPath: member).pathExtension.lowercased()
                return ext == "nds" || ext == "srl"
            }) else {
                return Classification(decision: .unknown, reason: "zip does not contain an NDS ROM")
            }

            let header = try zipMemberHeader(archiveURL: url, member: romMember)
            let result = classifyHeader(header)
            return Classification(decision: result.decision, reason: "zip member '\(romMember)' \(result.reason)")
        } catch {
            return Classification(decision: .unknown, reason: "could not inspect zip: \(error.localizedDescription)")
        }
    }

    private func classifyHeader(_ header: Data) -> Classification {
        guard header.count >= 16 else {
            return Classification(decision: .unknown, reason: "ROM header is too short")
        }

        let gameCodeData = header.subdata(in: 12..<16)
        guard let gameCode = String(data: gameCodeData, encoding: .ascii) else {
            return Classification(decision: .unknown, reason: "ROM header game code is not ASCII")
        }

        guard gameCode.range(of: #"^[A-Z0-9]{4}$"#, options: .regularExpression) != nil else {
            return Classification(decision: .unknown, reason: "ROM header game code is not recognized")
        }

        let destinationCode = String(gameCode.suffix(1))
        if destinationCode == "E" {
            return Classification(decision: .us, reason: "header destination code E (United States)")
        }
        if let destination = destinationCodes[destinationCode] {
            return Classification(
                decision: .nonUS,
                reason: "header destination code \(destinationCode) (\(destination))"
            )
        }

        return Classification(
            decision: .unknown,
            reason: "header destination code \(destinationCode) is not recognized"
        )
    }

    private func zipMembers(in archiveURL: URL) throws -> [String] {
        let output = try runProcess("/usr/bin/unzip", arguments: ["-Z1", archiveURL.path])
        guard output.status == 0 else {
            throw SorterError.shellFailed(output.stderr)
        }
        let stdout = String(data: output.stdoutData, encoding: .utf8) ?? ""
        return stdout
            .split(whereSeparator: \.isNewline)
            .map(String.init)
    }

    private func zipMemberHeader(archiveURL: URL, member: String) throws -> Data {
        let command = "/usr/bin/unzip -p \(shellQuote(archiveURL.path)) \(shellQuote(member)) | /usr/bin/head -c 16"
        let output = try runProcess("/bin/sh", arguments: ["-c", command])
        guard output.status == 0 else {
            throw SorterError.shellFailed(output.stderr)
        }
        return output.stdoutData
    }

    private func shellQuote(_ value: String) -> String {
        "'\(value.replacingOccurrences(of: "'", with: "'\\''"))'"
    }

    private func runProcess(_ executable: String, arguments: [String]) throws -> (stdoutData: Data, stderr: String, status: Int32) {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments

        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr

        try process.run()
        let stdoutData = stdout.fileHandleForReading.readDataToEndOfFile()
        let stderrData = stderr.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()

        return (
            stdoutData,
            String(data: stderrData, encoding: .utf8) ?? "",
            process.terminationStatus
        )
    }

    private func uniqueDestination(
        for rom: URL,
        sourceURL: URL,
        discardURL: URL?,
        reservedDestinations: inout Set<String>
    ) -> URL {
        let baseURL = discardURL ?? sourceURL.appendingPathComponent(defaultDiscardFolderName, isDirectory: true)
        let preferred = baseURL.appendingPathComponent(rom.lastPathComponent)
        let fileManager = FileManager.default

        if !fileManager.fileExists(atPath: preferred.path) && !reservedDestinations.contains(preferred.path) {
            reservedDestinations.insert(preferred.path)
            return preferred
        }

        let name = rom.deletingPathExtension().lastPathComponent
        let ext = rom.pathExtension
        var counter = 1
        while true {
            let candidateName = ext.isEmpty ? "\(name) (\(counter))" : "\(name) (\(counter)).\(ext)"
            let candidate = baseURL.appendingPathComponent(candidateName)
            if !fileManager.fileExists(atPath: candidate.path) && !reservedDestinations.contains(candidate.path) {
                reservedDestinations.insert(candidate.path)
                return candidate
            }
            counter += 1
        }
    }

    private func apply(action: PlannedAction, dryRun: Bool) throws {
        guard !dryRun else {
            return
        }

        let fileManager = FileManager.default
        switch action.kind {
        case .keep:
            return
        case .delete:
            try fileManager.removeItem(at: action.url)
        case .move:
            guard let destination = action.destination else {
                throw SorterError.missingDestination(action.url)
            }
            try fileManager.createDirectory(
                at: destination.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            try fileManager.moveItem(at: action.url, to: destination)
        }
    }
}
