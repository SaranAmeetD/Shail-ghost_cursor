import SwiftUI

enum GhostCursorAction {
    case hover
    case click
    case type
    case navigate
    case none
}

struct GhostCursorRingView: View {
    @Binding var currentPosition: CGPoint
    @Binding var currentAction: GhostCursorAction
    
    // Animation states
    @State private var isPulsing: Bool = false
    @State private var flashOpacity: Double = 0.0
    @State private var ringScale: CGFloat = 1.0
    
    // Constants from PRD
    let ringSize: CGFloat = 40.0
    let strokeWidth: CGFloat = 2.0
    let ringColor = Color(hex: "#3B8BD4") ?? Color.blue
    
    var body: some View {
        ZStack {
            // Main ring
            Circle()
                .stroke(ringColor, lineWidth: strokeWidth)
                .frame(width: ringSize, height: ringSize)
                // Glow effect
                .shadow(color: ringColor.opacity(0.6), radius: 8, x: 0, y: 0)
                .shadow(color: ringColor.opacity(0.4), radius: 15, x: 0, y: 0)
                
            // Flash overlay for actions
            Circle()
                .fill(ringColor)
                .frame(width: ringSize, height: ringSize)
                .opacity(flashOpacity)
        }
        .scaleEffect(ringScale)
        // Position relies on the window being transparent and covering the screen,
        // or the window itself moving. We will assume the window itself moves to the position,
        // so this view is just centered in the window.
        // Wait, if the window is transparent and covers the screen, we need to position it.
        // Let's assume the window covers the screen, so we offset the view.
        .position(x: currentPosition.x, y: currentPosition.y)
        .animation(.easeInOut(duration: 0.3), value: currentPosition)
        .onChange(of: currentAction) { _, newAction in
            handleAction(newAction)
        }
    }
    
    private func handleAction(_ action: GhostCursorAction) {
        // Reset animations
        isPulsing = false
        ringScale = 1.0
        flashOpacity = 0.0
        
        switch action {
        case .hover:
            // Pulse animation
            withAnimation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true)) {
                ringScale = 1.15
            }
        case .click, .type, .navigate:
            // Flash on action fire
            withAnimation(.easeOut(duration: 0.1)) {
                flashOpacity = 0.8
                ringScale = 0.8
            }
            // Fade out the flash
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                withAnimation(.easeIn(duration: 0.2)) {
                    flashOpacity = 0.0
                    ringScale = 1.0
                }
            }
        case .none:
            break
        }
    }
}

// Helper for Hex colors
extension Color {
    init?(hex: String) {
        var hexSanitized = hex.trimmingCharacters(in: .whitespacesAndNewlines)
        hexSanitized = hexSanitized.replacingOccurrences(of: "#", with: "")

        var rgb: UInt64 = 0

        var r: CGFloat = 0.0
        var g: CGFloat = 0.0
        var b: CGFloat = 0.0
        var a: CGFloat = 1.0

        let length = hexSanitized.count

        guard Scanner(string: hexSanitized).scanHexInt64(&rgb) else { return nil }

        if length == 6 {
            r = CGFloat((rgb & 0xFF0000) >> 16) / 255.0
            g = CGFloat((rgb & 0x00FF00) >> 8) / 255.0
            b = CGFloat(rgb & 0x0000FF) / 255.0

        } else if length == 8 {
            r = CGFloat((rgb & 0xFF000000) >> 24) / 255.0
            g = CGFloat((rgb & 0x00FF0000) >> 16) / 255.0
            b = CGFloat((rgb & 0x0000FF00) >> 8) / 255.0
            a = CGFloat(rgb & 0x000000FF) / 255.0

        } else {
            return nil
        }

        self.init(red: r, green: g, blue: b, opacity: a)
    }
}
