from dotenv import load_dotenv
import os

load_dotenv()

TG_API_ID   = int(os.environ["TG_API_ID"])
TG_API_HASH = os.environ["TG_API_HASH"]
TG_PHONE    = os.environ["TG_PHONE"]

TT_API_KEY  = os.environ["TT_API_KEY"]
APP_SECRET  = os.environ.get("APP_SECRET", "")

TT_BASE_URL    = "https://api.teamtailor.com/v1"
TT_API_VERSION = "20161108"

SESSION_PATH = os.path.join(os.path.dirname(__file__), "..", "session", "userbot")
TG_SESSION_STRING = os.environ.get("TG_SESSION_STRING", "")
