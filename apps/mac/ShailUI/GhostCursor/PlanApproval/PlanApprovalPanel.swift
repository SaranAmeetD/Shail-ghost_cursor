import AppKit
import SwiftUI

/// A floating panel used to present the Ghost Cursor Plan Approval UI securely above the workspace.
public class PlanApprovalPanel: NSPanel {
    
    public init(contentRect: NSRect) {
        super.init(
            contentRect: contentRect,
            styleMask: [.titled, .nonactivatingPanel, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        
        self.level = .floating // Stays above normal windows
        self.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        self.isMovableByWindowBackground = true
        self.titlebarAppearsTransparent = true
        self.titleVisibility = .hidden
        self.backgroundColor = .clear
        self.hasShadow = true
        self.isFloatingPanel = true
        self.hidesOnDeactivate = false
    }
    
    public override var canBecomeKey: Bool {
        return true
    }
    
    public override var canBecomeMain: Bool {
        return true
    }
}

/// Controller to manage the lifecycle of the Plan Approval Panel
public class PlanApprovalController {
    private var panel: PlanApprovalPanel?
    private var viewModel: PlanApprovalViewModel?
    
    public init() {}
    
    /// Presents the plan approval UI and waits for a user intent (approve/cancel).
    public func present(plan: GuidancePlan, onIntent: @escaping (PlanApprovalIntent) -> Void) {
        // If a panel is already presented, close it first.
        close()
        
        let vm = PlanApprovalViewModel(plan: plan)
        
        vm.onIntent = { [weak self] intent in
            // When an intent is emitted (either approve or cancel), close the panel
            self?.close()
            onIntent(intent)
        }
        
        self.viewModel = vm
        
        let view = PlanApprovalView(viewModel: vm)
        let hostingController = NSHostingController(rootView: view)
        
        let panel = PlanApprovalPanel(contentRect: NSRect(x: 0, y: 0, width: 400, height: 500))
        panel.contentViewController = hostingController
        panel.center()
        
        self.panel = panel
        
        // Make key and order front without activating the app, preventing focus stealing
        panel.makeKeyAndOrderFront(nil)
    }
    
    public func close() {
        panel?.orderOut(nil)
        panel = nil
        viewModel = nil
    }
}
