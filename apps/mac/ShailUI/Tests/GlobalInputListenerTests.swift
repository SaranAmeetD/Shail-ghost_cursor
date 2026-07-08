import XCTest
@testable import ShailUI

final class GlobalInputListenerTests: XCTestCase {
    func testIsShailHotkey_CmdShiftG() {
        let listener = GlobalInputListener()
        
        // Construct a synthetic Cmd+Shift+G NSEvent
        let event = NSEvent.keyEvent(
            with: .keyDown,
            location: .zero,
            modifierFlags: [.command, .shift],
            timestamp: 0,
            windowNumber: 0,
            context: nil,
            characters: "G",
            charactersIgnoringModifiers: "G",
            isARepeat: false,
            keyCode: 5 // 5 corresponds to the 'G' key
        )!
        
        XCTAssertTrue(listener.isShailHotkey(event))
    }
}
