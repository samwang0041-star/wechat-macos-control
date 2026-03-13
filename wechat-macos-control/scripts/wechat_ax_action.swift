#!/usr/bin/env swift

import AppKit
import ApplicationServices
import CoreGraphics
import Foundation

func attributeValue(_ element: AXUIElement, _ attribute: String) -> AnyObject? {
    var value: CFTypeRef?
    let result = AXUIElementCopyAttributeValue(element, attribute as CFString, &value)
    guard result == .success else { return nil }
    return value
}

func stringAttribute(_ element: AXUIElement, _ attribute: String) -> String? {
    attributeValue(element, attribute) as? String
}

func nonEmptyText(_ element: AXUIElement) -> String? {
    let candidates = [
        stringAttribute(element, kAXTitleAttribute as String),
        stringAttribute(element, kAXValueAttribute as String),
        stringAttribute(element, kAXDescriptionAttribute as String),
    ]
    for candidate in candidates {
        if let value = candidate?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty {
            return value
        }
    }
    return nil
}

func elementAttribute(_ element: AXUIElement, _ attribute: String) -> AXUIElement? {
    guard let value = attributeValue(element, attribute) else { return nil }
    return unsafeBitCast(value, to: AXUIElement.self)
}

func childrenAttribute(_ element: AXUIElement) -> [AXUIElement] {
    (attributeValue(element, kAXChildrenAttribute as String) as? [AXUIElement]) ?? []
}

func pointAttribute(_ element: AXUIElement, _ attribute: String) -> CGPoint? {
    guard let value = attributeValue(element, attribute) else { return nil }
    let axValue = unsafeBitCast(value, to: AXValue.self)
    guard AXValueGetType(axValue) == .cgPoint else { return nil }
    var point = CGPoint.zero
    return AXValueGetValue(axValue, .cgPoint, &point) ? point : nil
}

func sizeAttribute(_ element: AXUIElement, _ attribute: String) -> CGSize? {
    guard let value = attributeValue(element, attribute) else { return nil }
    let axValue = unsafeBitCast(value, to: AXValue.self)
    guard AXValueGetType(axValue) == .cgSize else { return nil }
    var size = CGSize.zero
    return AXValueGetValue(axValue, .cgSize, &size) ? size : nil
}

func click(at point: CGPoint) -> Bool {
    guard let source = CGEventSource(stateID: .combinedSessionState) else { return false }
    let move = CGEvent(mouseEventSource: source, mouseType: .mouseMoved, mouseCursorPosition: point, mouseButton: .left)
    let down = CGEvent(mouseEventSource: source, mouseType: .leftMouseDown, mouseCursorPosition: point, mouseButton: .left)
    let up = CGEvent(mouseEventSource: source, mouseType: .leftMouseUp, mouseCursorPosition: point, mouseButton: .left)
    move?.post(tap: .cghidEventTap)
    down?.post(tap: .cghidEventTap)
    up?.post(tap: .cghidEventTap)
    usleep(120_000)
    return true
}

func clickCenter(of element: AXUIElement) -> Bool {
    guard let point = pointAttribute(element, kAXPositionAttribute as String),
          let size = sizeAttribute(element, kAXSizeAttribute as String) else {
        return false
    }

    let center = CGPoint(x: point.x + size.width / 2, y: point.y + size.height / 2)
    return click(at: center)
}

func findCandidates(_ root: AXUIElement, match: (AXUIElement) -> Bool) -> [AXUIElement] {
    var results: [AXUIElement] = []
    if match(root) {
        results.append(root)
    }
    for child in childrenAttribute(root) {
        results.append(contentsOf: findCandidates(child, match: match))
    }
    return results
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
    for window in candidates {
        if findList(window, title: "会话") != nil {
            return window
        }
    }
    return candidates.first
}

func composeCandidates(in window: AXUIElement) -> [AXUIElement] {
    findCandidates(window) { element in
        let role = stringAttribute(element, kAXRoleAttribute as String) ?? ""
        let title = stringAttribute(element, kAXTitleAttribute as String) ?? ""
        return role == kAXTextAreaRole && title != "搜索"
    }
}

func focusComposeArea(in window: AXUIElement) -> Bool {
    let candidates = composeCandidates(in: window)

    for candidate in candidates {
        // A real mouse click makes WeChat treat the compose area as the
        // first responder; AX-focused alone is not enough for send shortcuts.
        if clickCenter(of: candidate) {
            return true
        }

        let focused = AXUIElementSetAttributeValue(
            candidate,
            kAXFocusedAttribute as CFString,
            kCFBooleanTrue
        )
        if focused == .success {
            return true
        }

        let pressed = AXUIElementPerformAction(candidate, kAXPressAction as CFString)
        if pressed == .success {
            return true
        }
    }

    return false
}

func setComposeText(in window: AXUIElement, text: String) -> Bool {
    for candidate in composeCandidates(in: window) {
        _ = focusComposeArea(in: window)
        let result = AXUIElementSetAttributeValue(candidate, kAXValueAttribute as CFString, text as CFTypeRef)
        if result == .success {
            return true
        }
    }
    return false
}

func selectVisibleChat(in window: AXUIElement, named target: String) -> Bool {
    guard let list = findList(window, title: "会话") else { return false }
    let listPoint = pointAttribute(list, kAXPositionAttribute as String)
    let listSize = sizeAttribute(list, kAXSizeAttribute as String)

    let candidates = findCandidates(list) { element in
        let role = stringAttribute(element, kAXRoleAttribute as String) ?? ""
        guard role == kAXStaticTextRole, let text = nonEmptyText(element) else { return false }
        let firstLine = text
            .components(separatedBy: .newlines)
            .first?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return firstLine == target
    }

    for candidate in candidates {
        if let candidatePoint = pointAttribute(candidate, kAXPositionAttribute as String),
           let candidateSize = sizeAttribute(candidate, kAXSizeAttribute as String),
           let listPoint,
           let listSize {
            let rowPoint = CGPoint(
                x: listPoint.x + min(32, max(12, listSize.width * 0.15)),
                y: candidatePoint.y + candidateSize.height / 2
            )
            if click(at: rowPoint) {
                return true
            }
        }
        let pressed = AXUIElementPerformAction(candidate, kAXPressAction as CFString)
        if pressed == .success {
            usleep(150_000)
            return true
        }
        if clickCenter(of: candidate) {
            return true
        }
        if let parent = elementAttribute(candidate, kAXParentAttribute as String), clickCenter(of: parent) {
            return true
        }
    }

    return false
}

func postKey(_ key: CGKeyCode, down: Bool, flags: CGEventFlags, pid: pid_t) -> Bool {
    guard let source = CGEventSource(stateID: .combinedSessionState),
          let event = CGEvent(keyboardEventSource: source, virtualKey: key, keyDown: down) else {
        return false
    }
    event.flags = flags
    event.postToPid(pid)
    return true
}

func sendShortcut(to pid: pid_t, mode: String) -> Bool {
    switch mode {
    case "enter":
        guard postKey(36, down: true, flags: [], pid: pid) else { return false }
        usleep(60_000)
        return postKey(36, down: false, flags: [], pid: pid)
    case "cmd-enter":
        guard postKey(55, down: true, flags: .maskCommand, pid: pid) else { return false }
        usleep(80_000)
        guard postKey(36, down: true, flags: .maskCommand, pid: pid) else { return false }
        usleep(60_000)
        guard postKey(36, down: false, flags: .maskCommand, pid: pid) else { return false }
        usleep(60_000)
        return postKey(55, down: false, flags: [], pid: pid)
    case "ctrl-enter":
        guard postKey(59, down: true, flags: .maskControl, pid: pid) else { return false }
        usleep(80_000)
        guard postKey(36, down: true, flags: .maskControl, pid: pid) else { return false }
        usleep(60_000)
        guard postKey(36, down: false, flags: .maskControl, pid: pid) else { return false }
        usleep(60_000)
        return postKey(59, down: false, flags: [], pid: pid)
    default:
        return false
    }
}

guard CommandLine.arguments.count >= 2 else {
    fputs("usage: wechat_ax_action.swift <focus-compose|set-compose-text|send-shortcut|select-visible-chat> [args]\n", stderr)
    exit(1)
}

let command = CommandLine.arguments[1]

guard AXIsProcessTrusted() else {
    fputs("Accessibility permission is required.\n", stderr)
    exit(1)
}

let apps = NSRunningApplication.runningApplications(withBundleIdentifier: "com.tencent.xinWeChat")
guard let app = apps.first else {
    fputs("WeChat is not running.\n", stderr)
    exit(1)
}

func activateAppForInteraction(_ app: NSRunningApplication) {
    _ = app.activate(options: [.activateIgnoringOtherApps])
    usleep(550_000)
}

let appElement = AXUIElementCreateApplication(app.processIdentifier)

func activeChatWindow() -> AXUIElement {
    guard let window = preferredChatWindow(appElement) else {
        fputs("No accessible WeChat windows found.\n", stderr)
        exit(1)
    }
    return window
}

switch command {
case "focus-compose":
    activateAppForInteraction(app)
    let window = activeChatWindow()
    if !focusComposeArea(in: window) {
        fputs("Could not focus the WeChat compose area.\n", stderr)
        exit(1)
    }
case "set-compose-text":
    guard CommandLine.arguments.count >= 3 else {
        fputs("set-compose-text requires a text argument.\n", stderr)
        exit(1)
    }
    activateAppForInteraction(app)
    let window = activeChatWindow()
    let text = CommandLine.arguments[2]
    if !setComposeText(in: window, text: text) {
        fputs("Could not set the WeChat compose text.\n", stderr)
        exit(1)
    }
case "select-visible-chat":
    guard CommandLine.arguments.count >= 3 else {
        fputs("select-visible-chat requires a chat name.\n", stderr)
        exit(1)
    }
    activateAppForInteraction(app)
    let window = activeChatWindow()
    let target = CommandLine.arguments[2]
    if !selectVisibleChat(in: window, named: target) {
        fputs("Could not select the requested visible WeChat chat.\n", stderr)
        exit(1)
    }
case "send-shortcut":
    activateAppForInteraction(app)
    var mode = "enter"
    var iterator = CommandLine.arguments.dropFirst(2).makeIterator()
    while let arg = iterator.next() {
        if arg == "--mode", let value = iterator.next() {
            mode = value
        }
    }
    if !sendShortcut(to: app.processIdentifier, mode: mode) {
        fputs("Could not send the configured WeChat shortcut.\n", stderr)
        exit(1)
    }
default:
    fputs("Unknown command: \(command)\n", stderr)
    exit(1)
}
