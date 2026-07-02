import AppKit
import SwiftUI

/// A transparent, click-through window that sits above all other content.
class GhostCursorOverlayWindow: NSWindow {
    
    init(contentRect: NSRect) {
        super.init(
            contentRect: contentRect,
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        
        self.level = .screenSaver // High enough to cover full-screen apps and menubar
        self.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle, .fullScreenAuxiliary]
        self.backgroundColor = .clear
        self.isOpaque = false
        self.hasShadow = false
        self.ignoresMouseEvents = true // Important: click-through!
        self.hidesOnDeactivate = false
    }
    
    override var canBecomeKey: Bool {
        return false
    }
    
    override var canBecomeMain: Bool {
        return false
    }
}

/// Controller to manage the Ghost Cursor overlay window
class GhostCursorOverlayController: ObservableObject {
    private var window: GhostCursorOverlayWindow?
    private var hostingView: NSHostingView<GhostCursorRingView>?
    
    @Published var currentPosition: CGPoint = .zero
    @Published var currentAction: GhostCursorAction = .none
    
    func showOverlay() {
        guard window == nil else { return }
        
        guard let screen = NSScreen.main else { return }
        
        let overlayWindow = GhostCursorOverlayWindow(contentRect: screen.frame)
        
        // We pass bindings to our published properties
        let ringView = GhostCursorRingView(
            currentPosition: Binding(
                get: { self.currentPosition },
                set: { self.currentPosition = $0 }
            ),
            currentAction: Binding(
                get: { self.currentAction },
                set: { self.currentAction = $0 }
            )
        )
        
        let hostView = NSHostingView(rootView: ringView)
        hostView.frame = overlayWindow.contentView!.bounds
        hostView.autoresizingMask = [.width, .height]
        
        overlayWindow.contentView?.addSubview(hostView)
        
        overlayWindow.makeKeyAndOrderFront(nil)
        self.window = overlayWindow
        self.hostingView = hostView
        
        // Position it offscreen or center initially
        self.currentPosition = CGPoint(x: screen.frame.midX, y: screen.frame.midY)
    }
    
    func hideOverlay() {
        window?.orderOut(nil)
        window = nil
        hostingView = nil
    }
    
    func moveTo(point: CGPoint, action: GhostCursorAction = .none) {
        // macOS coordinate system mapping: SwiftUI uses top-left origin for .position
        // NSScreen uses bottom-left origin.
        // ScreenRect from VSLM uses top-left origin.
        // We assume `point` is in top-left coordinates because that's what GhostCursorRingView uses.
        self.currentPosition = point
        self.currentAction = action
    }
}
