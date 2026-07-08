# Ghost Cursor Demo Recording Instructions

**Target Audience:** QA & Marketing
**Feature Scope:** Sprint 4.3 (Complete Implementation)

This document provides a step-by-step script for manually recording the Ghost Cursor demonstration. Please follow exactly to ensure all implemented functionality is highlighted. 
*(Note: VoiceTrigger remains an architectural abstraction and is omitted from this recording).*

## Pre-requisites
1. Log into a **Pro-tier** account on the SHAIL dashboard (required due to the feature flag).
2. Start the SHAIL backend and ensure Ollama/Gemma 4 is running.
3. Open a target application (e.g., Safari or a Text Editor) to act upon.
4. Start your screen recording software (e.g., QuickTime).

## Recording Script

### Phase 1: Triggering
1. While focused on the target application, press **`Cmd+Shift+G`**.
2. **Visual Cue:** The screen should briefly dim or show a capture flash, indicating `ScreenCaptureKit` has captured the context and invoked the VSLM pipeline.
3. **Narration/Text Overlay:** "User intent triggered via native keyboard shortcut. Context sent to Gemma 4."

### Phase 2: Planning
1. Wait for the `GuidancePlan` to be generated.
2. **Visual Cue:** The Plan Approval UI will appear as an overlay, presenting a structured, step-by-step JSON-derived plan (e.g., "Step 1: Click the search bar. Step 2: Type 'weather'.")
3. **Narration/Text Overlay:** "The VSLM Pipeline analyzes the screen and generates a deterministic plan."

### Phase 3: User Approval
1. Hover over the plan to show it is interactive.
2. Click the **"Approve & Execute"** button in the UI.
3. **Narration/Text Overlay:** "User approves the plan, initiating the execution loop."

### Phase 4: Execution
1. Take your hands off the keyboard and mouse. 
2. **Visual Cue:** The system will autonomously move the cursor (Ghost Cursor), perform the click, and type the query using the `AccessibilityBridgeDriver`. 
3. *Note: Ensure the target application is not a DENY domain (e.g., a banking site), or the `PrivacyGuard` will abort the execution.*
4. **Narration/Text Overlay:** "Ghost Cursor executes native interactions step-by-step."

### Phase 5: Completion
1. **Visual Cue:** The Result Observer validates the outcome (e.g., the search results load) and the Ghost Cursor overlay indicates "Task Completed Successfully".
2. **Narration/Text Overlay:** "Result Observer confirms success. Execution complete."
3. Stop recording.

## Post-Recording
- Upload the raw `.mp4` or `.mov` to the Sprint 4.3 release folder.
- Ensure the Clicky dashboard is checked to verify the session telemetry was correctly logged in `ghost_sessions.db`.
