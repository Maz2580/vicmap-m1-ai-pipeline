"""
M1 AI Validation API
Flask API endpoints for AI-powered M1 validation
"""
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import json
import logging
from datetime import datetime
import threading
import time
from typing import Dict, Any
import pandas as pd
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

# Import our AI validator components
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Try to use database-enhanced validator, fallback to standard if database fails
try:
    from data_processing.enhanced_validator_with_database import DatabaseEnhancedM1Validator
    USE_DATABASE = True
except Exception as e:
    from data_processing.enhanced_m1_validator_v2 import EnhancedM1ValidatorV2
    USE_DATABASE = False
    print(f"Warning: Could not import database-enhanced validator: {e}")
    print("Falling back to standard AI validator without database support")

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for frontend integration

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Main app URL for logging (defaults to port 5000)
MAIN_APP_URL = os.getenv('MAIN_APP_URL', 'http://localhost:5000')

# Log queue for non-blocking log sending
_log_queue = []
_log_thread = None
_log_queue_lock = threading.Lock()

def _log_sender_worker():
    """Background worker to send logs asynchronously"""
    global _log_queue
    while True:
        try:
            if _log_queue:
                with _log_queue_lock:
                    if _log_queue:
                        log_entry = _log_queue.pop(0)
                    else:
                        log_entry = None
                
                if log_entry:
                    try:
                        response = requests.post(
                            f'{MAIN_APP_URL}/api/logs/add',
                            json=log_entry,
                            timeout=1  # Short timeout to avoid blocking
                        )
                        if response.status_code != 200:
                            logger.debug(f"Log not sent (HTTP {response.status_code})")
                    except Exception:
                        # Silently fail - don't block validation
                        pass
            
            time.sleep(0.1)  # Small delay to avoid busy waiting
        except Exception:
            pass

def _start_log_sender():
    """Start background log sender thread"""
    global _log_thread
    if _log_thread is None or not _log_thread.is_alive():
        _log_thread = threading.Thread(target=_log_sender_worker, daemon=True)
        _log_thread.start()

def send_log_to_main_app(level: str, message: str):
    """
    Send log message to main app's log queue (non-blocking)
    This allows validation logs to appear in the main log stream
    """
    try:
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'level': level,
            'message': f'[AI Validation] {message}'
        }
        
        # Always log to console first (for immediate visibility)
        # Use print for guaranteed visibility in console
        print(f"[VALIDATION API] {level}: {message}")
        logger.info(f"[AI Validation] {message}")
        
        # Try to send directly first (synchronous, but with short timeout)
        try:
            response = requests.post(
                f'{MAIN_APP_URL}/api/logs/add',
                json=log_entry,
                timeout=2  # Increased timeout for reliability
            )
            if response.status_code == 200:
                response_data = response.json()
                # Only log success for first few messages to avoid spam
                if not hasattr(send_log_to_main_app, '_success_count'):
                    send_log_to_main_app._success_count = 0
                send_log_to_main_app._success_count += 1
                if send_log_to_main_app._success_count <= 3:
                    print(f"[VALIDATION API] ✓ Log #{send_log_to_main_app._success_count} sent successfully to main app")
                    logger.info(f"✓✓✓ Log sent successfully to main app!")
                    logger.info(f"   Message: {message[:80]}...")
                    logger.info(f"   Response: {response_data}")
                return  # Success - don't queue
            else:
                print(f"[VALIDATION API] ✗ Log send failed: HTTP {response.status_code}")
                logger.warning(f"✗ Log send failed (HTTP {response.status_code}): {response.text}")
        except requests.exceptions.Timeout:
            print(f"[VALIDATION API] ⚠ Log send timeout (main app slow?) - will queue")
            logger.warning(f"⚠ Log send timeout (main app slow?) - will queue: {message[:50]}...")
            # Timeout is OK - queue it
            pass
        except requests.exceptions.ConnectionError:
            print(f"[VALIDATION API] ✗✗✗ MAIN APP NOT CONNECTED at {MAIN_APP_URL}")
            print(f"[VALIDATION API]    Log will only appear in validation API console, NOT in web interface")
            print(f"[VALIDATION API]    Make sure main app (app.py) is running on port 5000")
            logger.error(f"✗✗✗ MAIN APP NOT CONNECTED at {MAIN_APP_URL}")
            logger.error(f"   Log will only appear in validation API console, NOT in web interface")
            logger.error(f"   Make sure main app (app.py) is running on port 5000")
            return  # Don't queue if main app is not running
        except Exception as e:
            print(f"[VALIDATION API] ✗ Direct log send failed: {e}")
            logger.error(f"✗ Direct log send failed: {e}")
            logger.error(f"   Exception type: {type(e).__name__}")
        
        # Queue for async sending (non-blocking fallback)
        with _log_queue_lock:
            _log_queue.append(log_entry)
            # Limit queue size to prevent memory issues
            if len(_log_queue) > 100:
                _log_queue.pop(0)  # Remove oldest
        
        # Start sender thread if not running
        _start_log_sender()
        
    except Exception as e:
        # Don't fail validation if logging fails
        logger.debug(f"Could not queue log: {e}")

# Try to import OpenAI validator
try:
    # Import from parent directory (v2_m1_ai_validator)
    import sys
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    from smart_openai_validator import SmartOpenAIValidator
    USE_OPENAI = True
    logger.info("OpenAI validator available")
except Exception as e:
    USE_OPENAI = False
    SmartOpenAIValidator = None
    logger.warning(f"OpenAI validator not available: {e}")

# Global variables for validation status
validation_status = {
    'is_running': False,
    'progress': 0,
    'current_record': 0,
    'total_records': 0,
    'current_operation': '',
    'errors': [],
    'warnings': [],
    'results': None,
    'start_time': None,
    'end_time': None
}

# Global variables for preview data
preview_data = {
    'pozi_data': None,
    'validation_results': None
}

# Initialize AI validator (default)
try:
    if USE_DATABASE:
        ai_validator = DatabaseEnhancedM1Validator()
        logger.info("Initialized with database-enhanced validator")
    else:
        ai_validator = EnhancedM1ValidatorV2()
        logger.info("Initialized with standard AI validator")
except Exception as e:
    logger.error(f"Failed to initialize validator: {e}")
    ai_validator = None

# Initialize OpenAI validator (optional)
openai_validator = None
if USE_OPENAI:
    try:
        openai_validator = SmartOpenAIValidator()
        logger.info("Initialized OpenAI validator")
    except Exception as e:
        logger.warning(f"Failed to initialize OpenAI validator: {e}")
        openai_validator = None

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'ai_validator_ready': ai_validator is not None,
        'openai_validator_ready': openai_validator is not None,
        'database_enabled': USE_DATABASE,
        'openai_enabled': USE_OPENAI
    })

@app.route('/api/test-log', methods=['GET'])
def test_log():
    """Test log forwarding to main app - for debugging"""
    try:
        print("[VALIDATION API] 🧪 Testing log forwarding...")
        logger.info("[VALIDATION API] 🧪 Testing log forwarding...")
        
        # Test different log levels
        send_log_to_main_app('INFO', '🧪 Test INFO log from validation API')
        send_log_to_main_app('WARNING', '⚠️ Test WARNING message from validation API')
        send_log_to_main_app('ERROR', '❌ Test ERROR message from validation API')
        
        # Test enhanced logger
        try:
            import sys
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            from utils.enhanced_logger import M1Logger
            
            test_logger = M1Logger("Test_Workflow", send_log_callback=send_log_to_main_app)
            test_logger.start_workflow(2, "Test Workflow for Log Verification")
            test_logger.step_started("Test Step", "Testing enhanced logger")
            test_logger.step_completed("Test Step", 0.5, "Enhanced logger working!")
            test_logger.workflow_completed({"Test": "Success", "Logs": "Sent to main app"})
            
            return jsonify({
                'message': 'Test logs sent to main app',
                'logs_sent': 7,
                'check_console': 'Look at validation API console and main app console',
                'check_web_ui': 'Check web interface log panel for messages',
                'main_app_url': MAIN_APP_URL
            })
        except ImportError as e:
            return jsonify({
                'message': 'Enhanced logger not available',
                'error': str(e),
                'basic_logs_sent': 3
            })
    except Exception as e:
        logger.error(f"Error in test_log: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/database-info', methods=['GET'])
def get_database_info():
    """Get database connection information"""
    if not ai_validator:
        return jsonify({'error': 'Validator not initialized'}), 500
    
    if USE_DATABASE and hasattr(ai_validator, 'get_database_info'):
        info = ai_validator.get_database_info()
        return jsonify(info)
    else:
        return jsonify({
            'connected': False,
            'message': 'Database not enabled'
        })

@app.route('/api/validate-m1', methods=['POST'])
def validate_m1():
    """
    Validate M1 file using AI-powered validation
    
    Request body:
    {
        "file_path": "path/to/file.csv",
        "validator_type": "default" | "openai" (optional, defaults to "default")
    }
    """
    global validation_status
    
    try:
        # Check if validation is already running
        if validation_status['is_running']:
            return jsonify({
                'error': 'Validation already in progress',
                'status': 'running'
            }), 409
        
        # Get file path and validator type from request
        data = request.get_json()
        file_path = data.get('file_path')
        # FIX: Make Smart OpenAI validator the DEFAULT (not 'default')
        # If OpenAI validator is available, use it by default; otherwise fall back to default
        validator_type = data.get('validator_type', 'openai' if openai_validator else 'default')
        
        if not file_path:
            return jsonify({'error': 'File path is required'}), 400
        
        # Resolve file path - handle both absolute and relative paths
        file_path = os.path.normpath(file_path)
        
        # If path is relative, try multiple locations
        if not os.path.isabs(file_path):
            # Try project root first
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            potential_paths = [
                os.path.join(project_root, file_path),
                file_path,  # Current working directory
                os.path.abspath(file_path)  # Resolved relative path
            ]
            
            found = False
            for potential_path in potential_paths:
                if os.path.exists(potential_path):
                    file_path = potential_path
                    found = True
                    break
            
            if not found:
                return jsonify({
                    'error': f'File not found: {file_path}',
                    'tried_paths': potential_paths
                }), 404
        else:
            # Absolute path - check directly
            if not os.path.exists(file_path):
                return jsonify({'error': f'File not found: {file_path}'}), 404
        
        # Validate validator type
        if validator_type == 'openai':
            if not openai_validator:
                return jsonify({
                    'error': 'OpenAI validator not available. Please check OPENAI_API_KEY is set.',
                    'available_validators': ['default']
                }), 400
        
        # Start validation in background thread
        # Use a wrapper to catch any exceptions in the thread
        def validation_wrapper():
            try:
                run_validation(file_path, validator_type)
            except Exception as e:
                logger.error(f"Validation thread error: {e}")
                validation_status['is_running'] = False
                validation_status['current_operation'] = f'Error: {str(e)}'
                validation_status['errors'].append(str(e))
        
        thread = threading.Thread(target=validation_wrapper, daemon=True)
        thread.daemon = True
        thread.start()
        
        # Return immediately - don't wait for validation to start
        logger.info(f"Validation thread started for file: {file_path}")
        return jsonify({
            'message': 'Validation started',
            'status': 'started',
            'file_path': file_path,
            'validator_type': validator_type
        }), 200
        
    except Exception as e:
        logger.error(f"Error starting validation: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/validation-status', methods=['GET'])
def get_validation_status():
    """Get current validation status"""
    return jsonify(validation_status)

@app.route('/api/validation-results', methods=['GET'])
def get_validation_results():
    """Get validation results"""
    if validation_status['results']:
        return jsonify(validation_status['results'])
    else:
        return jsonify({'error': 'No results available'}), 404

@app.route('/api/stop-validation', methods=['POST'])
def stop_validation():
    """Stop current validation"""
    global validation_status
    
    if validation_status['is_running']:
        validation_status['is_running'] = False
        validation_status['current_operation'] = 'Stopped by user'
        send_log_to_main_app('WARNING', 'Validation stopped by user')
        return jsonify({'message': 'Validation stopped'})
    else:
        return jsonify({'error': 'No validation running'}), 400

@app.route('/api/validation-cleanup', methods=['POST'])
def cleanup_validation_data():
    """Clean up validation data to free memory"""
    global preview_data, validation_status
    
    try:
        # Clear preview data
        preview_data = {
            'pozi_data': None,
            'validation_results': None
        }
        
        # Clear validation results (keep status for monitoring)
        validation_status['results'] = None
        validation_status['errors'] = []
        validation_status['warnings'] = []
        
        logger.info("Validation data cleaned up")
        send_log_to_main_app('INFO', 'Validation data cleaned up - memory freed')
        
        return jsonify({
            'status': 'cleaned',
            'message': 'Validation data cleaned up successfully'
        })
    except Exception as e:
        logger.error(f"Error cleaning up validation data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/smart-validate-m1', methods=['POST'])
def smart_validate_m1():
    """
    Use SmartOpenAIValidator directly (alternative to /api/validate-m1 with validator_type='openai')
    This endpoint explicitly uses the smart validator for clarity
    """
    global validation_status
    
    if not openai_validator:
        return jsonify({
            'error': 'Smart OpenAI validator not available. Please check OPENAI_API_KEY is set.',
            'available_validators': ['default']
        }), 400
    
    # Get file path from request
    data = request.get_json()
    file_path = data.get('file_path')
    
    if not file_path:
        return jsonify({'error': 'File path is required'}), 400
    
    # Resolve file path
    file_path = os.path.normpath(file_path)
    if not os.path.isabs(file_path):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        potential_paths = [
            os.path.join(project_root, file_path),
            file_path,
            os.path.abspath(file_path)
        ]
        found = False
        for potential_path in potential_paths:
            if os.path.exists(potential_path):
                file_path = potential_path
                found = True
                break
        if not found:
            return jsonify({'error': f'File not found: {file_path}'}), 404
    else:
        if not os.path.exists(file_path):
            return jsonify({'error': f'File not found: {file_path}'}), 404
    
    # Check if validation is already running
    if validation_status['is_running']:
        return jsonify({
            'error': 'Validation already in progress',
            'status': 'running'
        }), 409
    
    # Start validation with smart validator
    def validation_wrapper():
        try:
            run_validation(file_path, 'openai')  # Use 'openai' validator type
        except Exception as e:
            logger.error(f"Smart validation thread error: {e}")
            validation_status['is_running'] = False
            validation_status['current_operation'] = f'Error: {str(e)}'
            validation_status['errors'].append(str(e))
    
    thread = threading.Thread(target=validation_wrapper, daemon=True)
    thread.start()
    
    logger.info(f"Smart validation thread started for file: {file_path}")
    return jsonify({
        'message': 'Smart OpenAI validation started',
        'status': 'started',
        'file_path': file_path,
        'validator_type': 'smart_openai'
    }), 200

@app.route('/api/database/explore-schema', methods=['GET'])
def explore_database_schema():
    """Explore database schema using schema_explorer.py"""
    try:
        from utils.schema_explorer import VicMapSchemaExplorer
        explorer = VicMapSchemaExplorer()
        
        layer_name = request.args.get('layer', 'address')
        metadata = explorer.get_layer_metadata(layer_name)
        
        if metadata:
            return jsonify({
                'layer': layer_name,
                'metadata': metadata,
                'fields': metadata.get('fields', [])
            })
        else:
            return jsonify({'error': f'Could not get schema for layer: {layer_name}'}), 404
    except ImportError as e:
        return jsonify({'error': f'Schema explorer not available: {e}'}), 500
    except Exception as e:
        logger.error(f"Error exploring schema: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/database/optimize-query', methods=['POST'])
def optimize_database_query():
    """Optimize database query using query_optimizer.py"""
    try:
        from utils.query_optimizer import ValidationCache
        
        data = request.get_json()
        query_data = data.get('query_data') or data.get('data') or data
        
        if not query_data:
            return jsonify({'error': 'Query data is required'}), 400
        
        # Initialize cache
        cache = ValidationCache()
        
        # Try to get from cache first
        cached_result = cache.get(query_data)
        if cached_result:
            return jsonify({
                'optimized': True,
                'cached': True,
                'result': cached_result,
                'message': 'Result retrieved from cache',
                'cache_stats': {
                    'hits': cache.hits,
                    'misses': cache.misses
                }
            })
        
        # Store in cache for future use
        # Note: query_optimizer.py is primarily a cache, not a query optimizer
        # It optimizes by caching validation results
        cache.put(query_data, {'status': 'processed', 'data': query_data})
        
        return jsonify({
            'optimized': True,
            'cached': False,
            'result': {'status': 'processed', 'data': query_data},
            'message': 'Query processed and cached',
            'cache_stats': {
                'hits': cache.hits,
                'misses': cache.misses
            }
        })
    except ImportError as e:
        return jsonify({'error': f'Query optimizer not available: {e}'}), 500
    except Exception as e:
        logger.error(f"Error optimizing query: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/enhance-comments', methods=['POST'])
def enhance_comments():
    """
    Enhance comments using AI comment enhancer (connected to smart validator)
    FIX: Perplexity - This endpoint exists but wasn't properly connected
    """
    try:
        data = request.get_json()
        record_data = data.get('record_data') or data.get('row_data', {})
        edit_code = data.get('edit_code') or record_data.get('edit_code')
        comment = data.get('comment') or record_data.get('comments', '')
        
        if not edit_code and not record_data.get('edit_code'):
            return jsonify({'error': 'Edit code is required'}), 400
        
        # Ensure edit_code is in record_data for enhancer
        if edit_code and 'edit_code' not in record_data:
            record_data['edit_code'] = edit_code
        
        # Use AI comment enhancer
        from data_processing.ai_comment_enhancer import AICommentEnhancer
        enhancer = AICommentEnhancer()
        
        # Enhance comment - the enhancer needs record_data with edit_code
        enhanced_comment = enhancer.enhance_comment(record_data)
        
        # Check quality
        quality_score = 0.8  # Default
        if hasattr(enhancer, '_is_comment_adequate'):
            try:
                quality_score = 1.0 if enhancer._is_comment_adequate(enhanced_comment, edit_code or record_data.get('edit_code'), record_data) else 0.6
            except:
                pass
        
        return jsonify({
            'original_comment': comment,
            'enhanced_comment': enhanced_comment,
            'quality_score': quality_score,
            'edit_code': edit_code or record_data.get('edit_code'),
            'record_data': record_data
        })
    except ImportError as e:
        return jsonify({'error': f'Comment enhancer not available: {e}'}), 500
    except Exception as e:
        logger.error(f"Error enhancing comment: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/error-recovery', methods=['POST'])
def get_error_recovery():
    """
    Get AI-powered error recovery suggestions
    FIX: Perplexity - This exists but should be properly exposed via API
    """
    try:
        data = request.get_json()
        error_message = data.get('error_message')
        record_data = data.get('record_data', {}) or data.get('row_data', {})
        
        if not error_message:
            return jsonify({'error': 'Error message is required'}), 400
        
        # Use AI error recovery
        from data_processing.ai_error_recovery import AIErrorRecovery
        error_recovery = AIErrorRecovery()
        
        # Analyze error - this returns a dict with error_type, solutions, etc.
        analysis = error_recovery.analyze_error(error_message, record_data)
        
        return jsonify({
            'error_message': error_message,
            'analysis': analysis,
            'error_type': analysis.get('error_type', 'unknown'),
            'confidence': analysis.get('confidence', 0.0),
            'solutions': analysis.get('solutions', []),
            'auto_fix_available': analysis.get('auto_fix_available', False),
            'suggested_changes': analysis.get('suggested_changes', {}),
            'explanation': analysis.get('explanation', '')
        })
    except ImportError as e:
        return jsonify({'error': f'Error recovery not available: {e}'}), 500
    except Exception as e:
        logger.error(f"Error getting error recovery: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/database/helper', methods=['POST'])
def database_helper_query():
    """
    Use database_helper.py for multi-table database operations
    FIX: Perplexity - Expose database_helper.py via API
    """
    try:
        from data_processing.database_helper import InfoProdDatabaseHelper
        
        data = request.get_json()
        operation = data.get('operation')  # 'find_property', 'get_rates', 'find_address', etc.
        query_params = data.get('params', {})
        
        if not operation:
            return jsonify({'error': 'Operation is required'}), 400
        
        # Initialize database helper
        db_helper = InfoProdDatabaseHelper()
        
        # Route to appropriate method (using actual method names from database_helper.py)
        if operation == 'find_property' or operation == 'get_property':
            propnum = query_params.get('propnum')
            if not propnum:
                return jsonify({'error': 'propnum is required'}), 400
            result = db_helper.find_property_by_propnum(propnum, check_new_properties=True)
        elif operation == 'get_rates':
            propnum = query_params.get('propnum')
            if not propnum:
                return jsonify({'error': 'propnum is required'}), 400
            result = db_helper.get_rates_data(propnum)
        elif operation == 'find_address':
            address_data = query_params.get('address_data', query_params)
            result = db_helper.find_address_relationships(address_data)
        elif operation == 'validate_property':
            propnum = query_params.get('propnum')
            if not propnum:
                return jsonify({'error': 'propnum is required'}), 400
            exists, issues = db_helper.validate_property_exists(propnum)
            result = {'exists': exists, 'issues': issues}
        elif operation == 'get_database_info':
            result = {
                'property_tables': db_helper.property_tables,
                'parcel_tables': db_helper.parcel_tables,
                'rates_tables': db_helper.rates_tables,
                'primary_property_table': db_helper.property_table,
                'primary_parcel_table': db_helper.parcel_table,
                'primary_rates_table': db_helper.rates_table,
                'all_tables': db_helper.get_all_tables(),
                'database_summary': db_helper.get_database_summary()
            }
        elif operation == 'get_table_info':
            table_name = query_params.get('table_name')
            if not table_name:
                return jsonify({'error': 'table_name is required'}), 400
            result = db_helper.get_table_info(table_name)
        else:
            return jsonify({'error': f'Unknown operation: {operation}'}), 400
        
        return jsonify({
            'operation': operation,
            'result': result,
            'success': True
        })
    except ImportError as e:
        return jsonify({'error': f'Database helper not available: {e}'}), 500
    except Exception as e:
        logger.error(f"Error in database helper query: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/validate-batch', methods=['POST'])
def validate_batch():
    """
    Validate multiple M1 files in batch
    """
    try:
        data = request.get_json()
        file_paths = data.get('file_paths', [])
        
        if not file_paths:
            return jsonify({'error': 'File paths are required'}), 400
        
        results = []
        for file_path in file_paths:
            if os.path.exists(file_path):
                try:
                    result = ai_validator.validate_m1_file(file_path, auto_fix=True)
                    results.append({
                        'file_path': file_path,
                        'status': 'success',
                        'result': result
                    })
                except Exception as e:
                    results.append({
                        'file_path': file_path,
                        'status': 'error',
                        'error': str(e)
                    })
            else:
                results.append({
                    'file_path': file_path,
                    'status': 'error',
                    'error': 'File not found'
                })
        
        return jsonify({
            'message': 'Batch validation completed',
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Error in batch validation: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/field-mapping-suggestions', methods=['POST'])
def get_field_mapping_suggestions():
    """
    Get AI-powered field mapping suggestions
    """
    try:
        data = request.get_json()
        field_name = data.get('field_name')
        layer_type = data.get('layer_type', 'address')
        
        if not field_name:
            return jsonify({'error': 'Field name is required'}), 400
        
        suggestions = ai_validator.field_mapper.suggest_field_mapping(field_name, layer_type)
        
        return jsonify({
            'field_name': field_name,
            'layer_type': layer_type,
            'suggestions': suggestions
        })
        
    except Exception as e:
        logger.error(f"Error getting field mapping suggestions: {str(e)}")
        return jsonify({'error': str(e)}), 500

# REMOVED: Duplicate /api/error-recovery endpoint - kept the enhanced version at line 570
# REMOVED: Duplicate /api/comment-enhancement endpoint - using /api/enhance-comments instead
# Note: /api/enhance-comments (line 523) is the primary endpoint for comment enhancement

@app.route('/api/export-report', methods=['POST'])
def export_report():
    """
    Export validation report
    """
    try:
        data = request.get_json()
        report_data = data.get('report_data')
        format_type = data.get('format', 'json')  # json, csv, xlsx
        
        if not report_data:
            return jsonify({'error': 'Report data is required'}), 400
        
        # Generate report file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if format_type == 'json':
            filename = f"m1_validation_report_{timestamp}.json"
            filepath = os.path.join('reports', filename)
            os.makedirs('reports', exist_ok=True)
            
            with open(filepath, 'w') as f:
                json.dump(report_data, f, indent=2)
            
            return send_file(filepath, as_attachment=True)
        
        elif format_type == 'csv':
            # Convert to CSV format
            filename = f"m1_validation_report_{timestamp}.csv"
            filepath = os.path.join('reports', filename)
            os.makedirs('reports', exist_ok=True)
            
            # Extract validation results for CSV
            if 'validation_results' in report_data:
                df = pd.DataFrame(report_data['validation_results'])
                df.to_csv(filepath, index=False)
                return send_file(filepath, as_attachment=True)
        
        return jsonify({'error': 'Unsupported format'}), 400
        
    except Exception as e:
        logger.error(f"Error exporting report: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Preview endpoints
@app.route('/api/preview/pozi', methods=['POST'])
def upload_pozi_preview():
    """Upload and preview POZI CSV data"""
    global preview_data
    
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.endswith('.csv'):
            return jsonify({'error': 'File must be a CSV'}), 400
        
        # Read CSV file
        df = pd.read_csv(file)
        preview_data['pozi_data'] = df.to_dict('records')
        
        # Return preview data
        preview_info = {
            'filename': file.filename,
            'total_rows': len(df),
            'total_columns': len(df.columns),
            'columns': list(df.columns),
            'sample_data': df.head(10).to_dict('records'),
            'data_types': df.dtypes.astype(str).to_dict()
        }
        
        logger.info(f"POZI data uploaded for preview: {file.filename}, {len(df)} rows, {len(df.columns)} columns")
        return jsonify(preview_info)
        
    except Exception as e:
        logger.error(f"Error uploading POZI data: {str(e)}")
        return jsonify({'error': f'Error processing file: {str(e)}'}), 500

@app.route('/api/preview/pozi/data', methods=['GET'])
def get_pozi_preview_data():
    """Get POZI data for preview"""
    global preview_data
    
    if preview_data['pozi_data'] is None:
        return jsonify({'error': 'No POZI data available'}), 404
    
    try:
        # Get pagination parameters
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        
        # Calculate pagination
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        
        # Get data slice
        data_slice = preview_data['pozi_data'][start_idx:end_idx]
        
        response_data = {
            'data': data_slice,
            'total_rows': len(preview_data['pozi_data']),
            'page': page,
            'per_page': per_page,
            'total_pages': (len(preview_data['pozi_data']) + per_page - 1) // per_page
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error getting POZI preview data: {str(e)}")
        return jsonify({'error': f'Error retrieving data: {str(e)}'}), 500

@app.route('/api/preview/validation', methods=['POST'])
def upload_validation_preview():
    """Upload and preview AI validation results"""
    global preview_data
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No validation data provided'}), 400
        
        preview_data['validation_results'] = data
        
        # Calculate summary statistics
        total_rows = len(data)
        kept_count = sum(1 for row in data if row.get('decision') == 'KEEP')
        rejected_count = sum(1 for row in data if row.get('decision') == 'REJECT')
        
        # Get unique reasons
        all_reasons = []
        for row in data:
            reasons = row.get('reasons', [])
            if isinstance(reasons, list):
                all_reasons.extend(reasons)
            elif isinstance(reasons, str):
                all_reasons.append(reasons)
        
        unique_reasons = list(set(all_reasons))
        
        preview_info = {
            'total_rows': total_rows,
            'kept_count': kept_count,
            'rejected_count': rejected_count,
            'unique_reasons': unique_reasons,
            'sample_data': data[:10]  # First 10 rows
        }
        
        logger.info(f"Validation data uploaded for preview: {total_rows} rows, {kept_count} kept, {rejected_count} rejected")
        return jsonify(preview_info)
        
    except Exception as e:
        logger.error(f"Error uploading validation preview data: {str(e)}")
        return jsonify({'error': f'Error processing validation data: {str(e)}'}), 500

@app.route('/api/preview/validation/data', methods=['GET'])
def get_validation_preview_data():
    """Get validation data for preview"""
    global preview_data
    
    if preview_data['validation_results'] is None:
        return jsonify({'error': 'No validation data available'}), 404
    
    try:
        # Get pagination parameters
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        
        # Calculate pagination
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        
        # Get data slice
        data_slice = preview_data['validation_results'][start_idx:end_idx]
        
        response_data = {
            'data': data_slice,
            'total_rows': len(preview_data['validation_results']),
            'page': page,
            'per_page': per_page,
            'total_pages': (len(preview_data['validation_results']) + per_page - 1) // per_page
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error getting validation preview data: {str(e)}")
        return jsonify({'error': f'Error retrieving data: {str(e)}'}), 500

@app.route('/api/preview/summary', methods=['GET'])
def get_preview_summary():
    """Get summary of current preview data"""
    global preview_data
    
    summary = {
        'pozi_data': {
            'available': preview_data['pozi_data'] is not None,
            'rows': len(preview_data['pozi_data']) if preview_data['pozi_data'] else 0,
            'columns': len(preview_data['pozi_data'][0]) if preview_data['pozi_data'] and len(preview_data['pozi_data']) > 0 else 0
        },
        'validation_data': {
            'available': preview_data['validation_results'] is not None,
            'rows': len(preview_data['validation_results']) if preview_data['validation_results'] else 0,
            'kept': sum(1 for row in preview_data['validation_results'] if row.get('decision') == 'KEEP') if preview_data['validation_results'] else 0,
            'rejected': sum(1 for row in preview_data['validation_results'] if row.get('decision') == 'REJECT') if preview_data['validation_results'] else 0
        }
    }
    
    return jsonify(summary)

# Historical Reports Endpoints
@app.route('/api/reports/list', methods=['GET'])
def list_historical_reports():
    """List all available historical reports"""
    try:
        import glob
        
        # Get the project root directory (two levels up from this API file)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            file_path = os.path.join(project_root, file_path)
            file_path = os.path.normpath(file_path)
        
        logger.info(f"Loading POZI file: {file_path}")
        
        # Check if file exists
        if not os.path.exists(file_path):
            return jsonify({'error': f'File not found: {file_path}'}), 404
        
        # Load CSV file
        df = pd.read_csv(file_path)
        preview_data['pozi_data'] = df.to_dict('records')
        
        # Return preview data
        preview_info = {
            'filename': os.path.basename(file_path),
            'total_rows': len(df),
            'total_columns': len(df.columns),
            'columns': list(df.columns),
            'sample_data': df.head(10).to_dict('records'),
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
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            file_path = os.path.join(project_root, file_path)
            file_path = os.path.normpath(file_path)
        
        logger.info(f"Loading validation file: {file_path}")
        
        # Check if file exists
        if not os.path.exists(file_path):
            return jsonify({'error': f'File not found: {file_path}'}), 404
        
        # Load data based on file type
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
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

@app.route('/api/reports/demo', methods=['POST'])
def load_demo_data():
    """Load demo data for demonstration"""
    global preview_data
    
    try:
        # Get the project root directory
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # Load demo POZI data
        pozi_file = os.path.join(project_root, os.getenv("SAMPLE_M1_CSV", "tests/fixtures/sample_m1.csv"))
        if os.path.exists(pozi_file):
            df_pozi = pd.read_csv(pozi_file)
            preview_data['pozi_data'] = df_pozi.to_dict('records')
            
            pozi_info = {
                'filename': 'sample_m1.csv',
                'total_rows': len(df_pozi),
                'total_columns': len(df_pozi.columns),
                'columns': list(df_pozi.columns),
                'sample_data': df_pozi.head(10).to_dict('records'),
                'data_types': df_pozi.dtypes.astype(str).to_dict(),
                'source': 'demo'
            }
        else:
            pozi_info = {'error': 'Demo POZI file not found'}
        
        # Load demo validation data
        validation_file = os.path.join(project_root, 'smart_openai_validation_results.csv')
        if os.path.exists(validation_file):
            df_validation = pd.read_csv(validation_file)
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

def run_openai_validation(file_path: str):
    """
    Enhanced AI validation with meaningful logging using M1Logger
    """
    global validation_status, preview_data
    
    # Import enhanced logger
    import sys
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    from utils.enhanced_logger import M1Logger
    
    # Initialize enhanced logger with callback to send logs to main app
    m1_logger = M1Logger("AI_Validation", send_log_callback=send_log_to_main_app)
    
    try:
        filename = os.path.basename(file_path)
        
        # Start workflow
        m1_logger.start_workflow(4, f"Smart AI Validation of {filename}")
        
        validation_status['is_running'] = True
        validation_status['progress'] = 0
        validation_status['current_record'] = 0
        validation_status['errors'] = []
        validation_status['warnings'] = []
        validation_status['start_time'] = datetime.now().isoformat()
        
        # Step 1: File Analysis
        step_start = time.time()
        m1_logger.step_started("File Analysis", "Reading CSV and analyzing structure")
        
        df = pd.read_csv(file_path)
        validation_status['total_records'] = len(df)
        validation_status['current_operation'] = 'File loaded, analyzing structure...'
        
        m1_logger.step_progress(f"Loaded {len(df)} rows with {len(df.columns)} columns")
        m1_logger.step_completed("File Analysis", time.time() - step_start, 
                                f"{len(df)} rows ready for validation")
        
        # Step 2: Training Data Analysis
        step_start = time.time()
        m1_logger.step_started("AI Training Analysis", "OpenAI analyzing data patterns")
        m1_logger.step_progress("Connecting to OpenAI API...")
        
        validation_status['current_operation'] = 'Analyzing training data with OpenAI...'
        training_analysis = openai_validator.load_and_analyze_training_data(file_path)
        validation_status['progress'] = 25
        
        patterns_found = len(training_analysis.get('patterns', []))
        m1_logger.step_completed("AI Training Analysis", time.time() - step_start,
                                f"{patterns_found} data patterns identified")
        
        # Step 3: Row-by-Row Validation
        step_start = time.time()
        m1_logger.step_started("Smart Validation", "AI validating each record")
        
        validation_results = []
        batch_size = 10
        total_batches = (len(df) + batch_size - 1) // batch_size
        total_rows = len(df)
        
        m1_logger.step_progress(f"Processing {total_batches} batches of {batch_size} rows each")
        estimated_minutes = (total_rows * 4) // 60
        m1_logger.step_progress(f"Estimated time: ~{estimated_minutes} minutes")
        
        for batch_idx in range(total_batches):
            start_idx = batch_idx * batch_size
            end_idx = min((batch_idx + 1) * batch_size, total_rows)
            
            validation_status['current_record'] = end_idx
            validation_status['progress'] = 25 + int((batch_idx + 1) / total_batches * 65)
            validation_status['current_operation'] = f'Processing batch {batch_idx + 1}/{total_batches} (rows {start_idx}-{end_idx})...'
            
            # Progress logging every 5 batches or at end
            if (batch_idx + 1) % 5 == 0 or (batch_idx + 1) == total_batches:
                m1_logger.step_progress(f"Batch {batch_idx + 1}/{total_batches} complete", 
                                       batch_idx + 1, total_batches)
            
            # Process batch
            batch_df = df.iloc[start_idx:end_idx]
            for idx, row in batch_df.iterrows():
                try:
                    result = openai_validator.validate_single_row_with_openai(row, idx)
                    validation_results.append(result)
                    
                    # Log rejections
                    if result.get('decision') == 'REJECT':
                        reason = result.get('reason', 'Unknown reason')[:60]
                        m1_logger.step_warning(f"Row {idx + 1} rejected: {reason}")
                        
                except Exception as e:
                    m1_logger.step_error(f"Row {idx + 1} validation failed: {str(e)}",
                                        "Using fallback validation pattern")
                    fallback_result = openai_validator._fallback_single_validation({
                        'row_index': idx,
                        'propnum': str(row.get('propnum', '')).replace('.0', ''),
                        'comments': str(row.get('comments', ''))
                    })
                    validation_results.append(fallback_result)
        
        m1_logger.step_completed("Smart Validation", time.time() - step_start,
                                f"{len(validation_results)} records processed")
        
        # Step 4: Results Analysis
        step_start = time.time()
        m1_logger.step_started("Results Analysis", "Generating summary statistics")
        
        validation_status['current_operation'] = 'Generating summary statistics...'
        summary = openai_validator._generate_summary_statistics(validation_results)
        validation_status['progress'] = 100
        
        kept_count = summary["kept_count"]
        rejected_count = summary["rejected_count"]
        avg_confidence = summary["average_confidence"]
        
        m1_logger.step_completed("Results Analysis", time.time() - step_start,
                                f"{kept_count} kept, {rejected_count} rejected")
        
        # Final workflow summary
        workflow_summary = {
            "Records Processed": f"{summary['total_rows']}",
            "Records Kept": f"{kept_count} ({kept_count/summary['total_rows']*100:.1f}%)",
            "Records Rejected": f"{rejected_count} ({rejected_count/summary['total_rows']*100:.1f}%)",
            "Average Confidence": f"{avg_confidence:.1%}",
        }
        
        # Add top rejection reason if available
        if summary.get('rejection_reasons'):
            top_reason = sorted(summary['rejection_reasons'].items(), key=lambda x: x[1], reverse=True)[0]
            workflow_summary["Top Rejection Reason"] = f"{top_reason[0]} ({top_reason[1]} rows)"
        else:
            workflow_summary["Top Rejection Reason"] = "None"
        
        m1_logger.workflow_completed(workflow_summary)
        
        # Store results
        result = {
            'validation_results': validation_results,
            'summary_statistics': summary,
            'openai_training_analysis': training_analysis,
            'ai_recommendations': openai_validator._generate_ai_recommendations(summary, training_analysis['patterns']),
            'next_steps': openai_validator._generate_next_steps(summary),
            'validator_type': 'smart_openai'
        }
        
        validation_status['results'] = result
        validation_status['current_operation'] = 'OpenAI validation completed'
        validation_status['end_time'] = datetime.now().isoformat()
        
        # Store validation results in preview data
        preview_data['validation_results'] = validation_results
        
        # Extract errors and warnings
        for record in validation_results:
            if record.get('decision') == 'REJECT':
                reason = record.get('reason', 'Unknown reason')
                validation_status['errors'].append(f"Row {record.get('row_index')}: {reason}")
            if record.get('confidence', 1.0) < 0.7:
                validation_status['warnings'].append(f"Row {record.get('row_index')}: Low confidence ({record.get('confidence', 0):.1%})")
        
        validation_status['is_running'] = False
        
        # FIX: Perplexity - Automatic memory cleanup after validation completes
        # Schedule cleanup after a delay to allow results to be retrieved first
        def delayed_cleanup():
            time.sleep(300)  # Wait 5 minutes before cleanup (allows time to retrieve results)
            global preview_data
            # Only clear if validation is not running (safety check)
            if not validation_status.get('is_running', False):
                old_pozi_size = len(str(preview_data.get('pozi_data', [])))
                old_validation_size = len(str(preview_data.get('validation_results', [])))
                preview_data = {
                    'pozi_data': None,
                    'validation_results': None
                }
                logger.info(f"Auto-cleaned validation preview data (freed ~{old_pozi_size + old_validation_size} bytes)")
                send_log_to_main_app('INFO', 'Automatic memory cleanup completed')
        
        cleanup_thread = threading.Thread(target=delayed_cleanup, daemon=True)
        cleanup_thread.start()
        
    except Exception as e:
        m1_logger.step_error(f"Validation failed: {str(e)}", 
                            "Check file format and OpenAI API connection")
        validation_status['is_running'] = False
        validation_status['current_operation'] = f'Error: {str(e)}'
        validation_status['errors'].append(str(e))

def run_validation(file_path: str, validator_type: str = 'openai'):
    """
    Run validation in background thread
    
    Args:
        file_path: Path to the CSV file to validate
        validator_type: 'openai' (smart/default), 'database', or 'basic' (fallback)
    """
    global validation_status
    
    try:
        # FIX: Perplexity - Make Smart OpenAI validator the PRIMARY default
        # Try 'smart' or 'openai' first (they're the same - Smart OpenAI Validator)
        if (validator_type in ['openai', 'smart', 'smart_openai']) and openai_validator:
            run_openai_validation(file_path)
            return
        
        # Try database-enhanced validator if available
        if validator_type == 'database' and USE_DATABASE and ai_validator:
            # Use database-enhanced validator
            validation_status['is_running'] = True
            validation_status['progress'] = 0
            validation_status['current_record'] = 0
            validation_status['errors'] = []
            validation_status['warnings'] = []
            validation_status['start_time'] = datetime.now().isoformat()
            validation_status['current_operation'] = 'Loading M1 file with database validator...'
            
            filename = os.path.basename(file_path)
            send_log_to_main_app('INFO', f'Starting database-enhanced validation for file: {filename}')
            logger.info(f"Starting database-enhanced validation for file: {filename}")
            
            df = pd.read_csv(file_path)
            validation_status['total_records'] = len(df)
            result = ai_validator.validate_m1_file(file_path, auto_fix=True)
            
            validation_status['results'] = result
            validation_status['progress'] = 100
            validation_status['current_operation'] = 'Database validation completed'
            validation_status['end_time'] = datetime.now().isoformat()
            
            if 'validation_results' in result:
                preview_data['validation_results'] = result['validation_results']
            
            validation_status['is_running'] = False
            send_log_to_main_app('INFO', f'Database validation completed successfully for {filename}')
            logger.info(f"Database validation completed for {filename}")
            return
        
        # Fallback to basic validator (only if smart validator not available)
        logger.warning(f"Smart OpenAI validator not available, falling back to basic validator")
        send_log_to_main_app('WARNING', 'Smart OpenAI validator not available - using basic validator')
        validation_status['is_running'] = True
        validation_status['progress'] = 0
        validation_status['current_record'] = 0
        validation_status['errors'] = []
        validation_status['warnings'] = []
        validation_status['start_time'] = datetime.now().isoformat()
        validation_status['current_operation'] = 'Loading M1 file...'
        
        # Log to main app
        filename = os.path.basename(file_path)
        send_log_to_main_app('INFO', f'Starting validation for file: {filename}')
        logger.info(f"Starting validation for file: {filename}")
        
        # Load and analyze file
        df = pd.read_csv(file_path)
        validation_status['total_records'] = len(df)
        validation_status['current_operation'] = f'Processing {len(df)} records...'
        send_log_to_main_app('INFO', f'Loaded {len(df)} rows. Processing with default validator...')
        
        # Run validation with progress updates
        result = ai_validator.validate_m1_file(file_path, auto_fix=True)
        
        validation_status['results'] = result
        validation_status['progress'] = 100
        validation_status['current_operation'] = 'Validation completed'
        validation_status['end_time'] = datetime.now().isoformat()
        
        # Store validation results in preview data
        if 'validation_results' in result:
            preview_data['validation_results'] = result['validation_results']
            
            # Extract errors and warnings
            for record in result['validation_results']:
                if record.get('issues'):
                    validation_status['errors'].extend(record['issues'])
                if record.get('suggestions'):
                    validation_status['warnings'].extend(record['suggestions'])
        
        validation_status['is_running'] = False
        send_log_to_main_app('INFO', f'Validation completed successfully for {filename}')
        logger.info(f"Validation completed for {filename}")
        
    except Exception as e:
        error_msg = f"Error in validation: {str(e)}"
        send_log_to_main_app('ERROR', error_msg)
        logger.error(error_msg)
        validation_status['is_running'] = False
        validation_status['current_operation'] = f'Error: {str(e)}'
        validation_status['errors'].append(str(e))

if __name__ == '__main__':
    # Create reports directory
    os.makedirs('reports', exist_ok=True)
    
    # Get configuration from environment variables
    api_host = os.getenv('API_HOST', '0.0.0.0')
    api_port = int(os.getenv('API_PORT', '5001'))
    debug_mode = os.getenv('DEBUG', 'True').lower() == 'true'
    
    # Run the Flask app
    app.run(host=api_host, port=api_port, debug=debug_mode)
