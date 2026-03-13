#!/usr/bin/env swift

import AppKit
import ApplicationServices
import Foundation

struct Config {
    var depth: Int = 2
    var allWindows = false
}

func parseArgs() -> Config {
    var config = Config()
    var iterator = CommandLine.arguments.dropFirst().makeIterator()

    while let arg = iterator.next() {
        switch arg {
        case "--depth":
            if let raw = iterator.next(), let value = Int(raw), value >= 0 {
                config.depth = value
            }
        case "--all-windows":
            config.allWindows = true
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

func dumpNode(_ element: AXUIElement, level: Int, depthLimit: Int) {
    let indent = String(repeating: "  ", count: level)
    let role = stringAttribute(element, kAXRoleAttribute as String) ?? "?"
    let subrole = stringAttribute(element, kAXSubroleAttribute as String) ?? ""
    let title = stringAttribute(element, kAXTitleAttribute as String) ?? ""
    let desc = stringAttribute(element, kAXDescriptionAttribute as String) ?? ""
    let value = stringAttribute(element, kAXValueAttribute as String) ?? ""

    var parts = [role]
    if !subrole.isEmpty { parts.append("subrole=\(subrole)") }
    if !title.isEmpty { parts.append("title=\(title)") }
    if !desc.isEmpty { parts.append("desc=\(desc)") }
    if !value.isEmpty, value != title { parts.append("value=\(value)") }
    print(indent + parts.joined(separator: " | "))

    guard level < depthLimit else { return }
    for child in childrenAttribute(element) {
        dumpNode(child, level: level + 1, depthLimit: depthLimit)
    }
}

let config = parseArgs()

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

let windowElements: [AXUIElement]
if config.allWindows {
    windowElements = (attributeValue(appElement, kAXWindowsAttribute as String) as? [AXUIElement]) ?? []
} else if let focused = elementAttribute(appElement, kAXFocusedWindowAttribute as String) {
    windowElements = [focused]
} else {
    windowElements = (attributeValue(appElement, kAXWindowsAttribute as String) as? [AXUIElement]) ?? []
}

guard !windowElements.isEmpty else {
    fputs("No accessible WeChat windows found.\n", stderr)
    exit(1)
}

for (index, window) in windowElements.enumerated() {
    let title = stringAttribute(window, kAXTitleAttribute as String) ?? "(untitled)"
    print("Window \(index + 1): \(title)")
    dumpNode(window, level: 0, depthLimit: config.depth)
}
