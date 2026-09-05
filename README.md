# Voice AI QA Agent

This is an automated voice bot I built to test Pretty Good AI's phone agent for Pivot Point Orthopedics. It calls their test line, plays the role of a patient with a specific goal (rescheduling an appointment, asking about insurance, requesting a refill, and so on), has a real spoken conversation with their AI, and surfaces bugs based on how that conversation actually goes.

## How it works

When the bot places a call, Twilio opens a live, two-way audio connection to a small FastAPI server I wrote. As the other agent speaks, Deepgram transcribes it in real time, that transcript gets sent to Claude (which is playing the "patient" persona), and Claude's reply is converted to speech by ElevenLabs and streamed straight back into the call. Twilio also records the whole call separately as audio. When the call ends, the full conversation prints to the server logs.

I've written up the reasoning behind these choices — including where I considered a Realtime API instead — in `ARCHITECTURE.md`.

## Setting it up

1. Clone the repo and set up a virtual environment:
```bash
   git clone https://github.com/oabouhas/voice-ai-qa-agent.git
   cd voice-ai-qa-agent
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and fill in your own keys:
```bash
   cp .env.example .env
```
   You'll need free-tier accounts for:
   - **Twilio** (Account SID, Auth Token, and a phone number)
   - **Deepgram** (API key)
   - **Anthropic** (API key)
   - **ElevenLabs** (API key)

3. Deploy `main.py` somewhere with a real, public URL. I used [Render's](https://render.com) free tier. Twilio has to be able to reach your server over the internet, so this won't work running purely on localhost — I actually tried that first, and it's part of what pushed me toward a proper deployment (more on that below).

4. Update `PUBLIC_URL` at the top of `make_call.py` to point at wherever you deployed it.

## Placing a call

Once it's deployed, running a test call is one command:

```bash
python make_call.py <scenario>
```

`<scenario>` can be any of:
- `reschedule` — move an existing appointment (this is the default if you leave it off)
- `new_appointment` — a new patient booking their first visit
- `cancel` — cancel an appointment outright
- `refill` — request a prescription refill
- `hours_insurance` — ask about hours and insurance, no booking involved
- `edge_case` — a distracted caller who brings up a second topic mid-call and circles back

Once the call ends, the full transcript prints to your server's logs (search for `FULL TRANSCRIPT`). Audio is available in the Twilio console under Monitor → Logs → Voice → Call Recordings, downloadable directly as MP3.

## What's in here
main.py # FastAPI server that runs the actual conversation loop
make_call.py # Places an outbound call with whichever scenario you pick
transcripts/ # All 10 required test call transcripts
recordings/ # MP3 audio for a subset of the calls (see note below)
BUG_REPORT.md # What I found wrong with the agent, and why it matters
ARCHITECTURE.md # Why I built it this way

## Honestly, how this actually went

I want to be upfront that this took more iteration than I expected, and most of it wasn't the AI conversation logic — it was infrastructure. A few things that genuinely tripped me up, in case it's useful context for anyone reading the commit history:

- My first approach used a local tunnel (ngrok, then localtunnel) to expose my laptop to Twilio. Both turned out to be unreliable for sustaining a real-time WebSocket connection — calls would connect, then drop a few seconds in for no clear reason. I eventually gave up patching around it and deployed the server permanently on Render instead, which fixed the problem completely.
- I initially tried passing which scenario to run as a query string on the call URL. Twilio silently strips query strings from `<Stream>` URLs, so every call quietly ran the default scenario no matter what I passed. I only caught this by adding debug logging and noticing the query string was arriving empty. The fix was using Twilio's own `<Parameter>` tag inside `<Stream>`, which does get delivered reliably.
- Call recording didn't work at first because I'd assumed `<Connect>` supported a `record` attribute the same way `<Dial>` does. It doesn't — Twilio actually has a separate `<Start><Recording>` element for exactly this, which runs alongside the media stream.
- Early on, the bot's speech sounded choppy and kept cutting out mid-sentence. That turned out to be a manual `sleep()` I'd added between audio chunks, thinking I needed to pace playback myself. Twilio already handles that pacing on its end — removing the sleep fixed it.

Because the recording fix landed partway through my testing, I have full transcripts for all 10 required calls, but audio for a subset of them. I'd rather be upfront about that than pad the numbers.