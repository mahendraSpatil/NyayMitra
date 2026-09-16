"""Signed, time-limited delivery URLs for authenticated-type Cloudinary
assets. Every one of these case documents is uploaded with type
"authenticated" (never "upload") — never publicly fetchable by URL, only
through a URL minted here, each time, after the caller has been
re-authorized. Never switch an asset to public/"upload" type to work
around a 401/404; that defeats the entire point.
"""

import time

import cloudinary
import cloudinary.utils

from ..config import settings

# Long enough for our own backend to fetch the file right after upload, or
# for a client to load it once in a viewer — short enough that a leaked
# URL (a browser history entry, a proxy log) stops working quickly.
DEFAULT_EXPIRY_SECONDS = 300

_configured = False


def _ensure_configured() -> None:
    # api_sign_request (sign-upload) takes the secret as an explicit
    # argument and doesn't need this, but private_download_url reads
    # cloud_name/api_key/api_secret from cloudinary's own global config
    # state instead — has to be set somewhere before it's called.
    global _configured
    if _configured:
        return
    settings.require_cloudinary()
    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )
    _configured = True


def signed_download_url(public_id: str, expiry_seconds: int = DEFAULT_EXPIRY_SECONDS) -> tuple[str, int]:
    """Returns (url, expiresAtUnixTimestamp). public_id must be the exact
    value Cloudinary assigned on upload (for resource_type=raw, that
    includes the file extension — a pre-upload guess at the public_id
    without the extension will not resolve).
    """
    _ensure_configured()
    expires_at = int(time.time()) + expiry_seconds
    url = cloudinary.utils.private_download_url(
        public_id,
        None,
        resource_type="raw",
        type="authenticated",
        attachment=False,
        expires_at=expires_at,
    )
    return url, expires_at
