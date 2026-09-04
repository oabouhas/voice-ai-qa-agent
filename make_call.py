import os
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_number = os.getenv("TWILIO_PHONE_NUMBER")
target_number = os.getenv("TARGET_PHONE_NUMBER")

# IMPORTANT: update this every time your tunnel URL changes
PUBLIC_URL = "https://nice-rabbits-taste.loca.lt"

client = Client(account_sid, auth_token)

call = client.calls.create(
    to=target_number,
    from_=twilio_number,
    url=f"{PUBLIC_URL}/voice",
)

print(f"Call started: {call.sid}")