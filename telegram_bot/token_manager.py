"""
Token Manager
Handles Upstox token validation and refresh
"""
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from core_logic.logger_config import get_logger

logger = get_logger()

class TokenManager:
    def __init__(self):
        self.env_path = Path(__file__).parent.parent / ".env"
        self.token_check_url = "https://api.upstox.com/v2/user/profile"
    
    def read_env(self):
        """Read .env file and return as dictionary"""
        env_vars = {}
        if self.env_path.exists():
            with open(self.env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env_vars[key.strip()] = value.strip()
        return env_vars
    
    def check_token_validity(self):
        """
        Check if current Upstox access token is valid
        
        Returns:
            tuple: (is_valid: bool, message: str)
        """
        env_vars = self.read_env()
        access_token = env_vars.get('UPSTOX_ACCESS_TOKEN')
        
        if not access_token:
            return False, "No access token found in .env file"
        
        try:
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Accept': 'application/json'
            }
            
            response = requests.get(self.token_check_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    user_name = data.get('data', {}).get('user_name', 'Unknown')
                    return True, f"Token valid for user: {user_name}"
            
            elif response.status_code == 401:
                return False, "Token expired or invalid (401 Unauthorized)"
            
            else:
                return False, f"Token check failed with status {response.status_code}"
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Token validation error: {e}")
            return False, f"Network error during token check: {str(e)}"
        except Exception as e:
            logger.error(f"Unexpected error during token validation: {e}")
            return False, f"Error checking token: {str(e)}"
    
    def get_authorization_url(self):
        """
        Generate Upstox authorization URL for user to open in their browser
        
        Returns:
            str: Authorization URL
        """
        env_vars = self.read_env()
        client_id = env_vars.get('UPSTOX_CLIENT_ID')
        redirect_uri = env_vars.get('UPSTOX_REDIRECT_URI')
        
        if not client_id or not redirect_uri:
            return None
        
        auth_url = (
            "https://api.upstox.com/v2/login/authorization/dialog"
            f"?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}"
        )
        
        return auth_url
    
    def exchange_code_for_token(self, auth_code):
        """
        Exchange authorization code for access token
        
        Args:
            auth_code: Authorization code from Upstox redirect
        
        Returns:
            tuple: (success: bool, message: str, token: str or None)
        """
        env_vars = self.read_env()
        client_id = env_vars.get('UPSTOX_CLIENT_ID')
        client_secret = env_vars.get('UPSTOX_CLIENT_SECRET')
        redirect_uri = env_vars.get('UPSTOX_REDIRECT_URI')
        
        if not all([client_id, client_secret, redirect_uri]):
            return False, "Missing credentials in .env file", None
        
        token_url = "https://api.upstox.com/v2/login/authorization/token"
        payload = {
            "code": auth_code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        
        try:
            response = requests.post(token_url, data=payload, timeout=10)
            
            if response.status_code != 200:
                return False, f"Token exchange failed: {response.text}", None
            
            data = response.json()
            access_token = data.get("access_token")
            
            if not access_token:
                return False, "No access token in response", None
            
            # Update .env file
            self.update_env_token(access_token)
            
            return True, "Token updated successfully!", access_token
        
        except Exception as e:
            logger.error(f"Token exchange error: {e}")
            return False, f"Error: {str(e)}", None
    
    def update_env_token(self, token):
        """Update UPSTOX_ACCESS_TOKEN in .env file"""
        lines = []
        with open(self.env_path, "r") as f:
            lines = f.readlines()

        with open(self.env_path, "w") as f:
            for line in lines:
                if line.startswith("UPSTOX_ACCESS_TOKEN="):
                    f.write(f"UPSTOX_ACCESS_TOKEN={token}\n")
                else:
                    f.write(line)
        
        logger.info("Access token updated in .env file")
    
    def trigger_token_refresh_script(self):
        """
        Trigger the auto_fetch_token.py script
        Note: This requires manual intervention (OTP + browser)
        
        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            script_path = self.env_path.parent / "auto_fetch_token.py"
            
            if not script_path.exists():
                return False, "auto_fetch_token.py script not found"
            
            # Start the token refresh script as a subprocess
            # Note: This will require manual browser interaction
            import subprocess
            subprocess.Popen([sys.executable, str(script_path)])
            
            return True, "Token refresh script started. Please complete the browser authentication."
        
        except Exception as e:
            logger.error(f"Failed to start token refresh script: {e}")
            return False, f"Error starting refresh script: {str(e)}"
    
    def get_token_info(self):
        """
        Get detailed information about the current token
        
        Returns:
            dict: Token information
        """
        is_valid, message = self.check_token_validity()
        env_vars = self.read_env()
        
        return {
            'is_valid': is_valid,
            'message': message,
            'has_token': bool(env_vars.get('UPSTOX_ACCESS_TOKEN')),
            'checked_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

# Global instance
_token_manager = None

def get_token_manager() -> TokenManager:
    """Get or create global TokenManager instance"""
    global _token_manager
    if _token_manager is None:
        _token_manager = TokenManager()
    return _token_manager
