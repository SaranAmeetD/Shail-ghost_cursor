import sys
import os
import asyncio
import json
import logging
import gc
import re
from typing import Dict, Any, List, Optional
import websockets
from apps.shail.llm import call_llm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models import GuidancePlan


logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Ghost Cursor, an AI-powered UI execution engine.
Your task is to analyze the provided screenshot and convert the user's high-level intent into a structured, ordered GuidancePlan.

You MUST respond with a valid JSON object matching the following GuidancePlan schema:
{
  "steps": [
    {
      "action": "click" | "type" | "scroll" | "navigate",
      "target_selector": "string (CSS selector or element description)",
      "fallback_coords": [x, y],
      "expected_outcome": "string describing what changes visually"
    }
  ]
}

Only return valid JSON. Do not include markdown formatting or extra conversational text.
"""

class VSLMPipeline:
    def __init__(self, ws_uri: str = "ws://localhost:8765/capture", model: str = "gemma4"):
        self.ws_uri = ws_uri
        self.model = model

    async def capture_screen_base64(self, timeout: float = 10.0) -> str:
        """
        Connect to CaptureService WebSocket and request a single-frame base64 PNG.
        """
        logger.info(f"Connecting to CaptureService at {self.ws_uri}...")
        async with websockets.connect(self.ws_uri) as ws:
            request_id = "vslm-capture-sprint1.2"
            request_payload = {
                "type": "request_png_base64",
                "request_id": request_id
            }
            await ws.send(json.dumps(request_payload))
            
            # Await single frame response
            while True:
                response_str = await asyncio.wait_for(ws.recv(), timeout=timeout)
                response = json.loads(response_str)
                if response.get("type") == "png_response" and response.get("request_id") == request_id:
                    if response.get("status") == "ok":
                        data_b64 = response["data_b64"]
                        # Verify it is not empty
                        if not data_b64 or len(data_b64.strip()) == 0:
                            raise ValueError("Received empty base64 image data")
                        return data_b64
                    else:
                        raise RuntimeError(f"Capture failed: {response.get('message', 'Unknown error')}")

    async def generate_guidance_plan(self, intent: str, image_base64: str) -> GuidancePlan:
        """
        Send image + intent to Ollama using Shail LLM interface and parse into GuidancePlan.
        """
        messages = [
            {
                "role": "user",
                "content": f"User intent: {intent}",
                "images": [image_base64]
            }
        ]
        
        try:
            # Copy messages list and inner dictionaries to avoid side-effects from the finally block mutation
            messages_copy = [
                {k: (list(v) if isinstance(v, list) else v) for k, v in m.items()}
                for m in messages
            ]
            response_text, meta = await call_llm(
                messages_copy,
                system_prompt=SYSTEM_PROMPT,
                model=self.model
            )
            
            logger.info("Parsing VSLM output...")
            # Clean output in case model returns markdown wrapper like ```json ... ```
            cleaned_text = self._clean_json_response(response_text)
            
            # Parse raw dict
            parsed_dict = json.loads(cleaned_text)
            
            # Validate against Pydantic schema
            plan = GuidancePlan.model_validate(parsed_dict)
            return plan
        finally:
            # Transient image cleanup: explicitly delete base64 strings and trigger gc
            # Note: We treat gc as an optional cleanup step, not a security mechanism,
            # but we explicitly nullify references.
            if 'messages' in locals():
                for m in messages:
                    if 'images' in m:
                        m['images'] = None
                del messages
            logger.info("Transient screenshot memory reference cleared.")

    def _clean_json_response(self, text: str) -> str:
        """
        Helper to strip markdown JSON codeblock markers and whitespace.
        """
        cleaned = text.strip()
        # Find JSON blocks: ```json ... ```
        pattern = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
        match = pattern.search(cleaned)
        if match:
            cleaned = match.group(1).strip()
        return cleaned
