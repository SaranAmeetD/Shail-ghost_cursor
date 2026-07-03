import Foundation
import ApplicationServices
import CoreGraphics
import Cocoa

/// Controller for executing accessibility actions (click, type, etc.)
class AXController {
    
    /// Click at specified coordinates using CGEvent
    static func click(x: Int, y: Int) -> Bool {
        let point = CGPoint(x: CGFloat(x), y: CGFloat(y))
        
        // Create mouse down event
        guard let mouseDown = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: point, mouseButton: .left) else {
            return false
        }
        
        // Create mouse up event
        guard let mouseUp = CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: point, mouseButton: .left) else {
            return false
        }
        
        // Post events
        mouseDown.post(tap: .cghidEventTap)
        mouseUp.post(tap: .cghidEventTap)
        
        return true
    }
    
    /// Scroll at specified coordinates using CGEvent
    static func scroll(x: Int, y: Int, deltaX: Int, deltaY: Int) -> Bool {
        let point = CGPoint(x: CGFloat(x), y: CGFloat(y))
        
        // Move mouse to coordinate first
        guard let mouseMove = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: point, mouseButton: .left) else {
            return false
        }
        mouseMove.post(tap: .cghidEventTap)
        
        // Post scroll event
        guard let scrollEvent = CGEvent(scrollWheelEvent2Source: nil, units: .pixel, wheelCount: 2, wheel1: Int32(deltaY), wheel2: Int32(deltaX), wheel3: 0) else {
            return false
        }
        scrollEvent.post(tap: .cghidEventTap)
        
        return true
    }
    
    /// Type text using CGEvent
    static func typeText(_ text: String) -> Bool {
        // Create keyboard events for each character
        for char in text {
            let keyCode = getKeyCode(for: char)
            let keyDown = CGEvent(keyboardEventSource: nil, virtualKey: keyCode, keyDown: true)
            let keyUp = CGEvent(keyboardEventSource: nil, virtualKey: keyCode, keyDown: false)
            
            keyDown?.post(tap: .cghidEventTap)
            keyUp?.post(tap: .cghidEventTap)
            
            // Small delay between keystrokes for reliability
            usleep(10000) // 10ms
        }
        
        return true
    }
    
    /// Press a specific key
    static func pressKey(_ key: String) -> Bool {
        let keyCode = getKeyCode(for: key)
        guard keyCode != 0 else {
            return false
        }
        
        let keyDown = CGEvent(keyboardEventSource: nil, virtualKey: keyCode, keyDown: true)
        let keyUp = CGEvent(keyboardEventSource: nil, virtualKey: keyCode, keyDown: false)
        
        keyDown?.post(tap: .cghidEventTap)
        keyUp?.post(tap: .cghidEventTap)
        
        return true
    }
    
    /// Get information about the active window
    static func getActiveWindowInfo() -> [String: Any] {
        var info: [String: Any] = [:]
        
        // Get frontmost application
        guard let frontApp = NSWorkspace.shared.frontmostApplication else {
            return info
        }
        
        info["app_name"] = frontApp.localizedName ?? "Unknown"
        info["bundle_id"] = frontApp.bundleIdentifier ?? ""
        info["pid"] = frontApp.processIdentifier
        
        // Get active window
        let pid = frontApp.processIdentifier
        let appElement = AXUIElementCreateApplication(pid)
        
        var windowList: CFTypeRef?
        let result = AXUIElementCopyAttributeValue(
            appElement,
            kAXWindowsAttribute as CFString,
            &windowList
        )
        
        if result == .success, let windows = windowList as? [AXUIElement], !windows.isEmpty {
            let mainWindow = windows[0] // Usually the first window is the main one
            
            // Get window title
            if let title = getAttributeValue(mainWindow, kAXTitleAttribute as CFString) as? String {
                info["window_title"] = title
            }
            
            // Get window position and size
            if let positionRef = getAttributeValue(mainWindow, kAXPositionAttribute as CFString) {
                let position = unsafeBitCast(positionRef, to: AXValue.self)
                var point = CGPoint.zero
                if AXValueGetValue(position, .cgPoint, &point) {
                    info["window_x"] = Int(point.x)
                    info["window_y"] = Int(point.y)
                }
            }
            
            if let sizeRef = getAttributeValue(mainWindow, kAXSizeAttribute as CFString) {
                let size = unsafeBitCast(sizeRef, to: AXValue.self)
                var cgSize = CGSize.zero
                if AXValueGetValue(size, .cgSize, &cgSize) {
                    info["window_width"] = Int(cgSize.width)
                    info["window_height"] = Int(cgSize.height)
                }
            }
        }
        
        return info
    }
    
    /// Get AXUIElement at specified coordinates
    static func getElementAt(x: Int, y: Int) -> [String: Any]? {
        let point = CGPoint(x: CGFloat(x), y: CGFloat(y))
        
        // Get system-wide element
        let systemWide = AXUIElementCreateSystemWide()
        
        // Get element at point
        var elementRef: CFTypeRef?
        let result = AXUIElementCopyElementAtPosition(systemWide, Float(point.x), Float(point.y), &elementRef)
        
        guard result == .success, let element = elementRef else {
            return nil
        }
        
        let elementUI = unsafeBitCast(element, to: AXUIElement.self)
        
        // Get element info
        var pid: pid_t = 0
        AXUIElementGetPid(elementUI, &pid)
        
        var info: [String: Any] = [
            "x": x,
            "y": y,
            "pid": pid
        ]
        
        // Get app name
        if let app = NSRunningApplication(processIdentifier: pid) {
            info["app_name"] = app.localizedName ?? "Unknown"
            info["bundle_id"] = app.bundleIdentifier ?? ""
        }
        
        // Get role
        if let role = getAttributeValue(elementUI, kAXRoleAttribute as CFString) as? String {
            info["role"] = role
        }
        
        // Get title
        if let title = getAttributeValue(elementUI, kAXTitleAttribute as CFString) as? String {
            info["title"] = title
        }
        
        // Get value/text
        if let value = getAttributeValue(elementUI, kAXValueAttribute as CFString) {
            if let stringValue = value as? String {
                info["text"] = stringValue
            }
        }
        
        // Get position and size
        if let positionRef = getAttributeValue(elementUI, kAXPositionAttribute as CFString) {
            let position = unsafeBitCast(positionRef, to: AXValue.self)
            var pos = CGPoint.zero
            if AXValueGetValue(position, .cgPoint, &pos) {
                info["element_x"] = Int(pos.x)
                info["element_y"] = Int(pos.y)
            }
        }
        
        if let sizeRef = getAttributeValue(elementUI, kAXSizeAttribute as CFString) {
            let size = unsafeBitCast(sizeRef, to: AXValue.self)
            var cgSize = CGSize.zero
            if AXValueGetValue(size, .cgSize, &cgSize) {
                info["element_width"] = Int(cgSize.width)
                info["element_height"] = Int(cgSize.height)
            }
        }
        
        return info
    }
    
    // MARK: - Sprint 1.3: Window Element Tree
    
    /// Supported AX roles for the Sprint 1.3 element budget.
    private static let allowedRoles: Set<String> = [
        "AXButton", "AXTextField", "AXTextArea", "AXLink", "AXCheckBox",
        "AXRadioButton", "AXComboBox", "AXPopUpButton", "AXMenuItem",
        "AXMenuBar", "AXTabGroup", "AXTab", "AXStaticText",
        "AXSearchField", "AXToolbar"
    ]
    
    /// Interactive roles (higher priority in budget selection).
    private static let interactiveRoles: Set<String> = [
        "AXButton", "AXTextField", "AXTextArea", "AXLink", "AXCheckBox",
        "AXRadioButton", "AXComboBox", "AXPopUpButton", "AXMenuItem",
        "AXSearchField"
    ]
    
    /// Returns up to `deliverLimit` filtered, priority-sorted elements from the
    /// frontmost application's main window using iterative BFS.
    ///
    /// - Parameters:
    ///   - maxDepth:     Maximum BFS depth from the window root (default: 8).
    ///   - maxNodes:     Maximum nodes visited before stopping traversal (default: 150).
    ///   - deliverLimit: Maximum nodes delivered to the caller after filtering (default: 40).
    /// - Returns: Array of element info dictionaries using the canonical ScreenRect format.
    static func getWindowElements(
        maxDepth: Int = 8,
        maxNodes: Int = 150,
        deliverLimit: Int = 40
    ) -> [[String: Any]] {
        
        guard let frontApp = NSWorkspace.shared.frontmostApplication else {
            return []
        }
        
        let pid = frontApp.processIdentifier
        let appElement = AXUIElementCreateApplication(pid)
        
        // Obtain main window
        var windowListRef: CFTypeRef?
        guard AXUIElementCopyAttributeValue(
            appElement, kAXWindowsAttribute as CFString, &windowListRef
        ) == .success,
              let windows = windowListRef as? [AXUIElement],
              !windows.isEmpty else {
            return []
        }
        let rootWindow = windows[0]
        
        // Determine screen centre for proximity scoring
        let screenSize = NSScreen.main?.frame.size ?? CGSize(width: 1440, height: 900)
        let screenCX = screenSize.width / 2
        let screenCY = screenSize.height / 2
        
        // Identify the currently focused element for priority boosting
        var focusedRef: CFTypeRef?
        let systemWide = AXUIElementCreateSystemWide()
        let focusedElement: AXUIElement? = {
            guard AXUIElementCopyAttributeValue(
                systemWide, kAXFocusedUIElementAttribute as CFString, &focusedRef
            ) == .success, let ref = focusedRef else { return nil }
            return unsafeBitCast(ref, to: AXUIElement.self)
        }()
        
        // BFS state — plain tuples avoid local-struct visibility issues with helpers
        var queue: [(element: AXUIElement, depth: Int)] = [(element: rootWindow, depth: 0)]
        var visited = Set<String>()       // CFHash-based visit IDs assigned at traversal time
        var collected: [[String: Any]] = []
        var nodesVisited = 0
        
        while !queue.isEmpty && nodesVisited < maxNodes {
            let entry = queue.removeFirst()
            let element = entry.element
            let depth = entry.depth
            nodesVisited += 1
            
            // Assign a stable visit ID using object pointer as proxy
            // (AXUIElement has no built-in UUID; pointer is stable for this traversal)
            let elementPtr = String(UInt(bitPattern: CFHash(element)))
            guard !visited.contains(elementPtr) else { continue }
            visited.insert(elementPtr)
            
            // --- Filtering ---
            // Role filter
            let role = getAttributeValue(element, kAXRoleAttribute as CFString) as? String ?? ""
            guard allowedRoles.contains(role) else {
                // Still enqueue children if within depth limit
                if depth < maxDepth {
                    enqueueChildren(of: element, depth: depth, queue: &queue)
                }
                continue
            }
            
            // Hidden filter
            if let hidden = getAttributeValue(element, kAXHiddenAttribute as CFString) as? Bool, hidden {
                continue
            }
            
            // Enabled filter
            if let enabled = getAttributeValue(element, kAXEnabledAttribute as CFString) as? Bool, !enabled {
                continue
            }
            
            // Label filter: at least one of title/value/description must be non-empty
            let title = getAttributeValue(element, kAXTitleAttribute as CFString) as? String ?? ""
            let description = getAttributeValue(element, kAXDescriptionAttribute as CFString) as? String ?? ""
            let value: String = {
                if let v = getAttributeValue(element, kAXValueAttribute as CFString) as? String { return v }
                return ""
            }()
            guard !title.isEmpty || !description.isEmpty || !value.isEmpty else {
                if depth < maxDepth { enqueueChildren(of: element, depth: depth, queue: &queue) }
                continue
            }
            
            // Size filter: skip invisible elements
            var elemX = 0, elemY = 0, elemW = 0, elemH = 0
            if let posRef = getAttributeValue(element, kAXPositionAttribute as CFString) {
                let pos = unsafeBitCast(posRef, to: AXValue.self)
                var pt = CGPoint.zero
                if AXValueGetValue(pos, .cgPoint, &pt) {
                    elemX = Int(pt.x); elemY = Int(pt.y)
                }
            }
            if let szRef = getAttributeValue(element, kAXSizeAttribute as CFString) {
                let sz = unsafeBitCast(szRef, to: AXValue.self)
                var cgsz = CGSize.zero
                if AXValueGetValue(sz, .cgSize, &cgsz) {
                    elemW = Int(cgsz.width); elemH = Int(cgsz.height)
                }
            }
            guard elemW > 0 && elemH > 0 else {
                if depth < maxDepth { enqueueChildren(of: element, depth: depth, queue: &queue) }
                continue
            }
            
            // Priority scoring (lower score = higher priority)
            var priorityScore = 0
            // 1. Focused element gets score 0 (highest)
            if let focused = focusedElement, CFEqual(element, focused) {
                priorityScore = 0
            } else {
                // 2. Interactive > static
                priorityScore = interactiveRoles.contains(role) ? 10 : 50
                // 3. Proximity to screen centre (Euclidean distance, scaled)
                let cx = Double(elemX + elemW / 2)
                let cy = Double(elemY + elemH / 2)
                let dist = sqrt(pow(cx - Double(screenCX), 2) + pow(cy - Double(screenCY), 2))
                priorityScore += Int(dist / 100)
            }
            
            var info: [String: Any] = [
                "element_id":   elementPtr,
                "role":         role,
                "title":        String(title.prefix(120)),
                "value":        String(value.prefix(120)),
                "description":  String(description.prefix(120)),
                "x":            elemX,
                "y":            elemY,
                "width":        elemW,
                "height":       elemH,
                "_priority":    priorityScore   // stripped before response
            ]
            collected.append(info)
            
            // Enqueue children
            if depth < maxDepth {
                enqueueChildren(of: element, depth: depth, queue: &queue)
            }
        }
        
        // Sort by priority score, deliver top `deliverLimit`
        collected.sort { ($0["_priority"] as? Int ?? 999) < ($1["_priority"] as? Int ?? 999) }
        let delivered = Array(collected.prefix(deliverLimit))
        
        // Strip internal priority key before returning
        return delivered.map { elem in
            var e = elem
            e.removeValue(forKey: "_priority")
            return e
        }
    }
    
    /// Enqueues direct AX children of `element` into the BFS queue at `depth + 1`.
    private static func enqueueChildren(
        of element: AXUIElement,
        depth: Int,
        queue: inout [(element: AXUIElement, depth: Int)]
    ) {
        var childrenRef: CFTypeRef?
        guard AXUIElementCopyAttributeValue(
            element, kAXChildrenAttribute as CFString, &childrenRef
        ) == .success,
              let children = childrenRef as? [AXUIElement] else { return }
        for child in children {
            queue.append((element: child, depth: depth + 1))
        }
    }
    
    // MARK: - Helper Methods
    
    private static func getAttributeValue(_ element: AXUIElement, _ attribute: CFString) -> CFTypeRef? {
        var value: CFTypeRef?
        let result = AXUIElementCopyAttributeValue(element, attribute as CFString, &value)
        return result == .success ? value : nil
    }
    
    private static func getKeyCode(for character: Character) -> CGKeyCode {
        // Map common characters to key codes
        // This is a simplified mapping - for production, use a more complete mapping
        let charString = String(character).lowercased()
        
        switch charString {
        case "a": return 0
        case "b": return 11
        case "c": return 8
        case "d": return 2
        case "e": return 14
        case "f": return 3
        case "g": return 5
        case "h": return 4
        case "i": return 34
        case "j": return 38
        case "k": return 40
        case "l": return 37
        case "m": return 46
        case "n": return 45
        case "o": return 31
        case "p": return 35
        case "q": return 12
        case "r": return 15
        case "s": return 1
        case "t": return 17
        case "u": return 32
        case "v": return 9
        case "w": return 13
        case "x": return 7
        case "y": return 16
        case "z": return 6
        case "0": return 29
        case "1": return 18
        case "2": return 19
        case "3": return 20
        case "4": return 21
        case "5": return 23
        case "6": return 22
        case "7": return 26
        case "8": return 28
        case "9": return 25
        case " ": return 49 // Space
        case "\n", "\r": return 36 // Return/Enter
        case "\t": return 48 // Tab
        default:
            // For special characters, try to use Unicode
            // In production, use a proper key code mapping library
            return 0
        }
    }
    
    private static func getKeyCode(for key: String) -> CGKeyCode {
        // Map common key names to key codes
        switch key.lowercased() {
        case "enter", "return": return 36
        case "tab": return 48
        case "space": return 49
        case "delete", "backspace": return 51
        case "escape", "esc": return 53
        case "command", "cmd": return 55
        case "shift": return 56
        case "option", "alt": return 58
        case "control", "ctrl": return 59
        case "up": return 126
        case "down": return 125
        case "left": return 123
        case "right": return 124
        default:
            // Try to get key code for single character
            if key.count == 1 {
                return getKeyCode(for: Character(key))
            }
            return 0
        }
    }
}

