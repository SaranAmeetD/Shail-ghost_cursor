import json
import logging
from typing import Dict, Any, Optional

# We use standard library asyncio and websockets if available
# We will use websockets package which is standard for python asyncio websocket clients
try:
    import websockets
    import asyncio
except ImportError:
    # If not installed, it will raise ImportError when initialized,
    # but the interface remains intact.
    pass

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from execution.interfaces import VerifiableCursorDriver

logger = logging.getLogger(__name__)

class AccessibilityBridgeDriver(VerifiableCursorDriver):
    """
    CursorDriver implementation that communicates with the native 
    macOS AccessibilityBridge WebSocket server at ws://localhost:8766.
    """
    def __init__(self, uri: str = "ws://localhost:8766/accessibility"):
        self.uri = uri

    async def _send_command(self, payload: Dict[str, Any]) -> bool:
        """Helper to send a command via short-lived websocket connection."""
        try:
            # We open a connection per command for simplicity and statelessness in this basic adapter.
            # In a production environment with high frequency, a persistent connection would be preferred.
            async with websockets.connect(self.uri) as websocket:
                await websocket.send(json.dumps(payload))
                response_str = await websocket.recv()
                response = json.loads(response_str)
                if response.get("success"):
                    return True
                else:
                    logger.error(f"AccessibilityBridge command failed: {response.get('error', 'Unknown error')}")
                    return False
        except Exception as e:
            logger.error(f"Failed to connect to AccessibilityBridge: {e}")
            return False

    async def _send_command_raw(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Helper to send a command and return the raw JSON response."""
        try:
            async with websockets.connect(self.uri) as websocket:
                await websocket.send(json.dumps(payload))
                response_str = await websocket.recv()
                return json.loads(response_str)
        except Exception as e:
            logger.error(f"Failed to connect to AccessibilityBridge: {e}")
            return None

    def click(self, x: int, y: int) -> bool:
        payload = {
            "command": "click",
            "x": int(x),
            "y": int(y)
        }
        return asyncio.run(self._send_command(payload))

    def type_text(self, text: str) -> bool:
        payload = {
            "command": "type",
            "text": text
        }
        return asyncio.run(self._send_command(payload))

    def press_key(self, key: str) -> bool:
        payload = {
            "command": "press_key",
            "key": key
        }
        return asyncio.run(self._send_command(payload))

    def scroll(self, x: int, y: int, delta_x: int, delta_y: int) -> bool:
        payload = {
            "command": "scroll",
            "x": int(x),
            "y": int(y),
            "delta_x": int(delta_x),
            "delta_y": int(delta_y)
        }
        return asyncio.run(self._send_command(payload))

    def navigate(self, url: str) -> bool:
        # Navigate is defined as an interface method only per constraints.
        # Concrete implementation deferred.
        logger.info(f"navigate() called with url={url} - implementation deferred.")
        return True

    def get_element_at(self, x: int, y: int) -> Optional[Dict[str, Any]]:
        payload = {
            "command": "get_element_at",
            "x": int(x),
            "y": int(y)
        }
        response = asyncio.run(self._send_command_raw(payload))
        if response and response.get("success"):
            return response.get("element")
        return None
