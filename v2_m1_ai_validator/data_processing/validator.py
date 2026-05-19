"""
M1 validator with AI-powered validation rules and VicMap integration
"""
import logging
import re
from typing import Dict, List
import os
import sys

# Add the parent directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import (
    REQUIRED_FIELDS,
    EDIT_CODE_RULES,
    M1_FIELDS
)
from .comment_analyzer import M1CommentAnalyzer
from .vicmap_validator import VicmapValidator

class M1Validator:
    def __init__(self):
        self.logger = logging.getLogger('M1Validator')
        self.comment_analyzer = M1CommentAnalyzer()
        self.vicmap_validator = VicmapValidator()
        
    def validate_row(self, row: Dict) -> List[str]:
        """Validate a single M1 row"""
        issues = []
        
        # Basic field validation
        missing_fields = self._check_required_fields(row)
        if missing_fields:
            issues.extend([f"Missing required field: {field}" for field in missing_fields])
            
        edit_code = row.get('edit_code')
        if not edit_code:
            issues.append("No edit code provided")
            return issues
            
        # Get rules for this edit code
        rules = EDIT_CODE_RULES.get(edit_code)
        if not rules:
            issues.append(f"Unknown edit code: {edit_code}")
            return issues
            
        # Validate required fields for this edit code
        edit_code_fields = rules.get('required_fields', [])
        missing_edit_fields = [
            field for field in edit_code_fields 
            if not row.get(field)
        ]
        if missing_edit_fields:
            issues.extend([
                f"Edit code '{edit_code}' requires field: {field}"
                for field in missing_edit_fields
            ])
            
        # Validate field value rules
        field_issues = self._validate_field_values(row, rules)
        issues.extend(field_issues)
        
        # Comment analysis
        comment_issues = self.comment_analyzer.analyze_comment(
            edit_code, 
            row.get('comments', ''),
            row
        )
        issues.extend(comment_issues)
        
        return issues
        
    def _validate_against_vicmap(self, row: Dict, prop_info: Dict, issues: List[str]):
        """Validate M1 data against existing VicMap property data"""
        edit_code = row.get('edit_code')
        
        if edit_code in ['P', 'E']:  # Property updates
            # Check for property identifiers
            if prop_info.get('prop_pfi') != row.get('property_pfi'):
                issues.append(f"Property PFI mismatch: VicMap has {prop_info.get('prop_pfi')}")
                
            # For property updates, check if the property exists
            if not prop_info.get('prop_propnum'):
                issues.append(f"Property {row.get('propnum')} not found in VicMap")
                
        elif edit_code == 'A':  # Multi-assessment
            # For multi-assessment additions, both properties should exist
            if not prop_info.get('prop_propnum'):
                issues.append(f"Base property {row.get('propnum')} not found for multi-assessment")
                
            # Check if it's already part of a multi-assessment
            if prop_info.get('prop_multi_assessment') == 'Y':
                issues.append(f"Property {row.get('propnum')} is already part of a multi-assessment")
                
        elif edit_code == 'S':  # Address updates
            # Check if address fields match
            if row.get('house_number_1') and row.get('house_number_1') != prop_info.get('house_number_1'):
                issues.append(f"House number mismatch: VicMap has {prop_info.get('house_number_1')}")
                
            if row.get('road_name') and row.get('road_name') != prop_info.get('road_name'):
                issues.append(f"Road name mismatch: VicMap has {prop_info.get('road_name')}")
        
    def _check_required_fields(self, row: Dict) -> List[str]:
        """Check for required fields in M1"""
        return [
            field for field in REQUIRED_FIELDS
            if not row.get(field)
        ]
        
    def _validate_field_values(self, row: Dict, rules: Dict) -> List[str]:
        """Validate field values based on rules"""
        issues = []
        
        # Check field patterns and formats
        for field, value in row.items():
            if value and field in M1_FIELDS:
                field_rules = M1_FIELDS[field]
                
                # Check pattern if defined
                if 'pattern' in field_rules and value:
                    pattern = field_rules['pattern']
                    # Convert to string and clean up for validation
                    str_value = str(value).strip()
                    if not re.match(pattern, str_value):
                        if field == 'property_pfi':
                            issues.append(f"Property PFI must be numeric, got '{value}'")
                        elif field == 'spi':
                            issues.append(f"Invalid SPI format '{value}'. Must be like '1\\TP446069' or 'PC354544'")
                        elif field == 'propnum':
                            issues.append(f"Property number must be numeric, got '{value}'")
                        elif field == 'house_number_1':
                            issues.append(f"House number must be numeric with optional letter suffix, got '{value}'")
                        elif field == 'crefno':
                            issues.append(f"Council reference number format invalid, got '{value}'")
                        else:
                            issues.append(f"Invalid format for {field}: '{value}'")
                
                # Check allowed values if defined
                if 'allowed_values' in field_rules and value:
                    if value not in field_rules['allowed_values']:
                        issues.append(f"Invalid value for {field}: '{value}'. Must be one of {field_rules['allowed_values']}")
                            
        # VicMap validation for existing data
        if row.get('propnum'):
            exists, messages = self.vicmap_validator.validate_propnum(row['propnum'])
            if exists:
                # Get additional property info
                prop_info = self.vicmap_validator.get_property_info(row['propnum'])
                if prop_info:
                    self._validate_against_vicmap(row, prop_info, issues)
            elif messages:  # Only add messages if property doesn't exist
                issues.extend(messages)

        if row.get('spi'):
            exists, messages = self.vicmap_validator.validate_spi(row['spi'])
            if not exists and row.get('edit_code') != 'A':  # Don't validate SPI for new properties
                issues.extend(messages)

        # Validate address if present
        if all(row.get(f) for f in ['house_number_1', 'road_name', 'road_type', 'locality_name']):
            address_data = {
                'house_number_1': row['house_number_1'],
                'street_name': row['road_name'],
                'street_type': row['road_type'],
                'locality_name': row['locality_name']
            }
            exists, messages = self.vicmap_validator.validate_address(address_data)
            if not exists and row.get('edit_code') != 'S':  # Don't validate for new addresses
                issues.extend(messages)
        
        # Check conditional fields with improved error messages
        conditional_fields = rules.get('conditional_fields', {})
        if isinstance(conditional_fields, dict):
            for condition, fields in conditional_fields.items():
                if condition == 'distance_based' and row.get('distance_related_flag') == 'Y':
                    missing_fields = [field for field in fields if not row.get(field)]
                    if missing_fields:
                        issues.append(
                            f"Distance-based address requires these fields: {', '.join(missing_fields)}. "
                            "These are needed to specify the exact location of the property."
                        )
                elif condition == 'urban_address' and not row.get('distance_related_flag'):
                    missing_fields = [field for field in fields if not row.get(field)]
                    if missing_fields:
                        issues.append(
                            f"Urban address requires these fields: {', '.join(missing_fields)}. "
                            "These are needed for standard street addresses."
                        )
        elif isinstance(conditional_fields, list):
            missing_fields = [field for field in conditional_fields if not row.get(field)]
            if missing_fields:
                issues.append(
                    f"Required fields missing: {', '.join(missing_fields)}. "
                    "Please provide all required information."
                )
                
        # Validate numeric ranges
        for field, range_rule in rules.get('numeric_ranges', {}).items():
            value = row.get(field)
            if value is not None:
                try:
                    num_value = float(value)
                    if num_value < range_rule['min'] or num_value > range_rule['max']:
                        issues.append(
                            f"{field} value {value} outside valid range "
                            f"({range_rule['min']} - {range_rule['max']})"
                        )
                except ValueError:
                    issues.append(f"{field} value {value} is not numeric")
                    
        return issues