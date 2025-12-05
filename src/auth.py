"""
OAuth2 Authentication module for myUplink API
"""
import json
import webbrowser
from pathlib import Path
from urllib.parse import urlencode, parse_qs, urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler

import requests
from requests_oauthlib import OAuth2Session
from loguru import logger

from config import settings

# Configuration from centralized settings
CLIENT_ID = settings.MYUPLINK_CLIENT_ID
CLIENT_SECRET = settings.MYUPLINK_CLIENT_SECRET
REDIRECT_URI = settings.MYUPLINK_CALLBACK_URL
AUTH_URL = settings.MYUPLINK_AUTH_URL
TOKEN_URL = settings.MYUPLINK_TOKEN_URL
TOKENS_FILE = Path.home() / '.myuplink_tokens.json'


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback"""

    authorization_code = None

    def do_GET(self):
        """Handle GET request from OAuth redirect"""
        query = urlparse(self.path).query
        params = parse_qs(query)

        if 'code' in params:
            OAuthCallbackHandler.authorization_code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"""
                <html>
                <body>
                    <h1>Authorization Successful!</h1>
                    <p>You can close this window and return to the application.</p>
                </body>
                </html>
            """)
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"""
                <html>
                <body>
                    <h1>Authorization Failed!</h1>
                    <p>No authorization code received.</p>
                </body>
                </html>
            """)

    def log_message(self, format, *args):
        """Suppress default logging"""
        pass


class MyUplinkAuth:
    """Handle myUplink OAuth2 authentication"""

    def __init__(self):
        self.client_id = CLIENT_ID
        self.client_secret = CLIENT_SECRET
        self.redirect_uri = REDIRECT_URI
        self.auth_url = AUTH_URL
        self.token_url = TOKEN_URL
        self.tokens_file = TOKENS_FILE
        self.tokens = None

        if not self.client_id or not self.client_secret:
            raise ValueError(
                "Missing CLIENT_ID or CLIENT_SECRET. "
                "Please set them in .env file or environment variables."
            )

    def get_authorization_url(self):
        """Generate the authorization URL"""
        oauth = OAuth2Session(
            self.client_id,
            redirect_uri=self.redirect_uri,
            scope=['READSYSTEM', 'WRITESYSTEM', 'offline_access']
        )
        authorization_url, state = oauth.authorization_url(self.auth_url)
        return authorization_url, state

    def start_local_server(self, port=8080):
        """Start local server to receive OAuth callback"""
        server = HTTPServer(('localhost', port), OAuthCallbackHandler)
        logger.info(f"Starting local server on port {port}...")
        server.handle_request()  # Handle one request then stop
        return OAuthCallbackHandler.authorization_code

    def exchange_code_for_token(self, authorization_code):
        """Exchange authorization code for access token"""
        import time

        data = {
            'grant_type': 'authorization_code',
            'code': authorization_code,
            'redirect_uri': self.redirect_uri,
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }

        response = requests.post(self.token_url, data=data)
        response.raise_for_status()

        self.tokens = response.json()

        # Add expiration timestamp
        if 'expires_in' in self.tokens:
            self.tokens['expires_at'] = time.time() + self.tokens['expires_in']

        self.save_tokens()
        logger.info("Successfully obtained access token")
        return self.tokens

    def refresh_access_token(self):
        """Refresh the access token using refresh token"""
        import time

        if not self.tokens or 'refresh_token' not in self.tokens:
            raise ValueError("No refresh token available")

        # Keep the old refresh_token in case the new response doesn't include it
        old_refresh_token = self.tokens['refresh_token']

        data = {
            'grant_type': 'refresh_token',
            'refresh_token': old_refresh_token,
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }

        response = requests.post(self.token_url, data=data)
        response.raise_for_status()

        self.tokens = response.json()

        # Some OAuth implementations don't return a new refresh_token
        # In that case, keep the old one
        if 'refresh_token' not in self.tokens:
            self.tokens['refresh_token'] = old_refresh_token

        # Add expiration timestamp
        if 'expires_in' in self.tokens:
            self.tokens['expires_at'] = time.time() + self.tokens['expires_in']

        self.save_tokens()
        logger.info("Successfully refreshed access token")
        return self.tokens

    def save_tokens(self):
        """Save tokens to file"""
        with open(self.tokens_file, 'w') as f:
            json.dump(self.tokens, f, indent=2)
        logger.info(f"Tokens saved to {self.tokens_file}")

    def load_tokens(self):
        """Load tokens from file"""
        if self.tokens_file.exists():
            with open(self.tokens_file, 'r') as f:
                self.tokens = json.load(f)
            logger.info(f"Tokens loaded from {self.tokens_file}")
            return self.tokens
        return None

    def get_access_token(self):
        """Get valid access token (refresh if needed)"""
        import time

        if not self.tokens:
            self.load_tokens()

        if not self.tokens:
            raise ValueError("No tokens available. Please authenticate first.")

        # Check if token is expired or about to expire (within 5 minutes)
        if 'expires_at' in self.tokens:
            expires_at = self.tokens['expires_at']
            current_time = time.time()

            # Refresh if token expires within 5 minutes
            if current_time >= (expires_at - 300):
                logger.info("Access token expiring soon, refreshing...")
                try:
                    self.refresh_access_token()
                except Exception as e:
                    logger.error(f"Failed to refresh token: {e}")
                    raise ValueError(
                        "Token refresh failed. Please re-authenticate with: python src/auth.py"
                    )

        return self.tokens.get('access_token')

    def authenticate(self):
        """Full authentication flow"""
        # Check if we have saved tokens
        if self.load_tokens():
            logger.info("Found saved tokens. Attempting to refresh...")
            try:
                self.refresh_access_token()
                return self.tokens
            except Exception as e:
                logger.warning(f"Failed to refresh token: {e}")
                logger.info("Starting new authentication flow...")

        # Start new authentication flow
        auth_url, state = self.get_authorization_url()

        logger.info("Opening browser for authentication...")
        logger.info(f"Authorization URL: {auth_url}")
        webbrowser.open(auth_url)

        # Start local server to receive callback
        authorization_code = self.start_local_server()

        if not authorization_code:
            raise ValueError("Failed to receive authorization code")

        # Exchange code for token
        return self.exchange_code_for_token(authorization_code)


def main():
    """Test the authentication flow"""
    logger.info("Starting myUplink authentication test...")

    try:
        auth = MyUplinkAuth()
        tokens = auth.authenticate()

        logger.info("Authentication successful!")
        logger.info(f"Access token: {tokens['access_token'][:20]}...")
        logger.info(f"Token type: {tokens.get('token_type')}")
        logger.info(f"Expires in: {tokens.get('expires_in')} seconds")

        return tokens

    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        raise


if __name__ == '__main__':
    main()
