#!/usr/bin/env swift

import AppKit
import ApplicationServices
import Foundation

struct Config {
    var command = ""
    var limit = 10
}

struct NodeText: Hashable {
    let role: String
    let text: String
}

func parseArgs() -> Config {
    var config = Config()
    var args = CommandLine.arguments.dropFirst()
    guard let command = args.first else { return config }
    config.command = command
    args = args.dropFirst()

    var iterator = args.makeIterator()
    while let arg = iterator.next() {
        switch arg {
        case "--limit":
            if let raw = iterator.next(), let value = Int(raw), value > 0 {
                config.limit = value
            }
        default:
            continue
        }
    }
    return config
}

func attributeValue(_ element: AXUIElement, _ attribute: String) -> AnyObject? {
    var value: CFTypeRef?
    let result = AXUIElementCopyAttributeValue(element, attribute as CFString, &value)
    guard result == .success else { return nil }
    return value
}

func stringAttribute(_ element: AXUIElement, _ attribute: String) -> String? {
    attributeValue(element, attribute) as? String
}

func elementAttribute(_ element: AXUIElement, _ attribute: String) -> AXUIElement? {
    guard let value = attributeValue(element, attribute) else { return nil }
    return unsafeBitCast(value, to: AXUIElement.self)
}

func childrenAttribute(_ element: AXUIElement) -> [AXUIElement] {
    (attributeValue(element, kAXChildrenAttribute as String) as? [AXUIElement]) ?? []
}

func sanitize(_ text: String) -> String {
    var output = text
    let patterns = [
        #"sk-proj-[A-Za-z0-9_\-]{12,}"#,
        #"sk-[A-Za-z0-9_\-]{12,}"#,
        #"Bearer\s+[A-Za-z0-9_\-\.=]{16,}"#
    ]

    for pattern in patterns {
        if let regex = try? NSRegularExpression(pattern: pattern) {
            let range = NSRange(output.startIndex..<output.endIndex, in: output)
            output = regex.stringByReplacingMatches(
                in: output,
                options: [],
                range: range,
                withTemplate: "[REDACTED]"
            )
        }
    }

    return output
}

func nonEmptyText(_ element: AXUIElement) -> String? {
    let candidates = [
        stringAttribute(element, kAXTitleAttribute as String),
        stringAttribute(element, kAXValueAttribute as String),
        stringAttribute(element, kAXDescriptionAttribute as String)
    ]
    for candidate in candidates {
        if let value = candidate?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty {
            return sanitize(value)
        }
    }
    return nil
}

func collectNodes(_ element: AXUIElement) -> [AXUIElement] {
    var result = [element]
    for child in childrenAttribute(element) {
        result.append(contentsOf: collectNodes(child))
    }
    return result
}

func findFirst(_ root: AXUIElement, match: (AXUIElement) -> Bool) -> AXUIElement? {
    if match(root) { return root }
    for child in childrenAttribute(root) {
        if let found = findFirst(child, match: match) {
            return found
        }
    }
    return nil
}

func findList(_ root: AXUIElement, title: String) -> AXUIElement? {
    findFirst(root) { element in
        stringAttribute(element, kAXRoleAttribute as String) == kAXListRole &&
        stringAttribute(element, kAXTitleAttribute as String) == title
    }
}

func composeCandidates(in window: AXUIElement) -> [AXUIElement] {
    collectNodes(window).filter { element in
        let role = stringAttribute(element, kAXRoleAttribute as String) ?? ""
        let title = stringAttribute(element, kAXTitleAttribute as String) ?? ""
        return role == kAXTextAreaRole && !title.isEmpty && title != "搜索"
    }
}

func windowScore(_ window: AXUIElement) -> Int {
    var score = 0
    if findList(window, title: "消息") != nil { score += 5 }
    if !composeCandidates(in: window).isEmpty { score += 4 }
    if findList(window, title: "会话") != nil { score += 3 }
    if let title = stringAttribute(window, kAXTitleAttribute as String), !title.isEmpty { score += 1 }
    return score
}

func windowCandidates(_ appElement: AXUIElement) -> [AXUIElement] {
    var windows: [AXUIElement] = []
    if let focused = elementAttribute(appElement, kAXFocusedWindowAttribute as String) {
        windows.append(focused)
    }
    let allWindows = (attributeValue(appElement, kAXWindowsAttribute as String) as? [AXUIElement]) ?? []
    for window in allWindows where !windows.contains(where: { CFEqual($0, window) }) {
        windows.append(window)
    }
    return windows
}

func preferredChatWindow(_ appElement: AXUIElement) -> AXUIElement? {
    let candidates = windowCandidates(appElement)
    return candidates.max { windowScore($0) < windowScore($1) } ?? candidates.first
}

func collectTexts(from list: AXUIElement) -> [NodeText] {
    collectNodes(list).compactMap { element -> NodeText? in
        guard let text = nonEmptyText(element) else { return nil }
        let role = stringAttribute(element, kAXRoleAttribute as String) ?? "Unknown"
        return NodeText(role: role, text: text)
    }
}

func dedupePreservingOrder(_ items: [String]) -> [String] {
    var seen = Set<String>()
    var result: [String] = []
    for item in items where !item.isEmpty && !seen.contains(item) {
        seen.insert(item)
        result.append(item)
    }
    return result
}

func toJSON(_ value: Any) {
    if JSONSerialization.isValidJSONObject(value),
       let data = try? JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted]),
       let string = String(data: data, encoding: .utf8) {
        print(string)
    } else if let string = value as? String {
        print(string)
    } else {
        print("null")
    }
}

let config = parseArgs()

guard !config.command.isEmpty else {
    fputs("usage: wechat_ax_query.swift <current-chat|compose-text|visible-chats|current-messages> [--limit N]\n", stderr)
    exit(1)
}

guard AXIsProcessTrusted() else {
    fputs("Accessibility permission is required.\n", stderr)
    exit(1)
}

let apps = NSRunningApplication.runningApplications(withBundleIdentifier: "com.tencent.xinWeChat")
guard let app = apps.first else {
    fputs("WeChat is not running.\n", stderr)
    exit(1)
}

let appElement = AXUIElementCreateApplication(app.processIdentifier)
guard let window = preferredChatWindow(appElement) else {
    fputs("No accessible WeChat windows found.\n", stderr)
    exit(1)
}

switch config.command {
case "current-chat":
    let chatTitle = composeCandidates(in: window).first.flatMap {
        stringAttribute($0, kAXTitleAttribute as String)
    } ?? findFirst(window) { element in
        let role = stringAttribute(element, kAXRoleAttribute as String) ?? ""
        let text = nonEmptyText(element) ?? ""
        return role == kAXStaticTextRole && !text.isEmpty && !text.contains("已置顶")
    }.flatMap(nonEmptyText) ?? ""
    toJSON(chatTitle)

case "compose-text":
    let composeText = composeCandidates(in: window).first.flatMap {
        stringAttribute($0, kAXValueAttribute as String)
    } ?? ""
    toJSON(sanitize(composeText))

case "visible-chats":
    guard let list = findList(window, title: "会话") else {
        fputs("Could not find the 会话 list.\n", stderr)
        exit(1)
    }
    let items = childrenAttribute(list)
        .compactMap(nonEmptyText)
        .filter { $0 != "会话" && !$0.contains("消息免打扰") }
    toJSON(Array(items.prefix(config.limit)))

case "current-messages":
    guard let list = findList(window, title: "消息") else {
        fputs("Could not find the 消息 list.\n", stderr)
        exit(1)
    }
    let items = childrenAttribute(list)
        .compactMap(nonEmptyText)
        .filter { !$0.isEmpty }
    let slice = Array(items.suffix(config.limit))
    toJSON(slice)

default:
    fputs("Unknown command: \(config.command)\n", stderr)
    exit(1)
}
