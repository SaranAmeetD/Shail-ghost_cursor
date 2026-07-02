import SwiftUI

public enum PlanApprovalIntent {
    case approve(GuidancePlan)
    case cancel
}

public class PlanApprovalViewModel: ObservableObject {
    @Published public var plan: GuidancePlan?
    public var onIntent: ((PlanApprovalIntent) -> Void)?

    public init(plan: GuidancePlan? = nil) {
        self.plan = plan
    }
    
    public var isValid: Bool {
        guard let plan = plan else { return false }
        return !plan.steps.isEmpty
    }
    
    public func removeStep(id: UUID) {
        plan?.steps.removeAll { $0.id == id }
    }
    
    public func updateStep(_ step: GuidancePlanStep) {
        if let index = plan?.steps.firstIndex(where: { $0.id == step.id }) {
            plan?.steps[index] = step
        }
    }
    
    public func approve() {
        if let plan = plan, isValid {
            onIntent?(.approve(plan))
        }
    }
    
    public func cancel() {
        onIntent?(.cancel)
    }
}

public struct PlanApprovalView: View {
    @ObservedObject var viewModel: PlanApprovalViewModel
    @State private var editingStep: GuidancePlanStep?

    public init(viewModel: PlanApprovalViewModel) {
        self.viewModel = viewModel
    }

    public var body: some View {
        VStack(spacing: 0) {
            header
            
            Divider()
            
            if let plan = viewModel.plan, !plan.steps.isEmpty {
                List {
                    ForEach(plan.steps) { step in
                        stepRow(for: step)
                    }
                }
                .listStyle(.plain)
            } else {
                emptyState
            }
            
            Divider()
            
            footer
        }
        .frame(width: 400, height: 500)
        .background(Color(NSColor.windowBackgroundColor))
        .cornerRadius(12)
        .sheet(item: $editingStep) { step in
            EditStepView(step: step) { updatedStep in
                viewModel.updateStep(updatedStep)
            }
        }
    }
    
    private var header: some View {
        HStack {
            Text("Ghost Cursor Plan")
                .font(.headline)
            Spacer()
            if let count = viewModel.plan?.steps.count {
                Text("\(count) action\(count == 1 ? "" : "s")")
                    .foregroundColor(.secondary)
                    .font(.subheadline)
            }
        }
        .padding()
    }
    
    private var emptyState: some View {
        VStack(spacing: 12) {
            Spacer()
            Image(systemName: "cursorarrow.slash")
                .font(.system(size: 48))
                .foregroundColor(.secondary)
            Text("No actions planned")
                .font(.headline)
            Text("The guidance plan contains no executable steps.")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
            Spacer()
        }
        .padding()
    }
    
    private var footer: some View {
        HStack {
            Button("Cancel") {
                viewModel.cancel()
            }
            .keyboardShortcut(.escape, modifiers: [])
            .accessibilityLabel("Cancel execution")
            
            Spacer()
            
            Button("Approve All") {
                viewModel.approve()
            }
            .buttonStyle(.borderedProminent)
            .disabled(!viewModel.isValid)
            .keyboardShortcut(.defaultAction)
            .accessibilityLabel("Approve all actions")
        }
        .padding()
    }
    
    private func stepRow(for step: GuidancePlanStep) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .top) {
                Text(step.action.rawValue.uppercased())
                    .font(.caption.bold())
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(actionColor(for: step.action).opacity(0.2))
                    .foregroundColor(actionColor(for: step.action))
                    .cornerRadius(4)
                
                Text(step.targetSelector)
                    .font(.subheadline.monospaced())
                    .lineLimit(2)
                
                Spacer()
                
                Menu {
                    Button("Edit") {
                        editingStep = step
                    }
                    Button("Remove", role: .destructive) {
                        viewModel.removeStep(id: step.id)
                    }
                } label: {
                    Image(systemName: "ellipsis.circle")
                        .foregroundColor(.secondary)
                }
                .menuStyle(.borderlessButton)
                .frame(width: 24)
            }
            
            Text(step.expectedOutcome)
                .font(.caption)
                .foregroundColor(.secondary)
                .lineLimit(2)
        }
        .padding(.vertical, 4)
    }
    
    private func actionColor(for action: GuidancePlanStep.ActionType) -> Color {
        switch action {
        case .click: return .blue
        case .type: return .green
        case .scroll: return .orange
        case .navigate: return .purple
        }
    }
}

struct EditStepView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var step: GuidancePlanStep
    var onSave: (GuidancePlanStep) -> Void
    
    init(step: GuidancePlanStep, onSave: @escaping (GuidancePlanStep) -> Void) {
        self._step = State(initialValue: step)
        self.onSave = onSave
    }
    
    var body: some View {
        VStack(spacing: 0) {
            Text("Edit Step")
                .font(.headline)
                .padding()
            
            Form {
                Picker("Action", selection: $step.action) {
                    ForEach(GuidancePlanStep.ActionType.allCases, id: \.self) { action in
                        Text(action.rawValue.capitalized).tag(action)
                    }
                }
                
                TextField("Target Selector", text: $step.targetSelector)
                TextField("Expected Outcome", text: $step.expectedOutcome)
            }
            .padding()
            
            Divider()
            
            HStack {
                Button("Cancel") {
                    dismiss()
                }
                .keyboardShortcut(.escape, modifiers: [])
                
                Spacer()
                
                Button("Save") {
                    onSave(step)
                    dismiss()
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
            }
            .padding()
        }
        .frame(width: 350, height: 300)
    }
}
