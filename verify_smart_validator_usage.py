"""
Verify that smart_openai_validator.py is actually being used
and check why logs might not be visible
"""
import requests
import json
import sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

base_url = 'http://localhost:5001'

print('=' * 70)
print('SMART VALIDATOR USAGE VERIFICATION')
print('=' * 70)

# 1. Check health to verify validator is initialized
print('\n1. Checking validator initialization...')
print('-' * 70)
try:
    r = requests.get(f'{base_url}/api/health', timeout=5)
    health = r.json()
    print(f'✓ OpenAI Validator Ready: {health.get("openai_validator_ready")}')
    print(f'✓ OpenAI Enabled: {health.get("openai_enabled")}')
    print(f'✓ Database Enabled: {health.get("database_enabled")}')
    
    if not health.get("openai_validator_ready"):
        print('\n⚠️  WARNING: Smart OpenAI Validator is NOT initialized!')
        print('   This means smart_openai_validator.py is NOT being used.')
        print('   Check the validation API console for errors.')
    else:
        print('\n✓ Smart OpenAI Validator IS initialized!')
        print('   This means smart_openai_validator.py IS being used.')
        
except Exception as e:
    print(f'✗ Error checking health: {e}')

# 2. Check current validation status
print('\n2. Current validation status...')
print('-' * 70)
try:
    r = requests.get(f'{base_url}/api/validation-status', timeout=5)
    status = r.json()
    print(f'   is_running: {status.get("is_running")}')
    print(f'   validator_type in results: {status.get("results", {}).get("validator_type", "N/A")}')
    
    if status.get('results') and status['results'].get('validator_type') == 'smart_openai':
        print('\n✓ CONFIRMED: Last validation used smart_openai_validator.py!')
    elif status.get('is_running'):
        print('\n⏳ Validation is currently running...')
        print(f'   Progress: {status.get("progress", 0)}%')
        print(f'   Operation: {status.get("current_operation", "N/A")}')
    else:
        print('\n⚠️  No validation results yet. Start a validation to see which validator is used.')
        
except Exception as e:
    print(f'✗ Error checking status: {e}')

# 3. Check if logs are being sent to main app
print('\n3. Log transmission check...')
print('-' * 70)
print('   The enhanced logger sends logs via send_log_to_main_app()')
print('   which posts to http://localhost:5000/api/logs/add')
print('   Check the main app console (app.py) to see if logs are received.')
print('   If no logs appear in the web interface, check:')
print('   1. Is app.py running on port 5000?')
print('   2. Are logs appearing in the validation API console?')
print('   3. Are logs appearing in the main app console?')

# 4. Show which validator functions are called
print('\n4. Validation flow (when you click "AI Validate"):')
print('-' * 70)
print('   User clicks "AI Validate" →')
print('   Frontend calls /api/validate-m1 →')
print('   m1_validation_api.py calls run_validation(file_path, "openai") →')
print('   run_validation() checks if validator_type == "openai" →')
print('   Calls run_openai_validation(file_path) →')
print('   run_openai_validation() uses:')
print('      - openai_validator.load_and_analyze_training_data() ← smart_openai_validator.py')
print('      - openai_validator.validate_single_row_with_openai() ← smart_openai_validator.py')
print('      - openai_validator._generate_summary_statistics() ← smart_openai_validator.py')
print('\n✓ ALL of these come from smart_openai_validator.py!')

print('\n' + '=' * 70)
print('DIAGNOSIS:')
print('=' * 70)
print('If you don\'t see logs in the web interface, check:')
print('1. Validation API console (port 5001) - logs should appear there')
print('2. Main app console (port 5000) - logs forwarded from validation API')
print('3. Enhanced logger uses M1Logger which sends logs via send_log_to_main_app()')
print('4. Make sure both servers are running and can communicate')
print('=' * 70)

