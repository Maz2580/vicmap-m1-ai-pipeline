"""
Integration tests for M1 AI Validator
"""
import sys
import os
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from data_processing.validator import M1Validator

# Neutral placeholder LGA code for fixtures (not a real Victorian council code)
TEST_LGA_CODE = "999"

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def run_test_case(validator, test_case, test_name, expect_issues=False):
    """Helper function to run a test case and print results"""
    print(f"\n{test_name}:")
    issues = validator.validate_row(test_case)
    if expect_issues:
        if issues:
            print("Expected issues found:", issues)
        else:
            print("ERROR: Expected issues but found none")
    else:
        if issues:
            print("Unexpected issues found:", issues)
        else:
            print("Passed ✓")
    return issues

def test_spi_validation():
    validator = M1Validator()
    print("\nTesting SPI Validation:")
    
    # Test Case 1: Valid SPI with plan number
    test_case = {
        'lga_code': TEST_LGA_CODE,
        'edit_code': 'A',
        'propnum': '12345',
        'spi': '1\\TP446069',
        'comments': 'Adding property 12345 with SPI: 1\\TP446069 to multi-assessment'
    }
    run_test_case(validator, test_case, "Test 1 - Valid SPI with plan number")
    
    # Test Case 2: Valid SPI without plan number
    test_case = {
        'lga_code': TEST_LGA_CODE,
        'edit_code': 'A',
        'propnum': '12345',
        'spi': 'PC354544',
        'comments': 'Adding property 12345 with SPI: PC354544 to multi-assessment'
    }
    run_test_case(validator, test_case, "Test 2 - Valid SPI without plan number")
    
    # Test Case 3: Invalid SPI format
    test_case = {
        'lga_code': TEST_LGA_CODE,
        'edit_code': 'A',
        'propnum': '12345',
        'spi': '123-ABC',  # Invalid format
        'comments': 'Adding property with invalid SPI'
    }
    run_test_case(validator, test_case, "Test 3 - Invalid SPI format", expect_issues=True)

def test_address_validation():
    validator = M1Validator()
    print("\nTesting Address Validation:")
    
    # Test Case 1: Complete urban address
    test_case = {
        'lga_code': TEST_LGA_CODE,
        'edit_code': 'S',
        'house_number_1': '42',
        'road_name': 'High',
        'road_type': 'STREET',
        'locality_name': 'Richmond',
        'comments': 'Updated address to 42 High Street, Richmond'
    }
    run_test_case(validator, test_case, "Test 1 - Complete urban address")
    
    # Test Case 2: Rural address with distance
    test_case = {
        'lga_code': TEST_LGA_CODE,
        'edit_code': 'S',
        'road_name': 'High',
        'road_type': 'ROAD',
        'locality_name': 'Richmond',
        'distance_related_flag': 'Y',
        'easting': '123456',
        'northing': '5800000',
        'datum_proj': 'EPSG:28355',
        'comments': 'Updated rural address on High Road, Richmond - 500m from intersection'
    }
    run_test_case(validator, test_case, "Test 2 - Rural address with distance")
    
    # Test Case 3: Incomplete address
    test_case = {
        'lga_code': TEST_LGA_CODE,
        'edit_code': 'S',
        'road_name': 'High',  # Missing road_type
        'locality_name': 'Richmond',
        'comments': 'Updated address to High, Richmond'
    }
    run_test_case(validator, test_case, "Test 3 - Incomplete address", expect_issues=True)

def test_crefno_validation():
    validator = M1Validator()
    print("\nTesting Crefno Validation:")
    
    # Test Case 1: Valid crefno update
    test_case = {
        'lga_code': TEST_LGA_CODE,
        'edit_code': 'C',
        'crefno': 'CR123/456',
        'comments': 'Updated crefno to CR123/456'
    }
    run_test_case(validator, test_case, "Test 1 - Valid crefno update")
    
    # Test Case 2: Missing crefno in comment
    test_case = {
        'lga_code': TEST_LGA_CODE,
        'edit_code': 'C',
        'crefno': 'CR789/012',
        'comments': 'Updated reference number'  # Missing explicit crefno
    }
    run_test_case(validator, test_case, "Test 2 - Missing crefno in comment", expect_issues=True)

def test_property_identifiers():
    validator = M1Validator()
    print("\nTesting Property Identifier Validation:")
    
    # Test Case 1: Valid property update with all identifiers
    test_case = {
        'lga_code': TEST_LGA_CODE,
        'edit_code': 'P',
        'propnum': '12345',
        'property_pfi': '98765',
        'spi': '1\\TP446069',
        'comments': 'Updated property 12345 (PFI: 98765) with SPI: 1\\TP446069'
    }
    run_test_case(validator, test_case, "Test 1 - Complete property identifiers")
    
    # Test Case 2: Invalid PFI format
    test_case = {
        'lga_code': TEST_LGA_CODE,
        'edit_code': 'P',
        'propnum': '12345',
        'property_pfi': 'ABC123',  # Should be numeric
        'comments': 'Updated property 12345'
    }
    run_test_case(validator, test_case, "Test 2 - Invalid PFI format", expect_issues=True)

def test_multi_assessment():
    validator = M1Validator()
    print("\nTesting Multi-Assessment Validation:")
    
    # Test Case 1: Valid multi-assessment addition
    test_case = {
        'lga_code': TEST_LGA_CODE,
        'edit_code': 'A',
        'propnum': '12345',
        'spi': '1\\TP446069',
        'property_pfi': '98765',
        'comments': 'Adding property 12345 to multi-assessment, SPI: 1\\TP446069'
    }
    run_test_case(validator, test_case, "Test 1 - Valid multi-assessment")
        
    # Test Case 2: Invalid multi-assessment (missing required info)
    test_row = {
        'lga_code': TEST_LGA_CODE,
        'edit_code': 'A',
        'comments': 'Adding to multi-assessment'  # Missing propnum
    }
    issues = validator.validate_row(test_row)
    print("\nTest Case 2 - Invalid multi-assessment:")
    print("Expected issues:", issues)

def test_address_update_scenarios():
    validator = M1Validator()
    
    # Test Case 3: Valid address update
    test_row = {
        'lga_code': TEST_LGA_CODE,
        'edit_code': 'S',
        'propnum': '12345',
        'property_pfi': '98765',
        'road_name': 'High Street',
        'locality_name': 'Richmond',
        'house_number_1': '42',
        'comments': 'Updated address for property 12345 to 42 High Street, Richmond'
    }
    issues = validator.validate_row(test_row)
    print("\nTest Case 3 - Valid address update:")
    if issues:
        print("Unexpected issues found:", issues)
    else:
        print("Passed ✓")
        
    # Test Case 4: Distance-based address without required fields
    test_row = {
        'lga_code': TEST_LGA_CODE,
        'edit_code': 'S',
        'road_name': 'High Street',
        'locality_name': 'Richmond',
        'distance_related_flag': 'Y',  # Missing easting/northing
        'comments': 'Updated rural address'
    }
    issues = validator.validate_row(test_row)
    print("\nTest Case 4 - Invalid distance-based address:")
    print("Expected issues:", issues)

def test_property_update_scenarios():
    validator = M1Validator()
    
    # Test Case 5: Valid property update
    test_row = {
        'lga_code': TEST_LGA_CODE,
        'edit_code': 'P',
        'propnum': '12345',
        'property_pfi': '98765',
        'comments': 'Updated property details for PFI: 98765'
    }
    issues = validator.validate_row(test_row)
    print("\nTest Case 5 - Valid property update:")
    if issues:
        print("Unexpected issues found:", issues)
    else:
        print("Passed ✓")
        
    # Test Case 6: Property update with invalid comment
    test_row = {
        'lga_code': TEST_LGA_CODE,
        'edit_code': 'P',
        'propnum': '12345',
        'property_pfi': '98765',
        'comments': 'Made some changes'  # Missing property reference
    }
    issues = validator.validate_row(test_row)
    print("\nTest Case 6 - Property update with invalid comment:")
    print("Expected issues:", issues)

def test_edge_cases():
    validator = M1Validator()
    
    # Test Case 7: Unknown edit code
    test_row = {
        'lga_code': TEST_LGA_CODE,
        'edit_code': 'X',
        'comments': 'Test'
    }
    issues = validator.validate_row(test_row)
    print("\nTest Case 7 - Unknown edit code:")
    print("Expected issues:", issues)
    
    # Test Case 8: Empty comment
    test_row = {
        'lga_code': TEST_LGA_CODE,
        'edit_code': 'P',
        'propnum': '12345',
        'comments': ''
    }
    issues = validator.validate_row(test_row)
    print("\nTest Case 8 - Empty comment:")
    print("Expected issues:", issues)

def main():
    setup_logging()
    print("Running M1 AI Validator Integration Tests...")
    print("==========================================")
    
    test_spi_validation()
    test_address_validation()
    test_crefno_validation()
    test_property_identifiers()
    test_multi_assessment()
    
    print("\nTests completed.")

if __name__ == '__main__':
    main()