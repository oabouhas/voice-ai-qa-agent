# Bug Report — Pretty Good AI Voice Agent

I placed 10 test calls across six different scenarios: rescheduling, booking a new appointment, canceling, requesting a refill, asking about hours and insurance, and a deliberately messy "distracted caller" edge case. Full transcripts are in `transcripts/call-01.txt` through `call-10.txt`, and audio is in `recordings/` for a subset of the calls.

I'm leading with the issue that showed up the most, since it's the one I'd actually want fixed first if I worked here. The rest follow roughly in order of how much they'd affect a real patient.

---

### 1. The agent often just doesn't act on what the caller is clearly asking for, then hangs up

**Severity:** High
**Calls:** call-03, call-08, call-10 (and shows up partially in call-06 and call-07 too)

I said things like "I need to reschedule my Friday appointment to Monday" or "I need to cancel my upcoming appointment, I'm moving out of state" — clearly, more than once, in slightly different ways each time. In several calls, the agent just kept cycling through generic greetings ("thanks for calling," "how can I help you today") and never actually engaged with the request. Then, without warning, it would say "I am going to end the call now" and hang up.

What struck me most was call-10, where I deliberately played a distracted caller who mentions a second topic (a billing question) and then explicitly asks the agent which one to handle first. That's about as clear an opening as you can give an agent to take control of the conversation, and it still didn't happen. Seeing this same pattern across four different scenarios and two very different caller styles makes me think this isn't a fluke tied to one flow — it looks like a real gap in how the agent recognizes intent.

---

### 2. Identity verification can fail over and over even when the info is correct, and the eventual "transfer" goes nowhere

**Severity:** High
**Calls:** call-02, call-09

I gave my name and date of birth clearly, spelled the name out letter by letter more than once when asked, and the agent kept saying "I wasn't able to verify your identity" without ever telling me what was wrong or what it actually needed. In call-09 this went on for close to ten back-and-forth turns before it finally offered to loop in a "clinic support team" and said "transferring you now." What I got transferred to sounded like a completely different, generic line ("hello, you've reached the pretty good ai test line") that immediately said goodbye. So the promised handoff didn't actually lead anywhere, and I never got my original request handled.

---

### 3. The agent gave two different dates for the same appointment and never fully resolved which one was right

**Severity:** High
**Call:** call-01

I asked to move an appointment to "the Monday after September 8th." The agent first said "Monday September fourth," which is *before* the 8th — the opposite of what I asked. Later it confirmed "September fourteenth" a few times, which is correct, but then said "September four" again near the end. By the time the call ended, I genuinely couldn't tell you which date my appointment was actually on. For a scheduling system, that's about as bad as it gets — a real patient could easily walk away thinking they have an appointment on a day they don't.

---

### 4. The agent found my appointment in one call, then said I had none in a later call — same name, same date of birth

**Severity:** Medium-High
**Calls:** call-01 vs. call-04

Using the identical patient info both times, the agent successfully looked up and rescheduled an appointment in call-01. In call-04, with nothing changed on my end, it told me "you do not have any upcoming appointments scheduled," even after I asked it to check again. I don't know if this is a lookup bug or a record-matching issue, but either way, it means a patient's ability to manage their own appointment isn't reliable from one call to the next.

---

### 5. Basic questions about hours and weekend availability just get ignored

**Severity:** Medium-High
**Calls:** call-06, call-07

I asked about office hours and weekend availability in at least four different ways in one call and seven in another, and in call-06 none of it got answered before the call ended. Call-07 was a little more interesting — the agent actually answered a related insurance question correctly in the same call, so it's clearly capable of responding to *some* informational questions. It just never got to the hours question, and instead kept redirecting to unrelated things before hanging up. It also said something garbled at one point ("i am bode to end the call now"), which might be worth a separate look — possibly a text-generation glitch rather than a logic issue.

---

## Overall impression

If I had to describe the pattern in one sentence: the agent is inconsistent at recognizing what the caller actually wants, and when it gets stuck, its default is to give up and end the call rather than ask a clarifying question or hand off in a way that actually helps. I saw this across scheduling, canceling, and even a more naturalistic distracted-caller scenario, which is what makes me think it's systemic rather than a quirk of any one flow. If I were prioritizing fixes, I'd start with the date-confirmation bug and the identity-verification loop (#3 and #2) — those are the two most likely to directly hurt a real patient.