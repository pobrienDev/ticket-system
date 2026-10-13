"""The ticket-system backend package.

Loading .env happens here, once, so every module that reads os.environ at
import time (auth, database, rate_limit, main) sees the same values no
matter which of them is imported first. load_dotenv only fills in keys that
are not already set, so real environment variables always win.
"""

from dotenv import load_dotenv

load_dotenv()
