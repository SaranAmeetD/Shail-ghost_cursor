import XCTest
@testable import ShailUI

final class PlanApprovalTests: XCTestCase {
    
    func testJSONDecodingSuccess() throws {
        let json = """
        {
            "schema_version": "1",
            "steps": [
                {
                    "action": "click",
                    "target_selector": "button.submit",
                    "fallback_coords": [100, 200],
                    "expected_outcome": "Form submits"
                }
            ]
        }
        """.data(using: .utf8)!
        
        let decoder = JSONDecoder()
        let plan = try decoder.decode(GuidancePlan.self, from: json)
        
        XCTAssertEqual(plan.schemaVersion, "1")
        XCTAssertEqual(plan.steps.count, 1)
        XCTAssertEqual(plan.steps[0].action, .click)
        XCTAssertEqual(plan.steps[0].targetSelector, "button.submit")
        XCTAssertEqual(plan.steps[0].fallbackCoords, [100, 200])
        XCTAssertEqual(plan.steps[0].expectedOutcome, "Form submits")
    }
    
    func testJSONDecodingMissingFields() {
        let json = """
        {
            "schema_version": "1",
            "steps": [
                {
                    "action": "click"
                }
            ]
        }
        """.data(using: .utf8)!
        
        let decoder = JSONDecoder()
        XCTAssertThrowsError(try decoder.decode(GuidancePlan.self, from: json))
    }
    
    func testJSONDecodingMalformed() {
        let json = """
        {
            "schema_version": "1",
            "steps": [
        """.data(using: .utf8)!
        
        let decoder = JSONDecoder()
        XCTAssertThrowsError(try decoder.decode(GuidancePlan.self, from: json))
    }
    
    func testJSONDecodingUnicode() throws {
        let json = """
        {
            "schema_version": "1",
            "steps": [
                {
                    "action": "type",
                    "target_selector": "input.search",
                    "fallback_coords": [0, 0],
                    "expected_outcome": "🔍 searching for 漢字"
                }
            ]
        }
        """.data(using: .utf8)!
        
        let decoder = JSONDecoder()
        let plan = try decoder.decode(GuidancePlan.self, from: json)
        XCTAssertEqual(plan.steps[0].expectedOutcome, "🔍 searching for 漢字")
    }
    
    func testViewModelIntentEmissionApprove() {
        let step = GuidancePlanStep(action: .click, targetSelector: "btn", fallbackCoords: [0,0], expectedOutcome: "Success")
        let plan = GuidancePlan(schemaVersion: "1", steps: [step])
        let vm = PlanApprovalViewModel(plan: plan)
        
        var emittedIntent: PlanApprovalIntent?
        vm.onIntent = { intent in
            emittedIntent = intent
        }
        
        XCTAssertTrue(vm.isValid)
        vm.approve()
        
        if case .approve(let approvedPlan) = emittedIntent {
            XCTAssertEqual(approvedPlan, plan)
        } else {
            XCTFail("Expected .approve intent")
        }
    }
    
    func testViewModelIntentEmissionCancel() {
        let plan = GuidancePlan(schemaVersion: "1", steps: [])
        let vm = PlanApprovalViewModel(plan: plan)
        
        var emittedIntent: PlanApprovalIntent?
        vm.onIntent = { intent in
            emittedIntent = intent
        }
        
        XCTAssertFalse(vm.isValid) // Invalid because it's empty
        vm.approve() // Should not emit because it's invalid
        XCTAssertNil(emittedIntent)
        
        vm.cancel()
        
        if case .cancel = emittedIntent {
            XCTAssertTrue(true)
        } else {
            XCTFail("Expected .cancel intent")
        }
    }
    
    func testViewModelEditStep() {
        let step1 = GuidancePlanStep(action: .click, targetSelector: "btn1", fallbackCoords: [0,0], expectedOutcome: "One")
        let step2 = GuidancePlanStep(action: .click, targetSelector: "btn2", fallbackCoords: [0,0], expectedOutcome: "Two")
        let plan = GuidancePlan(schemaVersion: "1", steps: [step1, step2])
        let vm = PlanApprovalViewModel(plan: plan)
        
        var modifiedStep = step1
        modifiedStep.targetSelector = "btn1_modified"
        
        vm.updateStep(modifiedStep)
        
        XCTAssertEqual(vm.plan?.steps[0].targetSelector, "btn1_modified")
        XCTAssertEqual(vm.plan?.steps[1].targetSelector, "btn2")
    }
    
    func testViewModelRemoveStep() {
        let step1 = GuidancePlanStep(action: .click, targetSelector: "btn1", fallbackCoords: [0,0], expectedOutcome: "One")
        let step2 = GuidancePlanStep(action: .click, targetSelector: "btn2", fallbackCoords: [0,0], expectedOutcome: "Two")
        let plan = GuidancePlan(schemaVersion: "1", steps: [step1, step2])
        let vm = PlanApprovalViewModel(plan: plan)
        
        vm.removeStep(id: step1.id)
        
        XCTAssertEqual(vm.plan?.steps.count, 1)
        XCTAssertEqual(vm.plan?.steps[0].id, step2.id)
        
        vm.removeStep(id: step2.id)
        XCTAssertEqual(vm.plan?.steps.count, 0)
        XCTAssertFalse(vm.isValid) // Emptied plan should be invalid
    }
}
