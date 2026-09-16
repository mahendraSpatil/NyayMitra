"""Loads backend/.env once at import time. Never hardcode a secret here —
this module only reads from the environment."""

import os

from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()


class Settings:
    cloudinary_cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
    cloudinary_api_key = os.environ.get("CLOUDINARY_API_KEY", "")
    cloudinary_api_secret = os.environ.get("CLOUDINARY_API_SECRET", "")
    # Used only by tests/test_invites.py to sign in as the seeded test
    # accounts via the Identity Toolkit REST API — not read by the app
    # itself at request time.
    firebase_web_api_key = os.environ.get("FIREBASE_WEB_API_KEY", "")

    def require_cloudinary(self) -> None:
        if not (self.cloudinary_cloud_name and self.cloudinary_api_key and self.cloudinary_api_secret):
            raise HTTPException(
                status_code=500,
                detail=(
                    "Cloudinary credentials are not set on the server. Copy "
                    "backend/.env.example to backend/.env and fill in "
                    "CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and "
                    "CLOUDINARY_API_SECRET."
                ),
            )


settings = Settings()
