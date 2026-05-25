from flask import Flask, render_template, jsonify, request, Response, send_from_directory
from flask_cors import CORS
import json
import threading
import time
from datetime import datetime
from pathlib import Path
import logging
from queue import Queue
import sys
import os
import requests
from requests.auth import HTTPBasicAuth
import pandas as pd
import glob
import math

# Import your existing modules
from email_monitor import check_email_for_download_url
from download_extract import download_data, extract_data, setup_directories, clean_existing_data
from config import get_download_url, save_download_url, get_download_info, BASE_DIR
from utils.settings_manager import SettingsManager
from utils.auth import register_auth
import fme_runner
import pozi_runner

app = Flask(__name__)

# CORS: pass the allowed origins via the ALLOWED_ORIGINS env var (comma-
# separated). Leave it unset on localhost-only deployments to disable CORS
# entirely. Was previously wildcarded (security audit H-1).
_allowed = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if _allowed:
    CORS(app, origins=_allowed)

# Bearer-token authentication on /api/* routes. Set API_TOKEN in .env to
# enable; leave empty to keep the legacy wide-open behavior (a warning is
# logged at startup). Security audit C-1.
register_auth(app)

# Initialize settings manager
settings_manager = SettingsManager()

# Geocortex / Pozi viewer credentials from environment.
# GEOCORTEX_URL must be set in .env for production use (no default — adopters
# point this at their council's Geocortex / Pozi instance).
GEOCORTEX_URL = os.getenv("GEOCORTEX_URL", "")
GEOCORTEX_USER = os.getenv("GEOCORTEX_USER", os.getenv("EMAIL_USER", ""))
GEOCORTEX_PASS = os.getenv("GEOCORTEX_PASS", os.getenv("EMAIL_PASS", ""))

# Global state
app_state = {
    'status': 'idle',
    'current_step': None,
    'progress': 0,
    'email_monitoring': False,
    'last_email_check': None,
    'download_available': False,
    'fme_ready': False,
    'pozi_ready': False,
    'ai_validation_ready': True,  # Always available - can validate any M1 file
    'ai_validation_completed': False,
    'log_messages': []
}

# Global variables for preview data
preview_data = {
    'pozi_data': None,
    'validation_results': None
}

# Validation API URL (for proxy endpoints and status checking)
VALIDATION_API_URL = os.getenv('VALIDATION_API_URL', 'http://localhost:5001')

def clean_for_json(obj):
    """Recursively clean data structure to ensure JSON serialization"""
    if isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_for_json(item) for item in obj]
    elif isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    elif pd.isna(obj):
        return None
    else:
        return obj

# Log queue for real-time updates
log_queue = Queue()

class WebLogHandler(logging.Handler):
    """Custom logging handler that captures logs for web display."""
    def emit(self, record):
        # Filter out noisy logs
        message = self.format(record)
        
        # Skip status check logs and other noise
        if any(skip in message for skip in [
            'GET /api/status',
            'GET /api/logs/stream',
            '* Debugger is active',
            '* Debugger PIN'
        ]):
            return
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'level': record.levelname,
            'message': message
        }
        log_queue.put(log_entry)
        app_state['log_messages'].append(log_entry)
        # Keep only last 1000 messages
        if len(app_state['log_messages']) > 1000:
            app_state['log_messages'] = app_state['log_messages'][-1000:]

# Setup logging
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Add web handler
    web_handler = WebLogHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    web_handler.setFormatter(formatter)
    logger.addHandler(web_handler)

setup_logging()
logger = logging.getLogger(__name__)

@app.route('/')
def index():
    """Serve the main UI."""
    return render_template('index.html')

@app.route('/static/logo.png')
def serve_logo():
    """Serve the logo file."""
    import os
    
    # Try multiple locations
    logo_paths = [
        BASE_DIR / 'templates' / 'logo.png',
        BASE_DIR / 'logo.png',
        BASE_DIR / 'static' / 'logo.png'
    ]
    
    for logo_path in logo_paths:
        if logo_path.exists():
            try:
                return send_from_directory(logo_path.parent, logo_path.name)
            except Exception as e:
                print(f"Error serving logo: {e}")
                continue
    
    # If no logo found, return 404
    return "Logo not found", 404

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve other static files."""
    # Skip logo.png as it has its own route
    if filename == 'logo.png':
        return serve_logo()
    
    # Try to find the file
    for directory in [BASE_DIR / 'templates', BASE_DIR / 'static', BASE_DIR]:
        filepath = directory / filename
        if filepath.exists():
            return send_from_directory(directory, filename)
    
    return "File not found", 404

@app.route('/api/status')
def get_status():
    """Get current application status."""
    # Add download info if available
    download_info = get_download_info()
    if download_info and download_info.get('url'):
        app_state['download_available'] = True
        app_state['download_info'] = {
            'available': True,
            'email_date': download_info.get('email_date'),
            'last_updated': download_info.get('last_updated')
        }
    else:
        app_state['download_available'] = False
        app_state['download_info'] = {'available': False}
    
    # Check AI validation status from validation API
    try:
        import requests
        validation_status_response = requests.get(
            f'{VALIDATION_API_URL}/api/validation-status',
            timeout=2
        )
        if validation_status_response.status_code == 200:
            validation_status = validation_status_response.json()
            if validation_status.get('is_running'):
                app_state['status'] = 'ai_validation'
                app_state['current_step'] = validation_status.get('current_operation', 'AI Validation in progress...')
                app_state['progress'] = validation_status.get('progress', 0)
                app_state['ai_validation_running'] = True
            else:
                app_state['ai_validation_running'] = False
                if validation_status.get('results'):
                    app_state['ai_validation_completed'] = True
        else:
            app_state['ai_validation_running'] = False
    except Exception as e:
        # Validation API not running or not accessible - that's okay
        app_state['ai_validation_running'] = False
    
    return jsonify(app_state)

@app.route('/api/logs/stream')
def stream_logs():
    """Stream logs in real-time using Server-Sent Events."""
    def generate():
        try:
            while True:
                try:
                    # Try to get a log entry
                    log_entry = log_queue.get(timeout=30)
                    yield f"data: {json.dumps(log_entry)}\n\n"
                except Exception:
                    # Send keepalive
                    yield ": keepalive\n\n"
        except:
            # Silently handle any disconnect
            return
    
    response = Response(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response

@app.route('/api/logs/add', methods=['POST'])
def add_log_entry():
    """Add a log entry to the log queue (used by validation API)"""
    try:
        log_entry = request.get_json()
        if log_entry:
            # Validate log entry structure
            if 'message' in log_entry and 'level' in log_entry:
                # Add timestamp if not present
                if 'timestamp' not in log_entry:
                    log_entry['timestamp'] = datetime.now().isoformat()
                
                # Log to console for debugging (with full details)
                logger.info(f"✓ Received log from validation API:")
                logger.info(f"  Level: {log_entry.get('level')}")
                logger.info(f"  Message: {log_entry.get('message')}")
                logger.info(f"  Timestamp: {log_entry.get('timestamp')}")
                
                # Put in queue for streaming
                log_queue.put(log_entry)
                
                # Also add to stored messages
                app_state['log_messages'].append(log_entry)
                # Keep only last 1000 messages
                if len(app_state['log_messages']) > 1000:
                    app_state['log_messages'] = app_state['log_messages'][-1000:]
                
                logger.info(f"  ✓ Log added to queue (queue size: {log_queue.qsize()}, stored: {len(app_state['log_messages'])})")
                
                return jsonify({
                    'success': True,
                    'queue_size': log_queue.qsize(),
                    'stored_count': len(app_state['log_messages']),
                    'received_message': log_entry.get('message', '')[:100]
                }), 200
        logger.warning(f"Invalid log entry received: {log_entry}")
        return jsonify({'error': 'Invalid log entry', 'received': log_entry}), 400
    except Exception as e:
        logger.error(f"Error adding log entry: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/logs/test', methods=['GET'])
def test_logs():
    """Test endpoint to check log system"""
    return jsonify({
        'queue_size': log_queue.qsize(),
        'stored_messages_count': len(app_state['log_messages']),
        'last_10_messages': app_state['log_messages'][-10:],
        'validation_logs_count': len([m for m in app_state['log_messages'] if '[AI Validation]' in m.get('message', '')])
    })

@app.route('/api/email/check', methods=['POST'])
def check_email():
    """Check for new emails."""
    try:
        app_state['status'] = 'checking_email'
        logger.info("Checking for new emails...")
        
        result = check_email_for_download_url()
        
        if result:
            url, email_date = result
            
            # Check if this is newer than saved
            existing_info = get_download_info()
            if existing_info and existing_info.get('email_date'):
                existing_date = datetime.fromisoformat(existing_info['email_date'])
                email_date_compare = email_date.replace(tzinfo=None) if email_date.tzinfo else email_date
                existing_date_compare = existing_date.replace(tzinfo=None) if existing_date.tzinfo else existing_date
                
                if email_date_compare <= existing_date_compare:
                    logger.info(f"Email found but not newer than saved ({email_date} vs {existing_date})")
                    app_state['status'] = 'idle'
                    # Still mark as available since we have data
                    app_state['download_available'] = True
                    return jsonify({
                        'success': True,
                        'new_data': False,
                        'message': 'No new data available - you already have the latest'
                    })
            
            # Save the new URL
            save_download_url(url, email_date)
            app_state['download_available'] = True
            app_state['last_email_check'] = datetime.now().isoformat()
            app_state['status'] = 'idle'
            
            logger.info(f"New data available from email dated {email_date}")
            return jsonify({
                'success': True,
                'new_data': True,
                'email_date': email_date.isoformat(),
                'message': f'New data available from {email_date.strftime("%Y-%m-%d %H:%M")}'
            })
        else:
            # Check if we already have a saved URL
            existing_info = get_download_info()
            if existing_info and existing_info.get('url'):
                app_state['download_available'] = True
                logger.info("No new emails, but existing download URL available")
                return jsonify({
                    'success': True,
                    'new_data': False,
                    'message': 'No new emails found, but you have a saved download URL'
                })
            
            app_state['status'] = 'idle'
            logger.warning("No emails found with download URLs")
            return jsonify({
                'success': True,
                'new_data': False,
                'message': 'No new emails found'
            })
            
    except Exception as e:
        app_state['status'] = 'error'
        logger.error(f"Error checking email: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download_and_extract():
    """Download and extract data."""
    def process():
        try:
            app_state['status'] = 'downloading'
            app_state['progress'] = 0
            logger.info("Starting download and extraction...")
            
            url = get_download_url()
            if not url:
                raise ValueError("No download URL available")
            
            # Setup directories
            setup_directories()
            app_state['progress'] = 10
            
            # Clean existing data
            clean_existing_data()
            app_state['progress'] = 20
            
            # Download
            logger.info("Downloading data...")
            zip_path = download_data(url)
            app_state['progress'] = 60
            
            # Extract
            logger.info("Extracting data...")
            extract_data(zip_path)
            app_state['progress'] = 100
            
            app_state['status'] = 'idle'
            app_state['fme_ready'] = True
            logger.info("Download and extraction completed successfully")
            
        except Exception as e:
            app_state['status'] = 'error'
            logger.error(f"Download error: {e}")
    
    thread = threading.Thread(target=process)
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'message': 'Download started'})

@app.route('/api/fme/run', methods=['POST'])
def run_fme():
    """Run FME processing."""
    def process():
        try:
            app_state['status'] = 'fme_processing'
            app_state['progress'] = 0
            logger.info("Starting FME processing...")
            
            # Verify FME installation
            fme_runner.verify_fme_installation()
            app_state['progress'] = 10
            
            # Run FME
            result = fme_runner.run_fme(test_mode=False)
            
            if result.returncode == 0:
                app_state['status'] = 'idle'
                app_state['progress'] = 100
                app_state['pozi_ready'] = True
                logger.info("FME processing completed successfully")
            else:
                raise RuntimeError(f"FME processing failed with code {result.returncode}")
                
        except Exception as e:
            app_state['status'] = 'error'
            logger.error(f"FME processing error: {e}")
    
    thread = threading.Thread(target=process)
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'message': 'FME processing started'})

@app.route('/api/pozi/run', methods=['POST'])
def run_pozi():
    """Run Pozi Connect tasks."""
    def process():
        try:
            app_state['status'] = 'pozi_processing'
            app_state['progress'] = 0
            logger.info("Starting Pozi Connect tasks...")
            
            # Verify Pozi installation
            pozi_runner.verify_pozi_installation()
            app_state['progress'] = 10
            
            # Run Pozi tasks
            result = pozi_runner.run_pozi_tasks()
            
            if result.returncode == 0:
                app_state['status'] = 'completed'
                app_state['progress'] = 100
                
                # Find generated M1 file
                m1_file = pozi_runner.find_generated_m1_file()
                if m1_file:
                    app_state['m1_file'] = str(m1_file)
                    logger.info(f"M1 file generated: {m1_file}")
                
                logger.info("Pozi Connect tasks completed successfully")
            else:
                raise RuntimeError(f"Pozi Connect failed with code {result.returncode}")
                
        except Exception as e:
            app_state['status'] = 'error'
            logger.error(f"Pozi Connect error: {e}")
    
    thread = threading.Thread(target=process)
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'message': 'Pozi Connect tasks started'})

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get current settings."""
    try:
        settings = settings_manager.get_settings()
        # Remove sensitive information
        if 'email' in settings:
            settings['email'] = {k: ('*' * 8 if k in ['password'] else v) 
                               for k, v in settings['email'].items()}
        return jsonify({'success': True, 'settings': settings})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Update application settings."""
    try:
        new_settings = request.get_json()
        if not new_settings:
            return jsonify({'success': False, 'error': 'No settings provided'}), 400
        
        success = settings_manager.update_settings(new_settings)
        if success:
            return jsonify({'success': True, 'message': 'Settings updated successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to update settings'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/settings/test', methods=['POST'])
def test_settings():
    """Test settings connections (FME and email)."""
    try:
        settings = request.get_json()
        results = {}
        
        # Test FME if path provided
        if settings.get('fme', {}).get('executable_path'):
            fme_success, fme_message = settings_manager.test_fme_connection(
                settings['fme']['executable_path']
            )
            results['fme'] = {'success': fme_success, 'message': fme_message}
        
        # Test email if credentials provided
        if settings.get('email', {}).get('username') and settings.get('email', {}).get('password'):
            email_success, email_message = settings_manager.test_email_connection({
                'username': settings['email']['username'],
                'password': settings['email']['password']
            })
            results['email'] = {'success': email_success, 'message': email_message}
        
        # Test paths if provided
        if settings.get('paths'):
            paths_success, paths_message = settings_manager.validate_paths(settings['paths'])
            results['paths'] = {'success': paths_success, 'message': paths_message}
        
        return jsonify({'success': True, 'results': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/run-all', methods=['POST'])
def run_all():
    """Run the complete workflow."""
    def process():
        try:
            # Step 1: Check email
            app_state['status'] = 'checking_email'
            app_state['current_step'] = 'Checking for new data'
            app_state['progress'] = 0
            logger.info("="*70)
            logger.info("STARTING COMPLETE WORKFLOW")
            logger.info("="*70)
            
            result = check_email_for_download_url()
            if result:
                url, email_date = result
                save_download_url(url, email_date)
                logger.info(f"✓ Email check complete - data from {email_date}")
            else:
                logger.info("Using existing download URL")
            
            app_state['progress'] = 10
            
            # Step 2: Download and extract
            app_state['current_step'] = 'Downloading and extracting data'
            app_state['status'] = 'downloading'
            logger.info("\n[STEP 2/4] Downloading and extracting data...")
            
            url = get_download_url()
            if url:
                setup_directories()
                clean_existing_data()
                zip_path = download_data(url)
                extract_data(zip_path)
                logger.info("✓ Download and extraction complete")
            
            app_state['progress'] = 30
            
            # Step 3: FME processing
            app_state['current_step'] = 'Running FME processing'
            app_state['status'] = 'fme_processing'
            logger.info("\n[STEP 3/4] Running FME processing...")
            
            fme_runner.verify_fme_installation()
            fme_result = fme_runner.run_fme(test_mode=False)
            
            if fme_result.returncode != 0:
                raise RuntimeError("FME processing failed")
            
            logger.info("✓ FME processing complete")
            app_state['progress'] = 60
            
            # Step 4: Pozi tasks
            app_state['current_step'] = 'Running Pozi Connect tasks'
            app_state['status'] = 'pozi_processing'
            logger.info("\n[STEP 4/4] Running Pozi Connect tasks...")
            
            pozi_runner.verify_pozi_installation()
            pozi_result = pozi_runner.run_pozi_tasks()
            
            if pozi_result.returncode != 0:
                raise RuntimeError("Pozi Connect failed")
            
            logger.info("✓ Pozi Connect tasks complete")
            
            # Complete
            app_state['progress'] = 100
            app_state['status'] = 'completed'
            app_state['current_step'] = 'All tasks completed successfully!'
            
            # Find M1 file
            m1_file = pozi_runner.find_generated_m1_file()
            if m1_file:
                app_state['m1_file'] = str(m1_file)
                logger.info(f"\n✓ M1 file generated: {m1_file}")
            
            logger.info("\n" + "="*70)
            logger.info("WORKFLOW COMPLETED SUCCESSFULLY")
            logger.info("="*70)
            
        except Exception as e:
            app_state['status'] = 'error'
            app_state['current_step'] = f'Error: {str(e)}'
            logger.error(f"\n✗ Workflow error: {e}")
            logger.error("="*70)
    
    thread = threading.Thread(target=process)
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'message': 'Complete workflow started'})

# Historical Reports Endpoints
@app.route('/api/reports/list', methods=['GET'])
def list_historical_reports():
    """List all available historical reports"""
    try:
        # Get the project root directory (BASE_DIR)
        project_root = BASE_DIR
        logger.info(f"Project root directory: {project_root}")
        
        # Change to project root directory for file discovery
        original_cwd = os.getcwd()
        os.chdir(project_root)
        
        try:
            # Find POZI reports
            pozi_files = glob.glob('**/*pozi*.csv', recursive=True)
            pozi_files.extend(glob.glob('**/*POZI*.csv', recursive=True))
            
            # Find validation reports
            validation_files = glob.glob('**/*validation*results*.csv', recursive=True)
            validation_files.extend(glob.glob('**/*validation*report*.json', recursive=True))
            
            # Also check specific known locations
            known_pozi_files = [
                os.getenv("SAMPLE_M1_CSV", "tests/fixtures/sample_m1.csv")
            ]
            
            known_validation_files = [
                'smart_openai_validation_results.csv',
                'openai_validation_results.csv',
                'ai_intelligent_validation_results.csv',
                'pozi_validation_results.csv',
                'smart_openai_validation_report.json',
                'openai_validation_report.json',
                'ai_intelligent_validation_report.json'
            ]
            
            # Add known files if they exist
            for file_path in known_pozi_files:
                if os.path.exists(file_path) and file_path not in pozi_files:
                    pozi_files.append(file_path)
            
            for file_path in known_validation_files:
                if os.path.exists(file_path) and file_path not in validation_files:
                    validation_files.append(file_path)
                    
        finally:
            # Restore original working directory
            os.chdir(original_cwd)
        
        reports = {
            'pozi_reports': [],
            'validation_reports': []
        }
        
        # Normalize paths and remove duplicates
        seen_paths = set()
        
        # Process POZI reports
        for file_path in pozi_files:
            try:
                # Normalize path to handle Windows/Unix differences
                normalized_path = os.path.normpath(file_path)
                normalized_key = normalized_path.lower()
                
                # Skip duplicates and exclude pozi_validation_results.csv (it's a validation report)
                if normalized_key in seen_paths or 'pozi_validation_results.csv' in file_path.lower():
                    continue
                
                seen_paths.add(normalized_key)
                
                # Only process if file exists
                if os.path.exists(normalized_path):
                    file_stat = os.stat(normalized_path)
                    reports['pozi_reports'].append({
                        'filename': os.path.basename(normalized_path),
                        'path': normalized_path,
                        'size': file_stat.st_size,
                        'modified': file_stat.st_mtime,
                        'type': 'pozi'
                    })
            except Exception as e:
                logger.warning(f"Could not process POZI file {file_path}: {e}")
        
        # Reset seen_paths for validation reports
        seen_paths = set()
        
        # Process validation reports
        for file_path in validation_files:
            try:
                # Normalize path to handle Windows/Unix differences
                normalized_path = os.path.normpath(file_path)
                normalized_key = normalized_path.lower()
                
                # Skip duplicates
                if normalized_key in seen_paths:
                    continue
                
                seen_paths.add(normalized_key)
                
                # Only process if file exists
                if os.path.exists(normalized_path):
                    file_stat = os.stat(normalized_path)
                    file_type = 'csv' if normalized_path.endswith('.csv') else 'json'
                    reports['validation_reports'].append({
                        'filename': os.path.basename(normalized_path),
                        'path': normalized_path,
                        'size': file_stat.st_size,
                        'modified': file_stat.st_mtime,
                        'type': file_type
                    })
            except Exception as e:
                logger.warning(f"Could not process validation file {file_path}: {e}")
        
        # Sort by modification time (newest first)
        reports['pozi_reports'].sort(key=lambda x: x['modified'], reverse=True)
        reports['validation_reports'].sort(key=lambda x: x['modified'], reverse=True)
        
        return jsonify(reports)
        
    except Exception as e:
        logger.error(f"Error listing historical reports: {str(e)}")
        return jsonify({'error': f'Error listing reports: {str(e)}'}), 500

@app.route('/api/reports/load/pozi', methods=['POST'])
def load_historical_pozi():
    """Load historical POZI report"""
    global preview_data
    
    try:
        data = request.get_json()
        if not data or 'file_path' not in data:
            return jsonify({'error': 'File path required'}), 400
        
        file_path = data['file_path']
        
        # Normalize the path to handle Windows/Unix differences
        file_path = os.path.normpath(file_path)
        
        # If path is relative, make it relative to project root
        if not os.path.isabs(file_path):
            file_path = os.path.join(BASE_DIR, file_path)
            file_path = os.path.normpath(file_path)
        
        logger.info(f"Loading POZI file: {file_path}")
        
        # Check if file exists
        if not os.path.exists(file_path):
            return jsonify({'error': f'File not found: {file_path}'}), 404
        
        # Load CSV file with proper handling of quotes and special characters
        df = pd.read_csv(file_path, 
                        quotechar='"', 
                        escapechar='\\',
                        na_values=['', 'NULL', 'null'],
                        keep_default_na=True)
        
        # Convert to JSON string first (handles NaN and special characters properly)
        # pandas to_json() automatically converts NaN to null in JSON
        # Then parse back to ensure valid JSON structure
        json_str = df.to_json(orient='records', date_format='iso', default_handler=str)
        parsed_data = json.loads(json_str)
        
        # Clean any remaining NaN/inf values recursively
        cleaned_data = clean_for_json(parsed_data)
        preview_data['pozi_data'] = cleaned_data
        
        # Do the same for sample data
        sample_json_str = df.head(10).to_json(orient='records', date_format='iso', default_handler=str)
        sample_data = json.loads(sample_json_str)
        cleaned_sample = clean_for_json(sample_data)
        
        # Return preview data
        preview_info = {
            'filename': os.path.basename(file_path),
            'total_rows': len(df),
            'total_columns': len(df.columns),
            'columns': list(df.columns),
            'sample_data': cleaned_sample,
            'data_types': df.dtypes.astype(str).to_dict(),
            'source': 'historical'
        }
        
        logger.info(f"Historical POZI report loaded: {os.path.basename(file_path)}, {len(df)} rows, {len(df.columns)} columns")
        return jsonify(preview_info)
        
    except Exception as e:
        logger.error(f"Error loading historical POZI report: {str(e)}")
        return jsonify({'error': f'Error loading report: {str(e)}'}), 500

@app.route('/api/reports/load/validation', methods=['POST'])
def load_historical_validation():
    """Load historical validation report"""
    global preview_data
    
    try:
        data = request.get_json()
        if not data or 'file_path' not in data:
            return jsonify({'error': 'File path required'}), 400
        
        file_path = data['file_path']
        
        # Normalize the path to handle Windows/Unix differences
        file_path = os.path.normpath(file_path)
        
        # If path is relative, make it relative to project root
        if not os.path.isabs(file_path):
            file_path = os.path.join(BASE_DIR, file_path)
            file_path = os.path.normpath(file_path)
        
        logger.info(f"Loading validation file: {file_path}")
        
        # Check if file exists
        if not os.path.exists(file_path):
            return jsonify({'error': f'File not found: {file_path}'}), 404
        
        # Load data based on file type
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
            # Replace NaN with None for JSON serialization
            df = df.where(pd.notnull(df), None)
            validation_data = df.to_dict('records')
        elif file_path.endswith('.json'):
            with open(file_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
                # Extract validation results from JSON
                if 'validation_results' in json_data:
                    validation_data = json_data['validation_results']
                else:
                    validation_data = json_data
        else:
            return jsonify({'error': 'Unsupported file type'}), 400
        
        preview_data['validation_results'] = validation_data
        
        # Calculate summary statistics
        total_rows = len(validation_data)
        kept_count = sum(1 for row in validation_data if row.get('decision') == 'KEEP')
        rejected_count = sum(1 for row in validation_data if row.get('decision') == 'REJECT')
        
        # Get unique reasons
        all_reasons = []
        for row in validation_data:
            reasons = row.get('reasons', [])
            if isinstance(reasons, list):
                all_reasons.extend(reasons)
            elif isinstance(reasons, str):
                all_reasons.append(reasons)
        
        unique_reasons = list(set(all_reasons))
        
        preview_info = {
            'filename': os.path.basename(file_path),
            'total_rows': total_rows,
            'kept_count': kept_count,
            'rejected_count': rejected_count,
            'unique_reasons': unique_reasons,
            'sample_data': validation_data[:10],
            'source': 'historical'
        }
        
        logger.info(f"Historical validation report loaded: {os.path.basename(file_path)}, {total_rows} rows, {kept_count} kept, {rejected_count} rejected")
        return jsonify(preview_info)
        
    except Exception as e:
        logger.error(f"Error loading historical validation report: {str(e)}")
        return jsonify({'error': f'Error loading report: {str(e)}'}), 500

@app.route('/api/m1-files/list', methods=['GET'])
def list_m1_files():
    """List all available M1 CSV files that can be validated"""
    try:
        project_root = BASE_DIR
        original_cwd = os.getcwd()
        os.chdir(project_root)
        
        try:
            # Find M1/POZI CSV files in project directory
            m1_files = glob.glob('**/*M1*.csv', recursive=True)
            m1_files.extend(glob.glob('**/*pozi*.csv', recursive=True))
            m1_files.extend(glob.glob('**/*POZI*.csv', recursive=True))
            
            # Check POZI output directory (where POZI generates files)
            try:
                from config import POZI_OUTPUT_DIR
                if POZI_OUTPUT_DIR and os.path.exists(POZI_OUTPUT_DIR):
                    pozi_files = list(Path(POZI_OUTPUT_DIR).glob("M1_*.csv"))
                    for pozi_file in pozi_files:
                        file_str = str(pozi_file)
                        if file_str not in m1_files:
                            m1_files.append(file_str)
                    logger.info(f"Found {len(pozi_files)} M1 files in POZI output directory: {POZI_OUTPUT_DIR}")
            except Exception as e:
                logger.warning(f"Could not check POZI output directory: {e}")
            
            # Also check specific known locations
            known_files = [
                os.getenv("SAMPLE_M1_CSV", "tests/fixtures/sample_m1.csv")
            ]
            
            for file_path in known_files:
                if os.path.exists(file_path) and file_path not in m1_files:
                    m1_files.append(file_path)
                    
        finally:
            os.chdir(original_cwd)

        # If the caller asked for a specific directory (e.g. a previous run's
        # output folder), validate from there: override discovery with the M1
        # CSVs found under that directory. Lets users validate prior runs
        # without re-running the full Email->Download->FME->Pozi workflow.
        requested_dir = (request.args.get('directory') or '').strip()
        if requested_dir:
            if not os.path.isdir(requested_dir):
                return jsonify({
                    'error': f'Directory not found: {requested_dir}',
                    'files': [], 'count': 0, 'latest_file': None,
                }), 400
            m1_files = []
            for patt in ('*M1*.csv', '*POZI*.csv', '*pozi*.csv'):
                m1_files.extend(glob.glob(os.path.join(requested_dir, '**', patt), recursive=True))

        files_list = []
        seen_paths = set()
        
        for file_path in m1_files:
            try:
                normalized_path = os.path.normpath(file_path)
                normalized_key = normalized_path.lower()
                
                # Skip duplicates and validation results (they're not input files)
                if normalized_key in seen_paths or 'validation' in normalized_key.lower():
                    continue
                
                seen_paths.add(normalized_key)
                
                if os.path.exists(normalized_path):
                    file_stat = os.stat(normalized_path)
                    files_list.append({
                        'filename': os.path.basename(normalized_path),
                        'path': normalized_path,
                        'size': file_stat.st_size,
                        'modified': file_stat.st_mtime,
                        'display_path': normalized_path.replace('\\', '/')  # For display
                    })
            except Exception as e:
                logger.warning(f"Could not process M1 file {file_path}: {e}")
        
        # Sort by modification time (newest first)
        files_list.sort(key=lambda x: x['modified'], reverse=True)
        
        # Mark the latest file (most recently modified)
        if files_list:
            files_list[0]['is_latest'] = True
            logger.info(f"Latest M1 file: {files_list[0]['filename']} (modified: {datetime.fromtimestamp(files_list[0]['modified']).isoformat()})")
        
        return jsonify({
            'files': files_list,
            'count': len(files_list),
            'latest_file': files_list[0]['path'] if files_list else None
        })
        
    except Exception as e:
        logger.error(f"Error listing M1 files: {str(e)}")
        return jsonify({'error': f'Error listing files: {str(e)}'}), 500

# Initialize app_state with ai_validation fields
app_state.setdefault('ai_validation_running', False)
app_state.setdefault('ai_validation_completed', False)

@app.route('/api/validate-m1', methods=['POST'])
def proxy_validate_m1():
    """Proxy validation request to validation API (non-blocking)"""
    try:
        request_data = request.get_json()
        file_path = request_data.get('file_path', 'Unknown')
        validator_type = request_data.get('validator_type', 'openai')
        
        logger.info(f"🚀 VALIDATION REQUESTED: file={file_path}, validator={validator_type}")
        logger.info(f"   Forwarding to validation API at {VALIDATION_API_URL}/api/validate-m1")
        
        import requests
        # Use longer timeout as Perplexity suggested - validation API needs time to start thread
        response = requests.post(
            f'{VALIDATION_API_URL}/api/validate-m1',
            json=request_data,
            timeout=30  # Perplexity recommendation: longer timeout for reliability
        )
        
        response_data = response.json()
        logger.info(f"✅ VALIDATION API RESPONSE: status={response.status_code}, data={response_data}")
        
        return jsonify(response_data), response.status_code
    except requests.exceptions.Timeout:
        # Timeout is OK - validation is running in background
        logger.warning("⚠️ Validation API timeout - validation may have started in background")
        logger.warning(f"   This is normal for long-running validations. Check validation status endpoint.")
        return jsonify({
            'message': 'Validation request received - starting in background',
            'status': 'started',
            'note': 'Validation API is processing - check validation status endpoint for progress'
        }), 202  # Accepted
    except requests.exceptions.ConnectionError:
        error_msg = 'Validation API is not running. Please start the validation API on port 5001.'
        logger.error(f"❌ VALIDATION PROXY ERROR: {error_msg}")
        logger.error(f"   Run: python v2_m1_ai_validator/api/m1_validation_api.py")
        return jsonify({
            'error': error_msg,
            'hint': 'Run: python v2_m1_ai_validator/api/m1_validation_api.py'
        }), 503
    except Exception as e:
        error_msg = f"Error proxying validation request: {e}"
        logger.error(f"❌ VALIDATION PROXY ERROR: {error_msg}")
        logger.error(f"   Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"   Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health/validation-api', methods=['GET'])
def check_validation_api_health():
    """Check if validation API is running and healthy"""
    try:
        import requests
        response = requests.get(f'{VALIDATION_API_URL}/api/health', timeout=5)
        if response.status_code == 200:
            api_status = response.json()
            return jsonify({
                'status': 'connected',
                'validation_api_url': VALIDATION_API_URL,
                'api_status': api_status
            })
        else:
            return jsonify({
                'status': 'unhealthy',
                'validation_api_url': VALIDATION_API_URL,
                'http_status': response.status_code
            }), 503
    except requests.exceptions.ConnectionError:
        return jsonify({
            'status': 'disconnected',
            'validation_api_url': VALIDATION_API_URL,
            'error': 'Cannot connect to validation API'
        }), 503
    except Exception as e:
        logger.error(f"Error checking validation API health: {e}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@app.route('/api/validation-status', methods=['GET'])
def proxy_validation_status():
    """Proxy validation status request to validation API"""
    try:
        import requests
        response = requests.get(
            f'{VALIDATION_API_URL}/api/validation-status',
            timeout=5
        )
        return jsonify(response.json()), response.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({
            'error': 'Validation API is not running',
            'is_running': False
        }), 503
    except Exception as e:
        logger.error(f"Error proxying validation status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/validation-results', methods=['GET'])
def proxy_validation_results():
    """Proxy validation results request to validation API"""
    try:
        import requests
        response = requests.get(
            f'{VALIDATION_API_URL}/api/validation-results',
            timeout=5
        )
        return jsonify(response.json()), response.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({'error': 'Validation API is not running'}), 503
    except Exception as e:
        logger.error(f"Error proxying validation results: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/demo', methods=['POST'])
def load_demo_data():
    """Load demo data for demonstration"""
    global preview_data
    
    try:
        # Load demo POZI data
        pozi_file = os.path.join(BASE_DIR, os.getenv("SAMPLE_M1_CSV", "tests/fixtures/sample_m1.csv"))
        if os.path.exists(pozi_file):
            df_pozi = pd.read_csv(pozi_file,
                                 quotechar='"',
                                 escapechar='\\',
                                 na_values=['', 'NULL', 'null'],
                                 keep_default_na=True)
            
            # Convert to JSON string first (handles NaN and special characters properly)
            json_str = df_pozi.to_json(orient='records', date_format='iso', default_handler=str)
            parsed_data = json.loads(json_str)
            
            # Clean any remaining NaN/inf values recursively
            cleaned_data = clean_for_json(parsed_data)
            preview_data['pozi_data'] = cleaned_data
            
            # Do the same for sample data
            sample_json_str = df_pozi.head(10).to_json(orient='records', date_format='iso', default_handler=str)
            sample_data = json.loads(sample_json_str)
            cleaned_sample = clean_for_json(sample_data)
            
            pozi_info = {
                'filename': 'sample_m1.csv',
                'total_rows': len(df_pozi),
                'total_columns': len(df_pozi.columns),
                'columns': list(df_pozi.columns),
                'sample_data': cleaned_sample,
                'data_types': df_pozi.dtypes.astype(str).to_dict(),
                'source': 'demo'
            }
        else:
            pozi_info = {'error': 'Demo POZI file not found'}
        
        # Load demo validation data
        validation_file = os.path.join(BASE_DIR, 'smart_openai_validation_results.csv')
        if os.path.exists(validation_file):
            df_validation = pd.read_csv(validation_file)
            # Replace NaN with None for JSON serialization
            df_validation = df_validation.where(pd.notna(df_validation), None)
            validation_data = df_validation.to_dict('records')
            preview_data['validation_results'] = validation_data
            
            # Calculate summary statistics
            total_rows = len(validation_data)
            kept_count = sum(1 for row in validation_data if row.get('decision') == 'KEEP')
            rejected_count = sum(1 for row in validation_data if row.get('decision') == 'REJECT')
            
            validation_info = {
                'filename': 'smart_openai_validation_results.csv',
                'total_rows': total_rows,
                'kept_count': kept_count,
                'rejected_count': rejected_count,
                'sample_data': validation_data[:10],
                'source': 'demo'
            }
        else:
            validation_info = {'error': 'Demo validation file not found'}
        
        return jsonify({
            'pozi': pozi_info,
            'validation': validation_info,
            'message': 'Demo data loaded successfully'
        })
        
    except Exception as e:
        logger.error(f"Error loading demo data: {str(e)}")
        return jsonify({'error': f'Error loading demo data: {str(e)}'}), 500

if __name__ == '__main__':
    print("\n" + "="*70)
    print("M1 AUTOMATION WEB INTERFACE")
    print("="*70)
    print(f"Starting server...")
    print(f"Open your browser and go to: http://localhost:5000")
    print("="*70 + "\n")
    
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True, use_reloader=False)