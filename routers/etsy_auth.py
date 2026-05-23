"""
One-time Etsy OAuth 2.0 setup endpoints.

Visit http://localhost:9000/auth/etsy to kick off the flow.
After approving on Etsy, tokens are saved to .env automatically.
This only needs to be done once — refresh tokens never expire.
"""

import os
import secrets
import hashlib
import base64
import httpx
from fastapi import APIRouter
from fastapi.responses import RedirectResponse, HTMLResponse

router = APIRouter()

ETSY_CLIENT_ID = os.getenv("ETSY_API_KEY", "")
REDIRECT_URI   = "http://localhost:9000/auth/etsy/callback"
AUTH_URL       = "https://www.etsy.com/oauth/connect"
TOKEN_URL      = "https://api.etsy.com/v3/public/oauth/token"
SCOPES         = "listings_w listings_r shops_r shops_w"

# In-memory PKCE store — single user, single flow at a time
_pkce_store: dict[str, str] = {}


def _pkce_pair() -> tuple[str, str]:
    verifier  = secrets.token_urlsafe(64)[:128]
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


@router.get("/auth/etsy", include_in_schema=False)
async def etsy_auth_start():
    """Redirect to Etsy OAuth consent screen."""
    if not ETSY_CLIENT_ID:
        return HTMLResponse("<h2>ETSY_API_KEY not set in .env</h2>", status_code=500)

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    _pkce_store[state] = verifier

    scope_encoded = SCOPES.replace(" ", "%20")
    url = (
        f"{AUTH_URL}"
        f"?response_type=code"
        f"&client_id={ETSY_CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope={scope_encoded}"
        f"&state={state}"
        f"&code_challenge={challenge}"
        f"&code_challenge_method=S256"
    )
    return RedirectResponse(url)


@router.get("/auth/etsy/callback", include_in_schema=False)
async def etsy_auth_callback(code: str = "", state: str = "", error: str = ""):
    """Receive auth code from Etsy, exchange for tokens, save to .env."""
    if error:
        return HTMLResponse(f"<h2>Etsy OAuth error: {error}</h2><p>Go back and try again.</p>")

    verifier = _pkce_store.pop(state, None)
    if not verifier:
        return HTMLResponse("<h2>Invalid or expired state — visit /auth/etsy again.</h2>")

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            TOKEN_URL,
            data={
                "grant_type":    "authorization_code",
                "client_id":     ETSY_CLIENT_ID,
                "redirect_uri":  REDIRECT_URI,
                "code":          code,
                "code_verifier": verifier,
            },
        )

    if r.status_code != 200:
        return HTMLResponse(f"<h2>Token exchange failed ({r.status_code})</h2><pre>{r.text}</pre>")

    data = r.json()
    from agents.etsy_client import save_tokens
    save_tokens(data["access_token"], data["refresh_token"], data["expires_in"])

    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head><title>Etsy Connected</title>
    <style>body{font-family:monospace;background:#1a1a2e;color:#00ff88;padding:40px;}</style>
    </head>
    <body>
    <h2>✅ Etsy connected!</h2>
    <p>Tokens saved to .env. You can close this tab.</p>
    <p>Zurg will now publish listings directly to Etsy — no more Printify OAuth dependency.</p>
    </body>
    </html>
    """)
