import Foundation
import CoreGraphics
import SwiftUI

/// An internal test harness that simulates Ghost Cursor executions
/// without requiring the Python execution engine.
class GhostCursorTestHarness {
    private let controller: GhostCursorOverlayController
    private var isTesting = false
    
    init(controller: GhostCursorOverlayController) {
        self.controller = controller
    }
    
    func runTestSequence() {
        guard !isTesting else { return }
        isTesting = true
        
        controller.showOverlay()
        
        let center = CGPoint(x: 500, y: 300)
        controller.moveTo(point: center, action: .none)
        
        // Step 1: Move to point 1 and hover
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            let target1 = CGPoint(x: 800, y: 400)
            self.controller.moveTo(point: target1, action: .hover)
            
            // Step 2: Click
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                self.controller.moveTo(point: target1, action: .click)
                
                // Step 3: Move to point 2 and hover
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                    let target2 = CGPoint(x: 200, y: 150)
                    self.controller.moveTo(point: target2, action: .hover)
                    
                    // Step 4: Type
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                        self.controller.moveTo(point: target2, action: .type)
                        
                        // Finish
                        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                            self.controller.hideOverlay()
                            self.isTesting = false
                        }
                    }
                }
            }
        }
    }
}
