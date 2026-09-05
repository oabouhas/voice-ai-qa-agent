import os
import sys
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_number = os.getenv("TWILIO_PHONE_NUMBER")
target_number = os.getenv("TARGET_PHONE_NUMBER")

PUBLIC_URL = "https://voice-ai-qa-agent.onrender.com"

# Pass a scenario name as a command-line argument, e.g.:
#   python make_call.py refill
scenario = sys.argv[1] if len(sys.argv) > 1 else "reschedule"

client = Client(account_sid, auth_token)

call = client.calls.create(
    to=target_number,
    from_=twilio_number,
    url=f"{PUBLIC_URL}/voice?scenario={scenario}",
)

print(f"Call started: {call.sid} (scenario: {scenario})")