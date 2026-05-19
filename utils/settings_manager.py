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
        """Test FME connection by checking if the executable exists and can be run"""
        try:
            path_to_test = fme_path or self.settings['fme']['executable_path']
            if not path_to_test:
                return False, "FME path not configured"

            if not os.path.exists(path_to_test):
                return False, "FME executable not found at specified path"

            # Try to run FME with --version flag
            result = subprocess.run([path_to_test, '--version'], 
                                 capture_output=True, 
                                 text=True)
            
            if result.returncode == 0:
                return True, "FME connection successful"
            else:
                return False, f"Error running FME: {result.stderr}"

        except Exception as e:
            return False, f"Error testing FME connection: {str(e)}"

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