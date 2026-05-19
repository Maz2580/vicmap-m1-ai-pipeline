"""
Fast test suite for M1 AI Validator using mocked API calls
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_processing.validator import M1Validator
from data_processing.vicmap_validator import VicmapValidator
from data_processing.comment_analyzer import M1CommentAnalyzer

# Mock responses for testing
MOCK_RESPONSES = {
    'valid_property': {
        'features': [{
            'attributes': {
                'prop_pfi': '12345',
                'prop_propnum': '98765',
                'prop_lga_code': '346',
                'prop_status': 'A'
            }
        }]
    },
    'valid_parcel': {
        'features': [{
            'attributes': {
                'parcel_pfi': '67890',
                'parcel_spi': '1\\TP446069',
                'parcel_lga_code': '346',
                'parcel_status': 'A',
                'parcel_road': 'N'
            }
        }]
    },
    'valid_address': {
        'features': [{
            'attributes': {
                'address_pfi': '11111',
                'house_nbr_1': '42',
                'road_name': 'HIGH',
                'road_type': 'STREET',
                'locality_name': 'EXAMPLECITY',
                'lga_code': '346'
            }
        }]
    },
    'empty': {'features': []},
    'error': {'error': {'message': 'API Error'}}
}


class TestM1ValidatorFast(unittest.TestCase):
    """Fast tests for M1Validator with mocked API calls"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.validator = M1Validator()
        # Mock the VicMap validator to avoid API calls
        self.validator.vicmap_validator = Mock()
    
    def test_missing_required_fields(self):
        """Test detection of missing required fields"""
        row = {'edit_code': 'P'}  # Missing lga_code and comments
        issues = self.validator.validate_row(row)
        
        self.assertTrue(any('lga_code' in issue for issue in issues))
        self.assertTrue(any('comments' in issue for issue in issues))
    
    def test_invalid_edit_code(self):
        """Test handling of invalid edit codes"""
        row = {
            'lga_code': '346',
            'edit_code': 'X',  # Invalid
            'comments': 'Test'
        }
        issues = self.validator.validate_row(row)
        
        self.assertTrue(any('unknown' in issue.lower() for issue in issues))
    
    def test_valid_property_update(self):
        """Test valid property update with mocked VicMap"""
        row = {
            'lga_code': '346',
            'edit_code': 'P',
            'propnum': '12345',
            'property_pfi': '98765',
            'comments': 'Updated property 12345 details'
        }
        
        # Mock VicMap validation
        self.validator.vicmap_validator.validate_propnum.return_value = (True, [])
        self.validator.vicmap_validator.get_property_info.return_value = {
            'prop_propnum': '12345',
            'prop_pfi': '98765'
        }
        
        issues = self.validator.validate_row(row)
        
        # Should have no critical issues
        critical_issues = [i for i in issues if 'required' in i.lower() or 'missing' in i.lower()]
        self.assertEqual(len(critical_issues), 0)
    
    def test_spi_format_validation(self):
        """Test SPI format validation"""
        # Valid SPI formats
        valid_spis = ['1\\TP446069', 'PC354544', '2\\PS904644']
        
        for spi in valid_spis:
            row = {
                'lga_code': '346',
                'edit_code': 'A',
                'spi': spi,
                'propnum': '12345',
                'comments': f'Adding property with SPI {spi}'
            }
            
            # Mock VicMap
            self.validator.vicmap_validator.validate_propnum.return_value = (True, [])
            self.validator.vicmap_validator.validate_spi.return_value = (True, [])
            
            issues = self.validator.validate_row(row)
            spi_issues = [i for i in issues if 'spi' in i.lower() and 'format' in i.lower()]
            self.assertEqual(len(spi_issues), 0, f"Valid SPI {spi} flagged as invalid")
        
        # Invalid SPI format
        row = {
            'lga_code': '346',
            'edit_code': 'A',
            'spi': '123-ABC',  # Invalid
            'propnum': '12345',
            'comments': 'Adding property'
        }
        
        issues = self.validator.validate_row(row)
        self.assertTrue(any('spi' in i.lower() and 'format' in i.lower() for i in issues))
    
    def test_distance_based_address(self):
        """Test distance-based address validation"""
        row = {
            'lga_code': '346',
            'edit_code': 'S',
            'road_name': 'High',
            'road_type': 'ROAD',
            'locality_name': 'Richmond',
            'distance_related_flag': 'Y',
            # Missing easting, northing, datum_proj
            'comments': 'Updated rural address'
        }
        
        issues = self.validator.validate_row(row)
        
        self.assertTrue(any('distance-based' in i.lower() for i in issues))
        self.assertTrue(any('easting' in i.lower() or 'northing' in i.lower() for i in issues))


class TestCommentAnalyzerFast(unittest.TestCase):
    """Fast tests for M1CommentAnalyzer"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.analyzer = M1CommentAnalyzer()
    
    def test_multi_assessment_comment(self):
        """Test multi-assessment comment analysis"""
        row = {'propnum': '12345', 'spi': '1\\TP446069'}
        
        # Good comment
        good_comment = 'Adding property 12345 to multi-assessment with SPI 1\\TP446069'
        issues = self.analyzer.analyze_comment('A', good_comment, row)
        self.assertEqual(len(issues), 0)
        
        # Bad comment
        bad_comment = 'Adding property 12345'
        issues = self.analyzer.analyze_comment('A', bad_comment, row)
        self.assertTrue(any('multi-assessment' in i.lower() for i in issues))
    
    def test_address_update_comment(self):
        """Test address update comment analysis"""
        row = {
            'house_number_1': '42',
            'road_name': 'High',
            'road_type': 'STREET',
            'locality_name': 'Richmond'
        }
        
        # Good comment
        good_comment = 'Updated address to 42 High Street, Richmond'
        issues = self.analyzer.analyze_comment('S', good_comment, row)
        address_issues = [i for i in issues if 'address' in i.lower() and 'should' in i.lower()]
        self.assertEqual(len(address_issues), 0)
        
        # Bad comment
        bad_comment = 'Made some updates'
        issues = self.analyzer.analyze_comment('S', bad_comment, row)
        self.assertTrue(any('address' in i.lower() for i in issues))
    
    def test_empty_comment(self):
        """Test empty comment detection"""
        issues = self.analyzer.analyze_comment('P', '', {})
        self.assertTrue(any('no comment' in i.lower() for i in issues))


class TestVicmapValidatorFast(unittest.TestCase):
    """Fast tests for VicmapValidator with mocked API"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.validator = VicmapValidator()
    
    @patch('requests.get')
    def test_propnum_validation(self, mock_get):
        """Test property number validation"""
        # Mock successful response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = MOCK_RESPONSES['valid_property']
        mock_get.return_value = mock_response
        
        exists, messages = self.validator.validate_propnum('12345')
        
        self.assertTrue(exists)
        self.assertEqual(len(messages), 0)
    
    @patch('requests.get')
    def test_propnum_not_found(self, mock_get):
        """Test property number not found"""
        # Mock empty response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = MOCK_RESPONSES['empty']
        mock_get.return_value = mock_response
        
        exists, messages = self.validator.validate_propnum('999999')
        
        self.assertFalse(exists)
        self.assertTrue(any('not found' in msg.lower() for msg in messages))
    
    @patch('requests.get')
    def test_spi_validation(self, mock_get):
        """Test SPI validation"""
        # Mock successful response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = MOCK_RESPONSES['valid_parcel']
        mock_get.return_value = mock_response
        
        exists, messages = self.validator.validate_spi('1\\TP446069')
        
        self.assertTrue(exists)
        self.assertEqual(len(messages), 0)
    
    @patch('requests.get')
    def test_address_validation(self, mock_get):
        """Test address validation"""
        # Mock successful response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = MOCK_RESPONSES['valid_address']
        mock_get.return_value = mock_response
        
        address_data = {
            'house_number_1': '42',
            'street_name': 'HIGH',
            'street_type': 'STREET',
            'locality_name': 'EXAMPLECITY'
        }
        
        exists, messages = self.validator.validate_address(address_data)
        
        self.assertTrue(exists)
        self.assertEqual(len(messages), 0)
    
    def test_cache_functionality(self):
        """Test caching"""
        self.validator.clear_cache()
        self.assertEqual(len(self.validator.cache), 0)
        
        self.validator.cache['test'] = 'value'
        self.assertEqual(self.validator.cache['test'], 'value')
        
        self.validator.clear_cache()
        self.assertEqual(len(self.validator.cache), 0)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.validator = M1Validator()
        self.validator.vicmap_validator = Mock()
    
    def test_special_characters(self):
        """Test handling of special characters"""
        row = {
            'lga_code': '346',
            'edit_code': 'S',
            'house_number_1': '42A',
            'road_name': "O'Brien",  # Apostrophe
            'road_type': 'STREET',
            'locality_name': 'Richmond',
            'comments': "Updated address to 42A O'Brien Street"
        }
        
        # Mock address validation
        self.validator.vicmap_validator.validate_address.return_value = (True, [])
        
        # Should not crash
        issues = self.validator.validate_row(row)
        self.assertIsInstance(issues, list)
    
    def test_null_values(self):
        """Test handling of None/null values"""
        row = {
            'lga_code': '346',
            'edit_code': 'P',
            'propnum': None,
            'property_pfi': None,
            'comments': None
        }
        
        # Should detect missing values
        issues = self.validator.validate_row(row)
        self.assertTrue(len(issues) > 0)


def run_fast_tests():
    """Run all tests with detailed output"""
    import time
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestM1ValidatorFast))
    suite.addTests(loader.loadTestsFromTestCase(TestCommentAnalyzerFast))
    suite.addTests(loader.loadTestsFromTestCase(TestVicmapValidatorFast))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))
    
    # Run tests with timing
    start_time = time.time()
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    end_time = time.time()
    
    # Print summary
    print("\n" + "="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Time taken: {end_time - start_time:.2f} seconds")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("="*70)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    success = run_fast_tests()
    sys.exit(0 if success else 1)