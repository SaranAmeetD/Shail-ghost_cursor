import Foundation

/// Codable representation of the Python `GuidancePlan` JSON schema.
/// This acts as a read-only mirror of the single source of truth in `apps/ghost-cursor/models.py`.
public struct GuidancePlan: Codable, Equatable {
    public var schemaVersion: String
    public var steps: [GuidancePlanStep]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case steps
    }
}

public struct GuidancePlanStep: Codable, Equatable, Identifiable {
    // Generate a local ID for SwiftUI iteration, not part of JSON schema
    public var id = UUID()
    
    public var action: ActionType
    public var targetSelector: String
    public var fallbackCoords: [Int]
    public var expectedOutcome: String

    public enum ActionType: String, Codable, Equatable, CaseIterable {
        case click
        case type
        case scroll
        case navigate
    }

    enum CodingKeys: String, CodingKey {
        case action
        case targetSelector = "target_selector"
        case fallbackCoords = "fallback_coords"
        case expectedOutcome = "expected_outcome"
    }
}
