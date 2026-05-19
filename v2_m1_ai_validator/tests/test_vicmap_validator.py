"""
Tests for VicMap Validator
"""
import unittest
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_processing.vicmap_validator import VicmapValidator

class TestVicmapValidator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up test cases - runs once for the whole test suite"""
        logging.basicConfig(level=logging.INFO)
        cls.validator = VicmapValidator()

    def test_propnum_validation(self):
        """Test property number validation"""
        # Test with known valid property
        messages = self.validator.validate_propnum('39742')  # Known valid propnum from test data
        self.assertEqual(messages, [])
        
        # Test with invalid property
        messages = self.validator.validate_propnum('999999999')
        self.assertTrue(len(messages) > 0)
        self.assertTrue(any('not found' in msg.lower() for msg in messages))

    def test_spi_validation(self):
        """Test SPI validation"""
        # Test with known valid SPI - from test_vicmap_access.py data
        messages = self.validator.validate_spi('2\\PS904644')  # Known valid SPI
        self.assertEqual(messages, [])
        
        # Test with road parcel - from test_vicmap_access.py data
        messages = self.validator.validate_spi('R55\\PS617320')
        self.assertEqual(messages, ['Road parcel identified'])
        
        # Test with invalid SPI
        messages = self.validator.validate_spi('999\\INVALID')
        self.assertTrue(len(messages) > 0)
        self.assertTrue(any('not found' in msg.lower() for msg in messages))

    def test_address_validation(self):
        """Test address validation"""
        # Test with known valid address - Using structure from test_vicmap_access.py
        messages = self.validator.validate_address({
            'house_number_1': '1',
            'street_name': 'HIGH',
            'locality_name': 'EXAMPLECITY',
            'street_type': 'STREET'
        })
        self.assertEqual(messages, [])
        
        # Test with invalid address
        messages = self.validator.validate_address({
            'house_number_1': '99999',
            'street_name': 'NONEXISTENT',
            'locality_name': 'EXAMPLECITY'
        })
        self.assertTrue(len(messages) > 0)
        self.assertTrue(any('not found' in msg.lower() for msg in messages))
        
        # Test partial address match - using a known road from Shepparton
        messages = self.validator.validate_address({
            'house_number_1': '1',
            'street_name': 'WYNDHA',  # Partial match for WYNDHAM
            'locality_name': 'EXAMPLECITY'
        })
        self.assertTrue(any('similar road names' in msg.lower() for msg in messages))

    def test_property_info(self):
        """Test property info retrieval"""
        # Test with known valid PFI - from test_vicmap_access.py data
        info = self.validator.get_property_info('125250354')  # Known PFI
        self.assertIsNotNone(info)
        if info:
            self.assertIsInstance(info, dict)
            self.assertIn('prop_pfi', info)
            self.assertIn('parcel_status', info)
        
        # Test with invalid PFI
        info = self.validator.get_property_info('999999999')
        self.assertIsNone(info)

    def test_caching(self):
        """Test caching functionality"""
        # Clear cache first
        self.validator.clear_cache()
        
        # Test property info caching
        pfi = '125250354'  # Known valid PFI from test data
        info1 = self.validator.get_property_info(pfi)
        info2 = self.validator.get_property_info(pfi)
        self.assertIsNotNone(info1)
        self.assertEqual(info1, info2)  # Should get same data from cache
        
        # Test address validation caching
        addr_data = {
            'house_number_1': '1',
            'street_name': 'HIGH',
            'locality_name': 'EXAMPLECITY',
            'street_type': 'STREET'
        }
        self.validator.validate_address(addr_data)
        cache_key = f"address_1_HIGH_STREET_EXAMPLECITY"
        self.assertIn(cache_key, self.validator.cache)
        
        # Test cache clearing
        self.validator.clear_cache()
        self.assertEqual(len(self.validator.cache), 0)

if __name__ == '__main__':
    unittest.main()