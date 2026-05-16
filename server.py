"""
Smriti — voice-driven second brain server.

FastAPI + WebSocket bridging the browser microphone to Gemini Live. The model
talks back as audio; tool calls are intercepted and routed to graph_operation,
which reads/writes the user's Obsidian vault.
"""

import asyncio
import base64
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from google import genai
from google.genai import types

from tools import GraphOperation, execute, TOOL_DECLARATION, build_time_context


ROOT = Path(__file__).parent
load_dotenv(dotenv_path=ROOT / ".env")

API_KEY = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
VAULT_PATH = os.environ.get("VAULT_PATH")
if not API_KEY:
    raise SystemExit("ERROR: GOOGLE_API_KEY (or GEMINI_API_KEY) missing in .env")
if not VAULT_PATH:
    raise SystemExit("ERROR: VAULT_PATH missing in .env")

try:
    TOKEN_THRESHOLD = int(os.environ.get("TOKEN_THRESHOLD", "65000"))
except ValueError:
    TOKEN_THRESHOLD = 65000

SYSTEM_PROMPT_PATH = ROOT / "config" / "system_instructions.md"
THRESHOLD_REMINDER_PATH = ROOT / "config" / "threshold_reminder.md"

app = FastAPI()


def build_system_prompt(graph: GraphOperation) -> str:
    base = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    identity = graph.read_identity()
    return (
        base
        + "\n\n---\n\n# Live Session Context\n\n"
        + build_time_context()
        + "\n\n---\n\n"
        + f"Vault path: `{graph.vault_path}`\n\n"
        + "## identity.md (always loaded — the user's working-memory flash)\n\n"
        + "```markdown\n"
        + identity["content"]
        + "\n```\n"
    )


@app.get("/")
async def serve_index():
    return FileResponse(ROOT / "index.html")


@app.get("/token-tracker")
async def serve_token_tracker():
    test_file = ROOT / "test" / "token_tracker_ui.html"
    if test_file.exists():
        return FileResponse(test_file)
    return {"error": "Token tracker UI not found"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    graph = GraphOperation(VAULT_PATH)
    client = genai.Client(api_key=API_KEY)

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name="Aoede"
                )
            )
        ),
        system_instruction=build_system_prompt(graph),
        tools=[types.Tool(function_declarations=[types.FunctionDeclaration(**TOOL_DECLARATION)])],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )

    threshold_reminder_text = (
        THRESHOLD_REMINDER_PATH.read_text(encoding="utf-8")
        if THRESHOLD_REMINDER_PATH.exists()
        else ""
    )
    reminder_sent = False

    try:
        async with client.aio.live.connect(
            model="gemini-3.1-flash-live-preview",
            config=config,
        ) as session:
            await ws.send_json({"type": "status", "message": f"Connected · Vault: {graph.vault_path}"})

            async def browser_to_gemini():
                try:
                    while True:
                        data = await ws.receive_text()
                        msg = json.loads(data)
                        if msg["type"] == "audio":
                            audio_bytes = base64.b64decode(msg["data"])
                            await session.send_realtime_input(
                                audio=types.Blob(
                                    data=audio_bytes,
                                    mime_type="audio/pcm;rate=16000",
                                ),
                            )
                except WebSocketDisconnect:
                    pass

            async def gemini_to_browser():
                nonlocal reminder_sent
                try:
                    while True:
                        async for message in session.receive():
                            if message.server_content and message.server_content.model_turn:
                                for part in message.server_content.model_turn.parts:
                                    if part.inline_data and part.inline_data.data:
                                        audio_b64 = base64.b64encode(part.inline_data.data).decode("utf-8")
                                        await ws.send_json({"type": "audio", "data": audio_b64})

                            if message.server_content:
                                if message.server_content.input_transcription:
                                    text = message.server_content.input_transcription.text
                                    if text:
                                        await ws.send_json({"type": "input_transcript", "text": text})
                                if message.server_content.output_transcription:
                                    text = message.server_content.output_transcription.text
                                    if text:
                                        await ws.send_json({"type": "output_transcript", "text": text})

                                if message.server_content.turn_complete:
                                    usage = getattr(message, "usage_metadata", None)
                                    if usage is not None:
                                        prompt_tokens = getattr(usage, "prompt_token_count", None) or 0
                                        response_tokens = getattr(usage, "response_token_count", None) or 0
                                        total = getattr(usage, "total_token_count", None) or 0
                                        await ws.send_json({
                                            "type": "token_usage",
                                            "prompt": prompt_tokens,
                                            "response": response_tokens,
                                            "current": total,
                                            "threshold": TOKEN_THRESHOLD,
                                        })
                                        print(f"[TOKENS] Prompt: {prompt_tokens}, Response: {response_tokens}, Total: {total}")
                                        if (
                                            not reminder_sent
                                            and threshold_reminder_text
                                            and total >= TOKEN_THRESHOLD
                                        ):
                                            try:
                                                await session.send_realtime_input(
                                                    text=threshold_reminder_text,
                                                )
                                                reminder_sent = True
                                                await ws.send_json({
                                                    "type": "threshold_reached",
                                                    "current": total,
                                                    "threshold": TOKEN_THRESHOLD,
                                                })
                                            except Exception as inj_err:
                                                print(f"Failed to inject threshold reminder: {inj_err}")
                                    await ws.send_json({"type": "turn_complete"})
                                    break

                                if message.server_content.interrupted:
                                    await ws.send_json({"type": "interrupted"})
                                    break

                            if message.tool_call:
                                for fc in message.tool_call.function_calls:
                                    args = dict(fc.args) if fc.args else {}
                                    action = args.pop("action", None)
                                    await ws.send_json({
                                        "type": "tool_call",
                                        "name": fc.name,
                                        "action": action,
                                    })
                                    result = execute(graph, action, **args) if action else {
                                        "status": "error",
                                        "error": "Missing action",
                                    }
                                    await session.send_tool_response(
                                        function_responses=[
                                            types.FunctionResponse(
                                                id=fc.id,
                                                name=fc.name,
                                                response=result,
                                            )
                                        ]
                                    )
                                    await ws.send_json({
                                        "type": "tool_result",
                                        "name": fc.name,
                                        "action": action,
                                        "status": result.get("status", "unknown"),
                                    })
                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    print(f"Error in gemini_to_browser: {e}")
                    try:
                        await ws.send_json({"type": "error", "message": str(e)})
                    except Exception:
                        pass

            await asyncio.gather(browser_to_gemini(), gemini_to_browser())

    except Exception as e:
        print(f"Session error: {e}")
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    print("[INFO] Starting Smriti on http://localhost:8002")
    uvicorn.run(app, host="127.0.0.1", port=8002)
