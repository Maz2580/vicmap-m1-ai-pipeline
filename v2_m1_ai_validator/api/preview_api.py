"""
Preview API for M1 Automation System
Provides endpoints for data preview functionality
"""

import os
import sys
import json
import pandas as pd
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import logging

# Make the project root importable so we can pull in the shared
# `utils.auth` helper below.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.append(_PROJECT_ROOT)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# CORS: configured via the ALLOWED_ORIGINS env var (comma-separated).
# Default empty list disables CORS entirely. Security audit H-1.
_allowed = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if _allowed:
    CORS(app, origins=_allowed)

# Bearer-token authentication. Set API_TOKEN in .env to enable.
# Security audit C-1.
from utils.auth import register_auth
register_auth(app)

# Global variables to store current data
current_pozi_data = None
current_validation_data = None

# Historical reports storage
historical_reports = {
    'pozi_reports': {},
    'validation_reports': {}
}

@app.route('/api/preview/pozi', methods=['POST'])
def upload_pozi_preview():
    """Upload and preview POZI CSV data"""
    global current_pozi_data
    
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
        current_pozi_data = df.to_dict('records')
        
        # Return preview data
        preview_data = {
            'filename': file.filename,
            'total_rows': len(df),
            'total_columns': len(df.columns),
            'columns': list(df.columns),
            'sample_data': df.head(10).to_dict('records'),
            'data_types': df.dtypes.astype(str).to_dict()
        }
        
        logger.info(f"POZI data uploaded: {file.filename}, {len(df)} rows, {len(df.columns)} columns")
        return jsonify(preview_data)
        
    except Exception as e:
        logger.error(f"Error uploading POZI data: {str(e)}")
        return jsonify({'error': f'Error processing file: {str(e)}'}), 500

@app.route('/api/preview/pozi/data', methods=['GET'])
def get_pozi_data():
    """Get POZI data for preview"""
    global current_pozi_data
    
    if current_pozi_data is None:
        return jsonify({'error': 'No POZI data available'}), 404
    
    try:
        # Get pagination parameters
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        
        # Calculate pagination
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        
        # Get data slice
        data_slice = current_pozi_data[start_idx:end_idx]
        
        response_data = {
            'data': data_slice,
            'total_rows': len(current_pozi_data),
            'page': page,
            'per_page': per_page,
            'total_pages': (len(current_pozi_data) + per_page - 1) // per_page
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error getting POZI data: {str(e)}")
        return jsonify({'error': f'Error retrieving data: {str(e)}'}), 500

@app.route('/api/preview/validation', methods=['POST'])
def upload_validation_preview():
    """Upload and preview AI validation results"""
    global current_validation_data
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No validation data provided'}), 400
        
        current_validation_data = data
        
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
        
        preview_data = {
            'total_rows': total_rows,
            'kept_count': kept_count,
            'rejected_count': rejected_count,
            'unique_reasons': unique_reasons,
            'sample_data': data[:10]  # First 10 rows
        }
        
        logger.info(f"Validation data uploaded: {total_rows} rows, {kept_count} kept, {rejected_count} rejected")
        return jsonify(preview_data)
        
    except Exception as e:
        logger.error(f"Error uploading validation data: {str(e)}")
        return jsonify({'error': f'Error processing validation data: {str(e)}'}), 500

@app.route('/api/preview/validation/data', methods=['GET'])
def get_validation_data():
    """Get validation data for preview"""
    global current_validation_data
    
    if current_validation_data is None:
        return jsonify({'error': 'No validation data available'}), 404
    
    try:
        # Get pagination parameters
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        
        # Calculate pagination
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        
        # Get data slice
        data_slice = current_validation_data[start_idx:end_idx]
        
        response_data = {
            'data': data_slice,
            'total_rows': len(current_validation_data),
            'page': page,
            'per_page': per_page,
            'total_pages': (len(current_validation_data) + per_page - 1) // per_page
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error getting validation data: {str(e)}")
        return jsonify({'error': f'Error retrieving data: {str(e)}'}), 500

@app.route('/api/preview/summary', methods=['GET'])
def get_preview_summary():
    """Get summary of current preview data"""
    global current_pozi_data, current_validation_data
    
    summary = {
        'pozi_data': {
            'available': current_pozi_data is not None,
            'rows': len(current_pozi_data) if current_pozi_data else 0,
            'columns': len(current_pozi_data[0]) if current_pozi_data and len(current_pozi_data) > 0 else 0
        },
        'validation_data': {
            'available': current_validation_data is not None,
            'rows': len(current_validation_data) if current_validation_data else 0,
            'kept': sum(1 for row in current_validation_data if row.get('decision') == 'KEEP') if current_validation_data else 0,
            'rejected': sum(1 for row in current_validation_data if row.get('decision') == 'REJECT') if current_validation_data else 0
        }
    }
    
    return jsonify(summary)

@app.route('/api/preview/export/pozi', methods=['GET'])
def export_pozi_data():
    """Export POZI data as CSV"""
    global current_pozi_data
    
    if current_pozi_data is None:
        return jsonify({'error': 'No POZI data available'}), 404
    
    try:
        # Create DataFrame and export
        df = pd.DataFrame(current_pozi_data)
        output_path = 'temp_pozi_export.csv'
        df.to_csv(output_path, index=False)
        
        return send_file(output_path, as_attachment=True, download_name='pozi_data_export.csv')
        
    except Exception as e:
        logger.error(f"Error exporting POZI data: {str(e)}")
        return jsonify({'error': f'Error exporting data: {str(e)}'}), 500

@app.route('/api/preview/export/validation', methods=['GET'])
def export_validation_data():
    """Export validation data as CSV"""
    global current_validation_data
    
    if current_validation_data is None:
        return jsonify({'error': 'No validation data available'}), 404
    
    try:
        # Create DataFrame and export
        df = pd.DataFrame(current_validation_data)
        output_path = 'temp_validation_export.csv'
        df.to_csv(output_path, index=False)
        
        return send_file(output_path, as_attachment=True, download_name='validation_results_export.csv')
        
    except Exception as e:
        logger.error(f"Error exporting validation data: {str(e)}")
        return jsonify({'error': f'Error exporting data: {str(e)}'}), 500

@app.route('/api/preview/clear', methods=['POST'])
def clear_preview_data():
    """Clear all preview data"""
    global current_pozi_data, current_validation_data
    
    current_pozi_data = None
    current_validation_data = None
    
    logger.info("Preview data cleared")
    return jsonify({'message': 'Preview data cleared successfully'})

# Historical Reports Endpoints
@app.route('/api/reports/list', methods=['GET'])
def list_historical_reports():
    """List all available historical reports"""
    global historical_reports
    
    try:
        # Scan for available reports
        import os
        import glob
        
        # Get the project root directory (two levels up from this API file)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        logger.info(f"Project root directory: {project_root}")
        
        # Change to project root directory for file discovery
        original_cwd = os.getcwd()
        os.chdir(project_root)
        logger.info(f"Changed to directory: {os.getcwd()}")
        
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
                    logger.info(f"Added known POZI file: {file_path}")
            
            for file_path in known_validation_files:
                if os.path.exists(file_path) and file_path not in validation_files:
                    validation_files.append(file_path)
                    logger.info(f"Added known validation file: {file_path}")
            
            logger.info(f"Found {len(pozi_files)} POZI files: {pozi_files}")
            logger.info(f"Found {len(validation_files)} validation files: {validation_files}")
                    
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
    global current_pozi_data, historical_reports
    
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
        current_pozi_data = df.to_dict('records')
        
        # Store in historical reports
        report_id = os.path.basename(file_path)
        historical_reports['pozi_reports'][report_id] = {
            'data': current_pozi_data,
            'metadata': {
                'filename': report_id,
                'total_rows': len(df),
                'total_columns': len(df.columns),
                'columns': list(df.columns),
                'loaded_at': pd.Timestamp.now().isoformat()
            }
        }
        
        # Return preview data
        preview_info = {
            'filename': report_id,
            'total_rows': len(df),
            'total_columns': len(df.columns),
            'columns': list(df.columns),
            'sample_data': df.head(10).to_dict('records'),
            'data_types': df.dtypes.astype(str).to_dict(),
            'source': 'historical'
        }
        
        logger.info(f"Historical POZI report loaded: {report_id}, {len(df)} rows, {len(df.columns)} columns")
        return jsonify(preview_info)
        
    except Exception as e:
        logger.error(f"Error loading historical POZI report: {str(e)}")
        return jsonify({'error': f'Error loading report: {str(e)}'}), 500

@app.route('/api/reports/load/validation', methods=['POST'])
def load_historical_validation():
    """Load historical validation report"""
    global current_validation_data, historical_reports
    
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
        
        current_validation_data = validation_data
        
        # Store in historical reports
        report_id = os.path.basename(file_path)
        historical_reports['validation_reports'][report_id] = {
            'data': current_validation_data,
            'metadata': {
                'filename': report_id,
                'total_rows': len(validation_data),
                'loaded_at': pd.Timestamp.now().isoformat()
            }
        }
        
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
            'filename': report_id,
            'total_rows': total_rows,
            'kept_count': kept_count,
            'rejected_count': rejected_count,
            'unique_reasons': unique_reasons,
            'sample_data': validation_data[:10],
            'source': 'historical'
        }
        
        logger.info(f"Historical validation report loaded: {report_id}, {total_rows} rows, {kept_count} kept, {rejected_count} rejected")
        return jsonify(preview_info)
        
    except Exception as e:
        logger.error(f"Error loading historical validation report: {str(e)}")
        return jsonify({'error': f'Error loading report: {str(e)}'}), 500

@app.route('/api/reports/demo', methods=['POST'])
def load_demo_data():
    """Load demo data for demonstration"""
    global current_pozi_data, current_validation_data
    
    try:
        # Get the project root directory
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # Load demo POZI data
        pozi_file = os.path.join(project_root, os.getenv("SAMPLE_M1_CSV", "tests/fixtures/sample_m1.csv"))
        if os.path.exists(pozi_file):
            df_pozi = pd.read_csv(pozi_file)
            current_pozi_data = df_pozi.to_dict('records')
            
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
            current_validation_data = validation_data
            
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
    app.run(debug=True, host='0.0.0.0', port=5002)
