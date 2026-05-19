#!/usr/bin/env python3
"""
Demo script to showcase the AI M1 Validation integration
"""
import requests
import json
import time
import os
from datetime import datetime

# Configuration
API_BASE_URL = "http://localhost:5001"
MAIN_APP_URL = "http://localhost:5000"

def test_api_health():
    """Test if the AI validation API is running"""
    try:
        response = requests.get(f"{API_BASE_URL}/api/health", timeout=5)
        if response.status_code == 200:
            print("✅ AI Validation API is running")
            return True
        else:
            print(f"❌ AI Validation API returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ AI Validation API is not running. Please start it first.")
        return False
    except Exception as e:
        print(f"❌ Error testing API health: {e}")
        return False

def test_main_app():
    """Test if the main M1 automation app is running"""
    try:
        response = requests.get(f"{MAIN_APP_URL}/", timeout=5)
        if response.status_code == 200:
            print("✅ Main M1 Automation System is running")
            return True
        else:
            print(f"❌ Main app returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Main M1 Automation System is not running. Please start it first.")
        return False
    except Exception as e:
        print(f"❌ Error testing main app: {e}")
        return False

def demo_field_mapping():
    """Demo AI field mapping suggestions"""
    print("\n🔍 Testing AI Field Mapping...")
    
    test_cases = [
        {"field_name": "house_nbr_1", "layer_type": "address"},
        {"field_name": "street_name", "layer_type": "address"},
        {"field_name": "propnum", "layer_type": "property"},
        {"field_name": "spi", "layer_type": "parcel"}
    ]
    
    for case in test_cases:
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/field-mapping-suggestions",
                json=case,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"  ✅ {case['field_name']} -> {data.get('suggestions', {}).get('correct_field', 'N/A')}")
            else:
                print(f"  ❌ Failed to get suggestions for {case['field_name']}")
                
        except Exception as e:
            print(f"  ❌ Error testing {case['field_name']}: {e}")

def demo_error_recovery():
    """Demo AI error recovery suggestions"""
    print("\n🔧 Testing AI Error Recovery...")
    
    test_errors = [
        "M1 Road-Locality combination does not exist and not a new road",
        "Cannot Determine Property Pfi > 1 Property Found For Parcel Identifier",
        "Invalid SPI format",
        "Property number not found"
    ]
    
    for error in test_errors:
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/error-recovery",
                json={
                    "error_message": error,
                    "record_data": {"lga_code": "346", "road_name": "TEST ROAD"}
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                analysis = data.get('analysis', {})
                print(f"  ✅ Error: {error[:50]}...")
                print(f"     Solution: {analysis.get('suggested_solution', 'N/A')[:100]}...")
            else:
                print(f"  ❌ Failed to analyze error: {error[:50]}...")
                
        except Exception as e:
            print(f"  ❌ Error testing error recovery: {e}")

def demo_comment_enhancement():
    """Demo AI comment enhancement"""
    print("\n💬 Testing AI Comment Enhancement...")
    
    test_cases = [
        {
            "edit_code": "A",
            "comment": "New property",
            "row_data": {"propnum": "12345", "road_name": "MAIN STREET"}
        },
        {
            "edit_code": "B",
            "comment": "Update address",
            "row_data": {"property_pfi": "67890", "house_number_1": "123"}
        }
    ]
    
    for case in test_cases:
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/comment-enhancement",
                json=case,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"  ✅ Edit Code {case['edit_code']}:")
                print(f"     Original: {case['comment']}")
                print(f"     Enhanced: {data.get('enhanced_comment', 'N/A')[:100]}...")
                print(f"     Quality Score: {data.get('quality_score', 'N/A')}")
            else:
                print(f"  ❌ Failed to enhance comment for edit code {case['edit_code']}")
                
        except Exception as e:
            print(f"  ❌ Error testing comment enhancement: {e}")

def demo_validation_with_sample_data():
    """Demo validation with sample M1 data"""
    print("\n📊 Testing M1 Validation with Sample Data...")
    
    # Check if we have sample data
    sample_files = [
        "M1_documentation_and_train_data/trainning_data/Sample_of_passed_by_VES",
        "M1_documentation_and_train_data/trainning_data/Sample_of_failed_by_VES",
        "M1_documentation_and_train_data/trainning_data/Sample_generated_by_POZI_not_checked"
    ]
    
    sample_file = None
    for folder in sample_files:
        if os.path.exists(folder):
            csv_files = [f for f in os.listdir(folder) if f.endswith('.csv')]
            if csv_files:
                sample_file = os.path.join(folder, csv_files[0])
                break
    
    if not sample_file:
        print("  ⚠️  No sample M1 files found. Skipping validation demo.")
        return
    
    print(f"  📁 Using sample file: {sample_file}")
    
    try:
        # Start validation
        response = requests.post(
            f"{API_BASE_URL}/api/validate-m1",
            json={"file_path": sample_file},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'started':
                print("  ✅ Validation started successfully")
                print("  ⏳ Monitoring validation progress...")
                
                # Monitor progress
                for i in range(30):  # Monitor for up to 1 minute
                    time.sleep(2)
                    
                    status_response = requests.get(f"{API_BASE_URL}/api/validation-status")
                    if status_response.status_code == 200:
                        status = status_response.json()
                        
                        if status.get('is_running'):
                            progress = status.get('progress', 0)
                            operation = status.get('current_operation', 'Processing...')
                            print(f"    Progress: {progress}% - {operation}")
                        else:
                            print("  ✅ Validation completed!")
                            
                            # Get results
                            results_response = requests.get(f"{API_BASE_URL}/api/validation-results")
                            if results_response.status_code == 200:
                                results = results_response.json()
                                summary = results.get('summary', {})
                                print(f"    📈 Validation Rate: {summary.get('validation_rate', 'N/A')}")
                                print(f"    🔧 Auto-fixes Applied: {summary.get('auto_fixes_applied', 'N/A')}")
                                print(f"    ⚠️  Errors Found: {summary.get('total_errors', 'N/A')}")
                            break
                    else:
                        print(f"    ❌ Error checking status: {status_response.status_code}")
            else:
                print(f"  ❌ Failed to start validation: {data.get('error', 'Unknown error')}")
        else:
            print(f"  ❌ Failed to start validation: {response.status_code}")
            
    except Exception as e:
        print(f"  ❌ Error during validation demo: {e}")

def print_integration_summary():
    """Print a summary of the integration"""
    print("\n" + "="*60)
    print("🎉 AI M1 VALIDATION INTEGRATION SUMMARY")
    print("="*60)
    print()
    print("✅ Backend API: Flask-based AI validation service")
    print("✅ Frontend Integration: Enhanced HTML with AI components")
    print("✅ Real-time Monitoring: Live validation feed")
    print("✅ AI Insights Dashboard: Metrics and analytics")
    print("✅ Field Mapping: AI-powered field name suggestions")
    print("✅ Error Recovery: Intelligent error analysis and fixes")
    print("✅ Comment Enhancement: AI-improved M1 comments")
    print("✅ Export Features: JSON/CSV report generation")
    print()
    print("🚀 Ready to use! Start both services and visit:")
    print(f"   Main System: {MAIN_APP_URL}")
    print(f"   AI API: {API_BASE_URL}")
    print()
    print("📚 See AI_VALIDATION_INTEGRATION_GUIDE.md for details")

def main():
    """Main demo function"""
    print("🤖 AI M1 Validation Integration Demo")
    print("="*50)
    
    # Test services
    api_healthy = test_api_health()
    main_healthy = test_main_app()
    
    if not api_healthy or not main_healthy:
        print("\n❌ Please start both services before running this demo:")
        print("   1. python v2_m1_ai_validator/api/m1_validation_api.py")
        print("   2. python app.py")
        print("\n   Or use: start_ai_validation.bat")
        return
    
    # Run demos
    demo_field_mapping()
    demo_error_recovery()
    demo_comment_enhancement()
    demo_validation_with_sample_data()
    
    # Print summary
    print_integration_summary()

if __name__ == "__main__":
    main()
