"""
Demo script for Enhanced M1 Validator with AI features
Shows how to use the enhanced validation system
"""
import os
import sys
import pandas as pd
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from data_processing.enhanced_validator import EnhancedM1Validator

# Neutral placeholder LGA code for demo fixtures (not a real Victorian council code)
TEST_LGA_CODE = "999"

def create_sample_m1_data():
    """Create sample M1 data for demonstration"""
    sample_data = [
        {
            'lga_code': TEST_LGA_CODE,
            'edit_code': 'P',
            'propnum': '112152',
            'property_pfi': '45124878',
            'comments': 'Updated property 112152 details'
        },
        {
            'lga_code': TEST_LGA_CODE,
            'edit_code': 'S',
            'house_number_1': '517',
            'road_name': 'WANDONG',
            'road_type': 'ROAD',
            'locality_name': 'WANDONG',
            'comments': 'Updated address to 517 WANDONG ROAD, WANDONG'
        },
        {
            'lga_code': TEST_LGA_CODE,
            'edit_code': 'E',
            'propnum': '999999',
            'road_name': 'NEW_ROAD',
            'road_type': 'STREET',
            'locality_name': 'EXAMPLECITY',
            'comments': 'Test record with issues'
        },
        {
            'lga_code': TEST_LGA_CODE,
            'edit_code': 'A',
            'propnum': '107551',
            'spi': '90\\PS844324',
            'property_pfi': '45132363',
            'comments': 'Adding property to multi-assessment'
        },
        {
            'lga_code': TEST_LGA_CODE,
            'edit_code': 'C',
            'crefno': '12345',
            'spi': '1\\TP446069',
            'comments': 'Updating crefno'
        }
    ]
    
    return sample_data

def run_demo():
    """Run the enhanced validation demo"""
    print("🚀 Enhanced M1 Validator with AI Features - Demo")
    print("=" * 60)
    
    # Create sample data
    print("\n📊 Creating sample M1 data...")
    sample_data = create_sample_m1_data()
    
    # Save to CSV
    df = pd.DataFrame(sample_data)
    csv_file = 'demo_m1_data.csv'
    df.to_csv(csv_file, index=False)
    print(f"✅ Sample data saved to {csv_file}")
    
    # Initialize enhanced validator
    print("\n🤖 Initializing Enhanced M1 Validator...")
    validator = EnhancedM1Validator()
    
    # Run validation
    print("\n🔍 Running validation with AI enhancements...")
    try:
        report = validator.validate_m1_file(csv_file, auto_fix=True)
        
        # Display results
        print("\n📋 VALIDATION RESULTS")
        print("-" * 40)
        
        summary = report['summary']
        print(f"Total Records: {summary['total_records']}")
        print(f"Valid Records: {summary['valid_records']}")
        print(f"Invalid Records: {summary['invalid_records']}")
        print(f"Auto-fixed: {summary['auto_fixed']}")
        print(f"Manual Review Required: {summary['manual_review_required']}")
        print(f"Validation Rate: {summary['validation_rate']:.1f}%")
        print(f"Processing Time: {summary['processing_time']:.2f} seconds")
        
        # Display error analysis
        print("\n🔍 ERROR ANALYSIS")
        print("-" * 40)
        error_types = report['error_analysis']['error_types']
        if error_types:
            for error_type, count in error_types.items():
                print(f"{error_type}: {count} occurrences")
        else:
            print("No errors found!")
        
        # Display AI insights
        print("\n🧠 AI INSIGHTS")
        print("-" * 40)
        ai_insights = report['ai_insights']
        
        # Field mapping analysis
        field_mapping = ai_insights['field_mapping_issues']
        print(f"Field Mapping Accuracy: {field_mapping['mapping_accuracy']:.1f}%")
        
        # Comment quality
        comment_quality = ai_insights['comment_quality']
        print(f"Comment Quality Score: {comment_quality['quality_score']:.1f}%")
        
        # Suggestions
        suggestions = ai_insights['suggestions']
        if suggestions:
            print("\nSuggestions:")
            for suggestion in suggestions:
                print(f"  - {suggestion}")
        
        # Display detailed results
        print("\n📝 DETAILED RESULTS")
        print("-" * 40)
        for result in report['validation_results']:
            print(f"\nRecord {result['index']}:")
            print(f"  Edit Code: {result['record']['edit_code']}")
            print(f"  Validation: {'✅ PASSED' if result['validation_passed'] else '❌ FAILED'}")
            
            if result['issues']:
                print("  Issues:")
                for issue in result['issues']:
                    print(f"    - {issue}")
            
            if result['suggestions']:
                print("  Suggestions:")
                for suggestion in result['suggestions']:
                    print(f"    - {suggestion}")
            
            if result['auto_fixes']:
                print("  Auto-fixes applied:")
                for field, value in result['auto_fixes'].items():
                    if not field.startswith('_'):
                        print(f"    - {field}: {value}")
            
            if result['enhanced_comment']:
                print(f"  Enhanced Comment: {result['enhanced_comment']}")
        
        # Display recommendations
        print("\n💡 RECOMMENDATIONS")
        print("-" * 40)
        recommendations = report['recommendations']
        if recommendations:
            for recommendation in recommendations:
                print(f"- {recommendation}")
        else:
            print("No specific recommendations at this time.")
        
        # Export detailed report
        print("\n📄 Exporting detailed report...")
        report_file = 'enhanced_validation_report.txt'
        validator.export_validation_report(report, report_file)
        print(f"✅ Detailed report saved to {report_file}")
        
    except Exception as e:
        print(f"❌ Error during validation: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up
        if os.path.exists(csv_file):
            os.unlink(csv_file)
            print(f"\n🧹 Cleaned up {csv_file}")

def demonstrate_ai_features():
    """Demonstrate specific AI features"""
    print("\n🎯 AI FEATURES DEMONSTRATION")
    print("=" * 60)
    
    validator = EnhancedM1Validator()
    
    # Test field mapping
    print("\n1. Field Mapping Analysis")
    print("-" * 30)
    test_record = {
        'lga_code': '000',
        'edit_code': 'S',
        'house_nbr_1': '123',  # Wrong field name
        'street_name': 'MAIN',  # Wrong field name
        'street_type': 'STREET',  # Wrong field name
        'locality_name': 'EXAMPLECITY'
    }
    
    result = validator._validate_record_with_ai(test_record, 0, auto_fix=False)
    field_mappings = result['field_mappings']
    
    if 'address' in field_mappings:
        print("Address field mappings:")
        for field, analysis in field_mappings['address'].items():
            status = "✅" if analysis['is_valid'] else "❌"
            print(f"  {status} {field} -> {analysis['correct_field']}")
            if analysis['suggestions']:
                print(f"    Suggestions: {', '.join(analysis['suggestions'])}")
    
    # Test comment enhancement
    print("\n2. Comment Enhancement")
    print("-" * 30)
    test_record = {
        'lga_code': '000',
        'edit_code': 'P',
        'propnum': '112152',
        'comments': 'Update property'  # Basic comment
    }
    
    result = validator._validate_record_with_ai(test_record, 0, auto_fix=False)
    if result['enhanced_comment']:
        print(f"Original: {test_record['comments']}")
        print(f"Enhanced: {result['enhanced_comment']}")
    
    # Test error recovery
    print("\n3. Error Recovery")
    print("-" * 30)
    test_record = {
        'lga_code': TEST_LGA_CODE,
        'edit_code': 'S',
        'road_name': 'NEW_ROAD',
        'road_type': 'STREET',
        'locality_name': 'EXAMPLECITY',
        'comments': 'Test record'
    }
    
    result = validator._validate_record_with_ai(test_record, 0, auto_fix=True)
    if result['auto_fixes']:
        print("Auto-fixes applied:")
        for field, value in result['auto_fixes'].items():
            if not field.startswith('_'):
                print(f"  - {field}: {value}")
    
    if result['suggestions']:
        print("Suggestions:")
        for suggestion in result['suggestions']:
            print(f"  - {suggestion}")

if __name__ == '__main__':
    print("🎉 Welcome to the Enhanced M1 Validator Demo!")
    print("This demo showcases AI-powered features for M1 validation.")
    
    try:
        # Run main demo
        run_demo()
        
        # Demonstrate AI features
        demonstrate_ai_features()
        
        print("\n🎊 Demo completed successfully!")
        print("\nKey Features Demonstrated:")
        print("✅ AI-powered field mapping")
        print("✅ Intelligent error recovery")
        print("✅ Comment enhancement")
        print("✅ Comprehensive validation reporting")
        print("✅ Auto-fix capabilities")
        
    except KeyboardInterrupt:
        print("\n\n👋 Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
