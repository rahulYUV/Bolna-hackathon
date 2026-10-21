import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
BOLNA_API_KEY = os.getenv("BOLNA_API_KEY")
BOLNA_AGENT_ID = os.getenv("BOLNA_AGENT_ID")
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Create a env and setup the password.")