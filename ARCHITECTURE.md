# Architecture

## Overview

The bot places an outbound call through Twilio, which opens a live, bidirectional audio stream to a FastAPI server I wrote and deployed on Render. As the other agent speaks, the audio is forwarded in real time to Deepgram for transcription. Once Deepgram flags a finished sentence, that transcript goes to Claude, which is playing a "patient" persona with a specific goal for that call (reschedule an appointment, ask about insurance, request a refill, and so on, depending on which scenario I pass in). Claude's reply is converted to speech by ElevenLabs and streamed straight back into the live call. Twilio separately records the whole call as audio, and each conversation gets printed to the server logs in full once the call ends.

## Why a pipeline instead of a Realtime API

I considered using a voice-to-voice Realtime API (the kind that handles speech-to-speech in one continuous stream) instead of stitching together separate STT, LLM, and TTS steps. I went with the pipeline approach for a few reasons that mattered more to me than raw latency:

- **Debuggability.** With a pipeline, I can see exactly what was transcribed, what Claude decided to say, and what got sent to text-to-speech, all as plain text in the logs. When something went wrong (and a lot did — see the README), I could immediately tell which stage broke. A Realtime API collapses all of that into one opaque audio-to-audio stream, which would have made debugging significantly harder given how much troubleshooting this project actually required.
- **Using tools I already understood.** I'm comfortable with Python, FastAPI, and reasoning about discrete API calls. A pipeline let me build and fix this incrementally, one stage at a time, rather than debugging a single black-box connection.
- **This is a 6-hour take-home, not a production voice product.** The latency cost of a pipeline (roughly the sum of STT + LLM + TTS round-trip time per turn) is a real tradeoff, and in a production setting with tighter latency requirements, I'd lean toward a Realtime API. For this project, coherent conversation and the ability to actually finish the build mattered more than shaving a few hundred milliseconds off each turn.

## Key design decisions

**Deployment on Render instead of local tunneling.** I started with ngrok, then localtunnel, to expose my local server to Twilio. Both were unreliable for sustaining a live WebSocket connection — I'd get calls that connected and then dropped a few seconds in, seemingly at random. Rather than keep patching around a fundamentally flaky setup, I deployed the server on Render's free tier, which gave me a permanent public URL and completely eliminated the tunnel-related failures. In hindsight, I'd start here next time instead of treating deployment as an afterthought.

**Scenario system via Twilio's `<Parameter>` tag.** To test different intents (scheduling, canceling, refills, etc.) without duplicating code, I built a dictionary of system prompts keyed by scenario name, and pass the chosen scenario into each call. My first attempt passed this as a query string on the WebSocket URL, which Twilio silently strips — every call quietly ran the default scenario regardless of what I intended. I fixed this by using Twilio's native `<Parameter>` tag nested inside `<Stream>`, which arrives reliably in the `start` event's `customParameters`.

**Per-call state, not global state.** Conversation history and the active scenario are scoped to each WebSocket connection, not stored as module-level globals. This matters because Render can (and did) handle calls back-to-back, and global state would have leaked one call's conversation into the next.

**Call recording via `<Start><Recording>`, run alongside the media stream.** I initially assumed I could add a `record` attribute directly to `<Connect>`, the same way `<Dial>` supports it. Twilio's schema doesn't allow that, and it failed silently (no crash, just no recording) — I only found the actual cause by checking Twilio's own XML validation warnings on the call detail page. The fix was using the dedicated `<Start><Recording>` element, which runs independently of the stream.

## What I'd do differently with more time

The agent-side bugs I found suggest the persona prompts themselves are working — Claude reliably stays in character, states its goal, and pushes back when the other agent gives contradictory information (this is actually how I caught the double-booking-date bug in call-01). If I had more time, I'd add a lightweight state machine on top of the LLM to explicitly track "has the goal been achieved yet," so the bot could more assertively steer a call back on track rather than relying entirely on prompting.