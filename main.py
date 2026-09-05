import os
import json
import base64
import asyncio
import traceback

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
ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # "Rachel" voice

BASE_PATIENT_INFO = """If the agent asks for your name or date of birth, use:
Omnia Abouhassan, December 14th, 1998. Speak naturally, like a real patient on
the phone - short sentences, occasional filler words. Keep each response short
(1-2 sentences), like a real phone conversation. If the agent hasn't said
anything yet, start by greeting them and stating your goal for the call.
If the conversation seems to have reached a natural end, say a polite goodbye.
"""

SCENARIOS = {
    "reschedule": f"""You are Omnia, a patient calling Pivot Point Orthopedics.
You are testing their AI phone agent. Your goal: reschedule an upcoming
appointment from Friday to the following Monday.
{BASE_PATIENT_INFO}""",

    "new_appointment": f"""You are Omnia, a new patient calling Pivot Point
Orthopedics for the first time. Your goal: schedule a new appointment for a
knee pain evaluation, ideally sometime next week. You don't have an existing
appointment on file.
{BASE_PATIENT_INFO}""",

    "cancel": f"""You are Omnia, a patient calling Pivot Point Orthopedics.
Your goal: cancel your upcoming appointment entirely (not reschedule it) because
you're moving out of state and won't need the follow-up.
{BASE_PATIENT_INFO}""",

    "refill": f"""You are Omnia, a patient calling Pivot Point Orthopedics.
Your goal: request a refill of your pain medication prescription, which you're
running low on. If asked which medication, say "the one Dr. Lukovsky prescribed
after my last visit" and let the agent figure out details naturally.
{BASE_PATIENT_INFO}""",

    "hours_insurance": f"""You are Omnia, a prospective patient calling Pivot
Point Orthopedics for the first time. Your goal: ask about their office hours,
whether they're open on weekends, and whether they accept Blue Cross Blue
Shield insurance. You are not trying to book anything yet - just gathering info.
{BASE_PATIENT_INFO}""",

    "edge_case": f"""You are Omnia, a somewhat distracted patient calling Pivot
Point Orthopedics. Your goal: ask about rescheduling an appointment, but partway
through the call, interrupt yourself, change the subject briefly (mention you
also want to ask about a billing question), then circle back to the original
rescheduling request. Be a little unclear or meandering, like a real distracted
caller, but eventually get to the point.
{BASE_PATIENT_INFO}""",
}

DEFAULT_SCENARIO = "reschedule"


def print_full_transcript(transcript_lines: list, call_id: str, scenario: str):
    """Print one clean, easy-to-copy transcript block when the call ends."""
    print("\n" + "=" * 60)
    print(f"FULL TRANSCRIPT - Call ID: {call_id} - Scenario: {scenario}")
    print("=" * 60)
    if transcript_lines:
        for line in transcript_lines:
            print(line)
    else:
        print("(no transcript captured)")
    print("=" * 60 + "\n")


def call_claude(conversation_history: list, user_said: str, system_prompt: str) -> str:
    """Send the latest thing the agent said to Claude, get the patient's reply."""
    conversation_history.append({"role": "user", "content": user_said})

    response = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=150,
        system=system_prompt,
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
    """Twilio hits this when the call connects. We tell it to open a media stream
    AND record the call (both sides) so we have audio for the submission."""
    host = request.headers.get("host")
    scenario = request.query_params.get("scenario", DEFAULT_SCENARIO)
    if scenario not in SCENARIOS:
        scenario = DEFAULT_SCENARIO
    # NOTE: Twilio strips query strings from the <Stream> url, so we pass the
    # scenario via a <Parameter> tag instead, which arrives in the 'start' event.
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="wss://{host}/media-stream" record="record-from-answer-dual">
            <Parameter name="scenario" value="{scenario}" />
        </Stream>
    </Connect>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    print("[TWILIO] WebSocket connected")

    stream_sid = None
    call_active = True
    conversation_history = []
    transcript_lines = []
    scenario = DEFAULT_SCENARIO  # overwritten once the 'start' event arrives
    system_prompt = SCENARIOS[scenario]
    loop = asyncio.get_running_loop()

    dg_connection = deepgram.listen.live.v("1")

    def on_message(self, result, **kwargs):
        transcript = result.channel.alternatives[0].transcript
        if transcript and result.is_final:
            print(f"[DEEPGRAM] {transcript}")
            transcript_lines.append(f"AGENT: {transcript}")
            future = asyncio.run_coroutine_threadsafe(
                handle_final_transcript(transcript), loop
            )
            future.add_done_callback(log_task_errors)

    def on_error(self, error, **kwargs):
        print(f"[DEEPGRAM ERROR] {error}")

    def log_task_errors(f):
        try:
            f.result()
        except Exception:
            print("[ERROR] Exception in scheduled task:")
            traceback.print_exc()

    dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
    dg_connection.on(LiveTranscriptionEvents.Error, on_error)

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

    async def speak(reply_text: str):
        if not call_active:
            print("[INFO] Call already ended, skipping speech")
            return
        print(f"[SPEAKING] {reply_text}")
        transcript_lines.append(f"YOU: {reply_text}")
        audio_bytes = text_to_speech_ulaw(reply_text)
        await send_audio_to_twilio(websocket, stream_sid, audio_bytes)

    async def handle_final_transcript(transcript: str):
        reply_text = call_claude(conversation_history, transcript, system_prompt)
        await speak(reply_text)

    async def send_audio_to_twilio(ws, sid, audio_bytes):
        chunk_size = 160
        try:
            for i in range(0, len(audio_bytes), chunk_size):
                if not call_active:
                    break
                chunk = audio_bytes[i:i + chunk_size]
                payload = base64.b64encode(chunk).decode("utf-8")
                message = {
                    "event": "media",
                    "streamSid": sid,
                    "media": {"payload": payload},
                }
                await ws.send_text(json.dumps(message))
                await asyncio.sleep(0.02)
        except Exception:
            print("[INFO] Call ended while bot was still speaking - stopping playback")

    async def send_initial_greeting():
        await asyncio.sleep(1.5)
        print("[INIT] Sending opening line")
        opening_line = call_claude(
            conversation_history,
            "(The call has just connected. No one has spoken yet.)",
            system_prompt,
        )
        await speak(opening_line)

    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            print(f"[EVENT] {data['event']}")

            if data["event"] == "start":
                stream_sid = data["start"]["streamSid"]
                custom_params = data["start"].get("customParameters", {})
                scenario = custom_params.get("scenario", DEFAULT_SCENARIO)
                if scenario not in SCENARIOS:
                    scenario = DEFAULT_SCENARIO
                system_prompt = SCENARIOS[scenario]
                print(f"[TWILIO] Stream started: {stream_sid} - Scenario: {scenario}")
                asyncio.create_task(send_initial_greeting())

            elif data["event"] == "media":
                payload = data["media"]["payload"]
                audio_chunk = base64.b64decode(payload)
                dg_connection.send(audio_chunk)

            elif data["event"] == "stop":
                print("[TWILIO] Stream stopped")
                call_active = False
                dg_connection.finish()
                print_full_transcript(transcript_lines, stream_sid or "unknown-call", scenario)
                break

    except Exception:
        print("[ERROR] Exception in media_stream:")
        traceback.print_exc()
        call_active = False
        dg_connection.finish()
        print_full_transcript(transcript_lines, stream_sid or "unknown-call", scenario)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)