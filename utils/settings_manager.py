import json
import os
from datetime import datetime
from pathlib import Path
import subprocess
import imaplib

class SettingsManager:
    def __init__(self):
        self.config_dir = Path(__file__).parent.parent / 'config'
        self.settings_file = self.config_dir / 'settings.json'
        self._ensure_config_dir()
        self.settings = self._load_settings()

    def _ensure_config_dir(self):
        """Ensure the config directory exists"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        if not self.settings_file.exists():
            self._create_default_settings()

    def _create_default_settings(self):
        """Create default settings file if it doesn't exist"""
        default_settings = {
            "fme": {
                "executable_path": ""
            },
            "email": {
                "username": "",
                "password": "",
                "server": "outlook.office365.com",
                "port": 993
            },
            "paths": {
                "log_directory": "logs",
                "download_directory": "data/downloads",
                "extract_directory": "data/extract"
            },
            "last_updated": None
        }
        self._save_settings(default_settings)

    def _load_settings(self):
        """Load settings from file"""
        try:
            with open(self.settings_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading settings: {e}")
            return self._create_default_settings()

    def _save_settings(self, settings):
        """Save settings to file"""
        try:
            settings['last_updated'] = datetime.now().isoformat()
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f, indent=4)
            self.settings = settings
            return True
        except Exception as e:
            print(f"Error saving settings: {e}")
            return False

    def get_settings(self):
        """Get current settings"""
        return self.settings

    def update_settings(self, new_settings):
        """Update settings with new values"""
        try:
            # Merge new settings with existing ones
            current = self.settings.copy()
            
            # Update FME settings
            if 'fme' in new_settings:
                current['fme'].update(new_settings['fme'])
            
            # Update email settings
            if 'email' in new_settings:
                current['email'].update(new_settings['email'])
            
            # Update paths
            if 'paths' in new_settings:
                current['paths'].update(new_settings['paths'])

            return self._save_settings(current)
        except Exception as e:
            print(f"Error updating settings: {e}")
            return False

    def test_fme_connection(self, fme_path=None):
        """Test the configured FME executable by running it with --version.

        SECURITY (audit C-2): the path comes from server-side configuration
        only — either the explicit `M1_FME_EXE` env var or the persisted
        settings.json. Any caller-supplied `fme_path` argument is IGNORED
        unless it matches one of those, because the previous behavior
        (running an arbitrary path passed in via the HTTP API) was a
        network-reachable arbitrary-code-execution primitive.
        """
        try:
            configured_path = (
                os.getenv("M1_FME_EXE", "").strip()
                or self.settings.get("fme", {}).get("executable_path", "")
            )
            if not configured_path:
                return False, "FME path not configured on the server (set M1_FME_EXE)."

            # If a caller passed a path, only accept it if it matches the
            # server's configured value. This blocks arbitrary-binary
            # execution via the /api/settings/test endpoint.
            if fme_path is not None and fme_path != configured_path:
                return False, (
                    "Refusing to test a caller-supplied FME path. Only the "
                    "server-configured M1_FME_EXE may be tested."
                )

            if not os.path.exists(configured_path):
                return False, "FME executable not found at the configured path."

            # Sanity check: the configured path should look like an FME
            # executable. Trivial guard but useful when M1_FME_EXE is mis-set.
            basename = os.path.basename(configured_path).lower()
            if not basename.startswith("fme"):
                return False, (
                    "Configured M1_FME_EXE does not look like an FME "
                    "executable (basename must start with 'fme')."
                )

            result = subprocess.run(
                [configured_path, "--version"],
                capture_output=True,
                text=True,
                timeout=15,
            )

            if result.returncode == 0:
                return True, "FME connection successful."
            return False, f"Error running FME: {result.stderr.strip()}"

        except subprocess.TimeoutExpired:
            return False, "FME --version timed out."
        except Exception as e:
            return False, f"Error testing FME connection: {e}"

    def test_email_connection(self, credentials=None):
        """Test email connection using provided or stored credentials"""
        try:
            username = credentials['username'] if credentials else self.settings['email']['username']
            password = credentials['password'] if credentials else self.settings['email']['password']
            server = self.settings['email']['server']
            port = self.settings['email']['port']

            if not username or not password:
                return False, "Email credentials not configured"

            # Try to connect to the email server
            imap = imaplib.IMAP4_SSL(server, port)
            imap.login(username, password)
            imap.logout()
            
            return True, "Email connection successful"

        except Exception as e:
            return False, f"Error testing email connection: {str(e)}"

    def validate_paths(self, paths=None):
        """Validate and create directories if they don't exist"""
        try:
            paths_to_check = paths or self.settings['paths']
            
            for key, path in paths_to_check.items():
                # Create directory if it doesn't exist
                Path(path).mkdir(parents=True, exist_ok=True)
            
            return True, "Directories validated and created if needed"
        except Exception as e:
            return False, f"Error validating paths: {str(e)}"