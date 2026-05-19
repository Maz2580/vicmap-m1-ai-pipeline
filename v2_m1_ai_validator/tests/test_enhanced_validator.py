"""
Test suite for Enhanced M1 Validator with AI features
"""
import unittest
import tempfile
import os
import pandas as pd
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_processing.enhanced_validator import EnhancedM1Validator

class TestEnhancedValidator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up test cases"""
        cls.validator = EnhancedM1Validator()
        
        # Create test M1 data
        cls.test_data = [
            {
                'lga_code': '346',
                'edit_code': 'P',
                'propnum': '112152',
                'property_pfi': '45124878',
                'comments': 'Updated property 112152 details'
            },
            {
                'lga_code': '346',
                'edit_code': 'S',
                'house_number_1': '517',
                'road_name': 'WANDONG',
                'road_type': 'ROAD',
                'locality_name': 'WANDONG',
                'comments': 'Updated address to 517 WANDONG ROAD, WANDONG'
            },
            {
                'lga_code': '328',  # Wrong LGA code
                'edit_code': 'E',
                'propnum': '999999',
                'road_name': 'NEW_ROAD',
                'road_type': 'STREET',
                'locality_name': 'EXAMPLECITY',
                'comments': 'Test record with issues'
            }
        ]
    
    def test_enhanced_validation(self):
        """Test enhanced validation with AI features"""
        # Create temporary CSV file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            df = pd.DataFrame(self.test_data)
            df.to_csv(f.name, index=False)
            temp_file = f.name
        
        try:
            # Run validation
            report = self.validator.validate_m1_file(temp_file, auto_fix=True)
            
            # Check basic structure
            self.assertIn('success', report)
            self.assertIn('summary', report)
            self.assertIn('validation_results', report)
            
            # Check summary
            summary = report['summary']
            self.assertEqual(summary['total_records'], 3)
            self.assertGreaterEqual(summary['valid_records'], 0)
            self.assertGreaterEqual(summary['invalid_records'], 0)
            
            # Check validation results
            self.assertEqual(len(report['validation_results']), 3)
            
            # Check AI insights
            self.assertIn('ai_insights', report)
            self.assertIn('suggestions', report['ai_insights'])
            
        finally:
            # Clean up
            os.unlink(temp_file)
    
    def test_field_mapping_analysis(self):
        """Test field mapping analysis"""
        record = {
            'lga_code': '346',
            'edit_code': 'P',
            'propnum': '112152',
            'house_nbr_1': '123',  # Wrong field name
            'street_name': 'MAIN',  # Wrong field name
            'comments': 'Test record'
        }
        
        result = self.validator._validate_record_with_ai(record, 0, auto_fix=False)
        
        # Check field mappings
        self.assertIn('field_mappings', result)
        
        # Check for field mapping issues
        address_mappings = result['field_mappings'].get('address', {})
        if 'house_nbr_1' in address_mappings:
            self.assertFalse(address_mappings['house_nbr_1']['is_valid'])
            self.assertEqual(address_mappings['house_nbr_1']['correct_field'], 'house_number_1')
    
    def test_error_recovery(self):
        """Test error recovery system"""
        record = {
            'lga_code': '328',  # Wrong LGA code
            'edit_code': 'S',
            'road_name': 'NEW_ROAD',
            'road_type': 'STREET',
            'locality_name': 'EXAMPLECITY',
            'comments': 'Test record'
        }
        
        result = self.validator._validate_record_with_ai(record, 0, auto_fix=True)
        
        # Check for auto-fixes
        self.assertIn('auto_fixes', result)
        
        # Check for suggestions
        self.assertIn('suggestions', result)
        self.assertGreater(len(result['suggestions']), 0)
    
    def test_comment_enhancement(self):
        """Test comment enhancement"""
        record = {
            'lga_code': '346',
            'edit_code': 'P',
            'propnum': '112152',
            'comments': 'Update property'  # Basic comment
        }
        
        result = self.validator._validate_record_with_ai(record, 0, auto_fix=False)
        
        # Check for enhanced comment
        self.assertIn('enhanced_comment', result)
        if result['enhanced_comment']:
            self.assertIn('112152', result['enhanced_comment'])
            self.assertIn('property', result['enhanced_comment'].lower())
    
    def test_validation_report_generation(self):
        """Test validation report generation"""
        # Create test validation results
        validation_results = [
            {
                'index': 0,
                'record': self.test_data[0],
                'issues': [],
                'suggestions': [],
                'auto_fixes': {},
                'enhanced_comment': None,
                'field_mappings': {},
                'validation_passed': True
            },
            {
                'index': 1,
                'record': self.test_data[1],
                'issues': ['Property not found'],
                'suggestions': ['Check property number'],
                'auto_fixes': {'lga_code': '346'},
                'enhanced_comment': 'Enhanced comment',
                'field_mappings': {},
                'validation_passed': False
            }
        ]
        
        errors = [(self.test_data[1], ['Property not found'])]
        
        report = self.validator._generate_validation_report(validation_results, errors)
        
        # Check report structure
        self.assertIn('success', report)
        self.assertIn('summary', report)
        self.assertIn('error_analysis', report)
        self.assertIn('ai_insights', report)
        self.assertIn('recommendations', report)
        
        # Check summary
        summary = report['summary']
        self.assertEqual(summary['total_records'], 2)
        self.assertEqual(summary['valid_records'], 1)
        self.assertEqual(summary['invalid_records'], 1)
    
    def test_export_validation_report(self):
        """Test validation report export"""
        # Create test report
        report = {
            'success': True,
            'summary': {
                'total_records': 2,
                'valid_records': 1,
                'invalid_records': 1,
                'auto_fixed': 0,
                'manual_review_required': 1,
                'validation_rate': 50.0,
                'processing_time': 1.5
            },
            'error_analysis': {
                'error_types': {'not_found': 1},
                'common_issues': ['not_found: 1 occurrences'],
                'error_recovery_report': {}
            },
            'ai_insights': {
                'field_mapping_issues': {'total_fields_analyzed': 10, 'mapping_issues': 0, 'mapping_accuracy': 100.0},
                'comment_quality': {'total_comments': 2, 'empty_comments': 0, 'short_comments': 0, 'average_length': 25.0, 'quality_score': 80.0, 'improvements_needed': []},
                'suggestions': ['1 records can be auto-fixed']
            },
            'validation_results': [],
            'recommendations': ['Validation rate is below 80% - review common error patterns']
        }
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            temp_file = f.name
        
        try:
            # Export report
            self.validator.export_validation_report(report, temp_file)
            
            # Check file was created
            self.assertTrue(os.path.exists(temp_file))
            
            # Check file content
            with open(temp_file, 'r', encoding='utf-8') as f:
                content = f.read()
                self.assertIn('M1 Validation Report', content)
                self.assertIn('Total Records: 2', content)
                self.assertIn('Valid Records: 1', content)
                self.assertIn('Invalid Records: 1', content)
        
        finally:
            # Clean up
            if os.path.exists(temp_file):
                os.unlink(temp_file)

if __name__ == '__main__':
    unittest.main()
