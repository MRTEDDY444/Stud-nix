"""
Central configuration for Student Hub.
All secrets are read from environment variables — never hardcoded,
never sent to the frontend.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///student_hub.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Search provider
    SEARCH_API_KEY = os.environ.get("SEARCH_API_KEY", "")
    SEARCH_API_PROVIDER = os.environ.get("SEARCH_API_PROVIDER", "mock")

    # AI provider
    AI_API_KEY = os.environ.get("AI_API_KEY", "")
    AI_API_PROVIDER = os.environ.get("AI_API_PROVIDER", "mock")

    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB upload limit

    # Simple in-memory rate limit defaults (per IP, per minute)
    RATE_LIMIT_SEARCH = "20 per minute"
    RATE_LIMIT_AI = "15 per minute"
