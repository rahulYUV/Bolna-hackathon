import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
BOLNA_API_KEY = os.getenv("BOLNA_API_KEY")
BOLNA_AGENT_ID = os.getenv("BOLNA_AGENT_ID")
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SHOPKEEPER_PHONE = os.getenv("SHOPKEEPER_PHONE")
DEMO_AUTH_BYPASS = os.getenv("DEMO_AUTH_BYPASS", "false").lower() == "true"
SHOP_NAME = os.getenv("SHOP_NAME", "My kirana shop")
SHOP_TYPE = os.getenv("SHOP_TYPE", "Neighborhood kirana/general store")
SHOP_LOCATION = os.getenv("SHOP_LOCATION", "")
SHOP_LANGUAGE = os.getenv("SHOP_LANGUAGE", "Hindi/Hinglish")
SHOP_CALLING_HOURS = os.getenv("SHOP_CALLING_HOURS", "10:00 AM - 1:00 AM")
MAX_CALL_ATTEMPTS = int(os.getenv("MAX_CALL_ATTEMPTS", "3"))
CUSTOMER_DATA_RETENTION_DAYS = int(os.getenv("CUSTOMER_DATA_RETENTION_DAYS", "30"))
BOLNA_WEBHOOK_SECRET = os.getenv("BOLNA_WEBHOOK_SECRET")
BOLNA_WEBHOOK_ALLOWED_IPS = {
    ip.strip() for ip in os.getenv(
        "BOLNA_WEBHOOK_ALLOWED_IPS",
        "13.203.39.153,13.126.9.249,13.202.133.53",
    ).split(",") if ip.strip()
}
CALL_TRIGGER_COOLDOWN_MINUTES = int(os.getenv("CALL_TRIGGER_COOLDOWN_MINUTES", "5"))

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Create a env and setup the password.")
