import Foundation
import CoreGraphics
import SwiftUI

/// An internal test harness that simulates Ghost Cursor executions
/// without requiring the Python execution engine.
class GhostCursorTestHarness {
    private let controller: GhostCursorOverlayController
    private let planApprovalController: PlanApprovalController
    private var isTesting = false
    
    init(controller: GhostCursorOverlayController, planApprovalController: PlanApprovalController) {
        self.controller = controller
        self.planApprovalController = planApprovalController
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
    
    func runPlanApprovalTest() {
        guard let url = URL(string: "http://localhost:8000/ghost/plan") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let key = SettingsManager.shared.settings.apiKey
        if !key.isEmpty { request.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization") }
        
        let payload: [String: Any] = ["intent": "Click the 'Submit' button"]
        request.httpBody = try? JSONSerialization.data(withJSONObject: payload)
        
        Task {
            do {
                let (data, response) = try await URLSession.shared.data(for: request)
                if let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) {
                    let decoder = JSONDecoder()
                    let realPlan = try decoder.decode(GuidancePlan.self, from: data)
                    
                    await MainActor.run {
                        self.planApprovalController.present(plan: realPlan) { intent in
                            switch intent {
                            case .approve(let approvedPlan):
                                print("Plan approved: \(approvedPlan.steps.count) steps")
                                // Start execution here
                                self.executeApprovedPlan(approvedPlan)
                            case .cancel:
                                print("Plan cancelled")
                            }
                        }
                    }
                } else {
                    print("Failed to fetch GuidancePlan: HTTP status \(String(describing: (response as? HTTPURLResponse)?.statusCode))")
                }
            } catch {
                print("Error fetching GuidancePlan: \(error)")
            }
        }
    }

    private func executeApprovedPlan(_ plan: GuidancePlan) {
        guard let url = URL(string: "http://localhost:8000/ghost/execute") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let key = SettingsManager.shared.settings.apiKey
        if !key.isEmpty { request.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization") }
        
        request.httpBody = try? JSONEncoder().encode(plan)
        
        Task {
            do {
                let (_, response) = try await URLSession.shared.data(for: request)
                if let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) {
                    print("Execution started on backend.")
                } else {
                    print("Execution failed: HTTP status \(String(describing: (response as? HTTPURLResponse)?.statusCode))")
                }
            } catch {
                print("Error sending execute request: \(error)")
            }
        }
    }
}
