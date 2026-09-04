import os
import json
import base64
import asyncio
from datetime import datetime

from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from dotenv import load_dotenv

from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions
from anthropic import Anthropic
import requests

load_dotenv()

app = FastAPI()

deepgram = DeepgramClient(os.getenv("DEEPGRAM_API_KEY"))
claude = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # default "Rachel" voice; swap later if you want

# The persona your bot plays on the call.
SYSTEM_PROMPT = """You are Omnia, a patient calling Pivot Point Orthopedics.
You are testing their AI phone agent. Your goal: reschedule an upcoming
appointment from Friday to the following Monday. Speak naturally, like a real
patient on the phone — short sentences, occasional filler words. If the agent
asks for your name or date of birth, use: Omnia Abouhassan, December 14th, 1998.
Keep each response short (1-2 sentences), like real phone conversation.
If the conversation seems to have reached a natural end, say a polite goodbye.
"""

conversation_history = []


def call_claude(user_said: str) -> str:
    """Send the latest thing the agent said to Claude, get the patient's reply."""
    conversation_history.append({"role": "user", "content": user_said})

    response = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=150,
        system=SYSTEM_PROMPT,
        messages=conversation_history,
    )
    reply = response.content[0].text
    conversation_history.append({"role": "assistant", "content": reply})
    print(f"[CLAUDE] {reply}")
    return reply


def text_to_speech_ulaw(text: str) -> bytes:
    """Call ElevenLabs and get back raw mulaw 8kHz audio (matches Twilio's format)."""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    params = {"output_format": "ulaw_8000"}
    payload = {
        "text": text,
        "model_id": "eleven_turbo_v2_5",
    }
    resp = requests.post(url, headers=headers, params=params, json=payload)
    resp.raise_for_status()
    return resp.content


@app.post("/voice")
async def voice_webhook(request: Request):
    """Twilio hits this when the call connects. We tell it to open a media stream."""
    host = request.headers.get("host")
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="wss://{host}/media-stream" />
    </Connect>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    print("[TWILIO] WebSocket connected")

    stream_sid = None
    loop = asyncio.get_event_loop()

    # --- Set up Deepgram live transcription ---  
    dg_connection = deepgram.listen.live.v("1")

    def on_message(self, result, **kwargs):
        transcript = result.channel.alternatives[0].transcript
        if transcript and result.is_final:
            print(f"[DEEPGRAM] {transcript}")
            asyncio.run_coroutine_threadsafe(
                handle_final_transcript(transcript), loop
            )

    dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)

    options = LiveOptions(
        model="nova-2",
        language="en-US",
        encoding="mulaw",
        sample_rate=8000,
        channels=1,
        interim_results=True,
        utterance_end_ms="1000",
        vad_events=True,
    )
    dg_connection.start(options)

    async def handle_final_transcript(transcript: str):
        """Once the agent finishes a sentence, get Claude's reply and speak it."""
        reply_text = call_claude(transcript)
        audio_bytes = text_to_speech_ulaw(reply_text)
        await send_audio_to_twilio(websocket, stream_sid, audio_bytes)

    async def send_audio_to_twilio(ws, sid, audio_bytes):
        """Twilio expects base64 mulaw audio in ~160-byte (20ms) chunks."""
        chunk_size = 160
        for i in range(0, len(audio_bytes), chunk_size):
            chunk = audio_bytes[i:i + chunk_size]
            payload = base64.b64encode(chunk).decode("utf-8")
            message = {
                "event": "media",
                "streamSid": sid,
                "media": {"payload": payload},
            }
            await ws.send_text(json.dumps(message))
            await asyncio.sleep(0.02)  # pace it roughly at real-time

    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            print(f"[EVENT] {data['event']}")  # log every single event type we get

            if data["event"] == "start":
                stream_sid = data["start"]["streamSid"]
                print(f"[TWILIO] Stream started: {stream_sid}")

            elif data["event"] == "media":
                payload = data["media"]["payload"]
                audio_chunk = base64.b64decode(payload)
                dg_connection.send(audio_chunk)

            elif data["event"] == "stop":
                print("[TWILIO] Stream stopped")
                dg_connection.finish()
                break

    except Exception as e:
        import traceback
        print("[ERROR] Exception in media_stream:")
        traceback.print_exc()
        dg_connection.finish()

    except Exception as e:
        print(f"[ERROR] {e}")
        dg_connection.finish()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)