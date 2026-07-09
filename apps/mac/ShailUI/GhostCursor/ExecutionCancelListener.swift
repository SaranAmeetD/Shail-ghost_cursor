import AppKit
import Foundation

class ExecutionCancelListener {
    private var globalMonitor: Any?
    private var localMonitor: Any?
    private let onCancel: () -> Void

    init(onCancel: @escaping () -> Void) {
        self.onCancel = onCancel
    }

    func startMonitoring() {
        globalMonitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { [weak self] event in
            if self?.isCancelHotkey(event) == true {
                DispatchQueue.main.async { self?.onCancel() }
            }
        }

        localMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            if self?.isCancelHotkey(event) == true {
                DispatchQueue.main.async { self?.onCancel() }
                return nil
            }
            return event
        }
    }

    func stopMonitoring() {
        if let monitor = globalMonitor { NSEvent.removeMonitor(monitor) }
        if let monitor = localMonitor  { NSEvent.removeMonitor(monitor) }
        globalMonitor = nil
        localMonitor  = nil
    }

    private func isCancelHotkey(_ event: NSEvent) -> Bool {
        // Escape is keyCode 53
        if event.keyCode == 53 { return true }
        // Cmd + . (period keyCode is 47)
        let required: NSEvent.ModifierFlags = [.command]
        let modifiers = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        if modifiers == required && event.keyCode == 47 {
            return true
        }
        return false
    }

    deinit {
        stopMonitoring()
    }
}
