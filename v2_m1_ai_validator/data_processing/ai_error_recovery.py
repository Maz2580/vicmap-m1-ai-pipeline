"""
AI-Powered Error Recovery System for M1 Validation
Provides intelligent suggestions for fixing validation errors
"""
import os
import re
import logging
from typing import Dict, List, Tuple, Optional
from .ai_field_mapper import AIFieldMapper

class AIErrorRecovery:
    """AI-powered error recovery and suggestion system"""
    
    def __init__(self):
        self.logger = logging.getLogger('AIErrorRecovery')
        self.field_mapper = AIFieldMapper()
        
        # Common error patterns and their solutions
        self.error_patterns = {
            'road_locality_not_exist': {
                'pattern': r'Road-Locality combination does not exist',
                'solutions': [
                    'Add "Y" to the new_road field for new road/locality combinations',
                    'Check spelling of road name and locality name',
                    'Verify the road exists in VicMap using LASSI or VaaS'
                ],
                'auto_fix': self._fix_road_locality_issue
            },
            'property_not_found': {
                'pattern': r'Property.*not found',
                'solutions': [
                    'Verify the property number exists in VicMap',
                    'Check that lga_code matches your configured LGA_CODE',
                    'Use property PFI instead of property number if available'
                ],
                'auto_fix': self._fix_property_not_found
            },
            'spi_not_found': {
                'pattern': r'SPI.*not found',
                'solutions': [
                    'Verify SPI format (e.g., "1\\TP446069" or "PC354544")',
                    'Check if parcel exists in VicMap',
                    'Ensure correct LGA code is used'
                ],
                'auto_fix': self._fix_spi_not_found
            },
            'missing_required_field': {
                'pattern': r'Missing required field',
                'solutions': [
                    'Check edit code requirements in M1 documentation',
                    'Ensure all mandatory fields are populated',
                    'Verify field names match VicMap schema'
                ],
                'auto_fix': self._fix_missing_required_field
            },
            'invalid_format': {
                'pattern': r'Invalid format|Invalid value',
                'solutions': [
                    'Check field format requirements',
                    'Verify data type (numeric, text, etc.)',
                    'Use correct field names from VicMap schema'
                ],
                'auto_fix': self._fix_invalid_format
            },
            'invalid_edit_code': {
                'pattern': r'Invalid edit code|Unknown edit code',
                'solutions': [
                    'Use only valid edit codes: A, C, E, P, R, S, Z',
                    'Check for typos or case sensitivity issues',
                    'Refer to M1 documentation for correct edit code usage'
                ],
                'auto_fix': self._fix_invalid_edit_code
            },
            'duplicate_property': {
                'pattern': r'Duplicate property|Property already exists',
                'solutions': [
                    'Use edit code "C" instead of "A" for existing properties',
                    'Check if property already exists in VicMap',
                    'Verify property number is unique'
                ],
                'auto_fix': self._fix_duplicate_property
            },
            'invalid_plan_prefix': {
                'pattern': r'Invalid plan prefix|Plan prefix not recognized',
                'solutions': [
                    'Use valid plan prefixes: PS, PC, TP, LP, CP, RP, SP, CS',
                    'Check for typos in plan prefix',
                    'Verify plan number format'
                ],
                'auto_fix': self._fix_invalid_plan_prefix
            },
            'invalid_house_number': {
                'pattern': r'Invalid house number|House number format',
                'solutions': [
                    'Use numeric values for house numbers',
                    'For ranges, use house_number_1 and house_number_2',
                    'For suffixes, use house_suffix_1 and house_suffix_2'
                ],
                'auto_fix': self._fix_invalid_house_number
            },
            'invalid_road_type': {
                'pattern': r'Invalid road type|Road type not recognized',
                'solutions': [
                    'Use standard VicMap road types (ROAD, STREET, AVENUE, etc.)',
                    'Check for abbreviations (RD, ST, AVE) that should be expanded',
                    'Verify road type spelling'
                ],
                'auto_fix': self._fix_invalid_road_type
            }
        }
        
        # The council's own LGA code, taken from configuration. A generic tool
        # cannot know any council's "correct" Victorian LGA code, so we never
        # hardcode one and never auto-rewrite between codes. We only flag a
        # record whose lga_code doesn't match the configured LGA_CODE.
        self.expected_lga_code = os.getenv("LGA_CODE", "")
    
    def analyze_error(self, error_message: str, record: Dict) -> Dict[str, any]:
        """
        Analyze error message and provide recovery suggestions
        
        Args:
            error_message: The error message to analyze
            record: The M1 record that caused the error
            
        Returns:
            Dictionary with analysis and suggestions
        """
        analysis = {
            'error_type': 'unknown',
            'confidence': 0.0,
            'solutions': [],
            'auto_fix_available': False,
            'suggested_changes': {},
            'explanation': ''
        }
        
        # Ensure error_message is a string
        if isinstance(error_message, list):
            error_message = ' '.join(str(msg) for msg in error_message)
        else:
            error_message = str(error_message)
        
        error_lower = error_message.lower()
        
        # Match against known error patterns
        for error_type, pattern_info in self.error_patterns.items():
            if re.search(pattern_info['pattern'], error_lower):
                analysis['error_type'] = error_type
                analysis['confidence'] = 0.9
                analysis['solutions'] = pattern_info['solutions']
                analysis['auto_fix_available'] = True
                analysis['explanation'] = self._get_error_explanation(error_type, record)
                
                # Try to generate auto-fix
                if pattern_info['auto_fix']:
                    suggested_changes = pattern_info['auto_fix'](record, error_message)
                    if suggested_changes:
                        analysis['suggested_changes'] = suggested_changes
                        analysis['auto_fix_available'] = True
                
                break
        
        # If no pattern matched, try generic analysis
        if analysis['error_type'] == 'unknown':
            analysis = self._generic_error_analysis(error_message, record)
        
        return analysis
    
    def _fix_road_locality_issue(self, record: Dict, error_message: str) -> Dict[str, str]:
        """Auto-fix road-locality combination issues"""
        suggested_changes = {}
        
        # Check if new_road flag is missing
        if not record.get('new_road') and record.get('edit_code') in ['S', 'E']:
            suggested_changes['new_road'] = 'Y'
            suggested_changes['_explanation'] = 'Added new_road flag for new road/locality combination'
        
        # Flag (don't silently rewrite) an lga_code that doesn't match the
        # configured LGA_CODE. Only meaningful when LGA_CODE is set.
        lga_code = record.get('lga_code')
        if self.expected_lga_code and lga_code and lga_code != self.expected_lga_code:
            suggested_changes['lga_code'] = self.expected_lga_code
            suggested_changes['_explanation'] = (
                f'lga_code {lga_code} does not match the configured LGA_CODE '
                f'{self.expected_lga_code}'
            )

        return suggested_changes

    def _fix_property_not_found(self, record: Dict, error_message: str) -> Dict[str, str]:
        """Auto-fix property not found issues"""
        suggested_changes = {}

        # Flag an lga_code that doesn't match the configured LGA_CODE.
        lga_code = record.get('lga_code')
        if self.expected_lga_code and lga_code and lga_code != self.expected_lga_code:
            suggested_changes['lga_code'] = self.expected_lga_code
            suggested_changes['_explanation'] = (
                f'lga_code {lga_code} does not match the configured LGA_CODE '
                f'{self.expected_lga_code}'
            )

        return suggested_changes

    def _fix_invalid_edit_code(self, record: Dict, error_message: str) -> Dict[str, str]:
        """Auto-fix invalid edit code issues"""
        suggested_changes = {}
        
        # Check for common edit code mistakes
        edit_code = record.get('edit_code', '')
        if edit_code.lower() == 'a':
            suggested_changes['edit_code'] = 'A'
            suggested_changes['_explanation'] = 'Corrected edit code case to uppercase A'
        elif edit_code.lower() == 'c':
            suggested_changes['edit_code'] = 'C'
            suggested_changes['_explanation'] = 'Corrected edit code case to uppercase C'
        elif edit_code.lower() == 'p':
            suggested_changes['edit_code'] = 'P'
            suggested_changes['_explanation'] = 'Corrected edit code case to uppercase P'
        elif edit_code.lower() == 's':
            suggested_changes['edit_code'] = 'S'
            suggested_changes['_explanation'] = 'Corrected edit code case to uppercase S'
        elif edit_code.lower() == 'r':
            suggested_changes['edit_code'] = 'R'
            suggested_changes['_explanation'] = 'Corrected edit code case to uppercase R'
        
        return suggested_changes
    
    def _fix_duplicate_property(self, record: Dict, error_message: str) -> Dict[str, str]:
        """Auto-fix duplicate property issues"""
        suggested_changes = {}
        
        # If trying to add a property that already exists, change to 'C' (update)
        if record.get('edit_code') == 'A':
            suggested_changes['edit_code'] = 'C'
            suggested_changes['_explanation'] = 'Changed edit code from A to C for existing property'
        
        return suggested_changes
    
    def _fix_invalid_plan_prefix(self, record: Dict, error_message: str) -> Dict[str, str]:
        """Auto-fix invalid plan prefix issues"""
        suggested_changes = {}
        
        # Common plan prefix corrections
        plan_number = record.get('plan_number', '')
        if plan_number.startswith('tp'):
            suggested_changes['plan_number'] = 'TP' + plan_number[2:]
            suggested_changes['_explanation'] = 'Corrected plan prefix to uppercase TP'
        elif plan_number.startswith('ps'):
            suggested_changes['plan_number'] = 'PS' + plan_number[2:]
            suggested_changes['_explanation'] = 'Corrected plan prefix to uppercase PS'
        elif plan_number.startswith('lp'):
            suggested_changes['plan_number'] = 'LP' + plan_number[2:]
            suggested_changes['_explanation'] = 'Corrected plan prefix to uppercase LP'
        elif plan_number.startswith('pc'):
            suggested_changes['plan_number'] = 'PC' + plan_number[2:]
            suggested_changes['_explanation'] = 'Corrected plan prefix to uppercase PC'
        
        return suggested_changes
    
    def _fix_invalid_house_number(self, record: Dict, error_message: str) -> Dict[str, str]:
        """Auto-fix invalid house number issues"""
        suggested_changes = {}
        
        # Fix common house number format issues
        house_number = record.get('house_number_1', '')
        
        # Remove non-numeric characters from house number
        if house_number and not house_number.isdigit():
            # Extract numeric part and suffix
            match = re.match(r'(\d+)([A-Za-z]*)', house_number)
            if match:
                number, suffix = match.groups()
                suggested_changes['house_number_1'] = number
                if suffix:
                    suggested_changes['house_suffix_1'] = suffix
                suggested_changes['_explanation'] = f'Split house number {house_number} into number {number} and suffix {suffix}'
        
        return suggested_changes
    
    def _fix_invalid_road_type(self, record: Dict, error_message: str) -> Dict[str, str]:
        """Auto-fix invalid road type issues"""
        suggested_changes = {}
        
        # Common road type abbreviation expansions
        road_type = record.get('road_type', '')
        road_type_upper = road_type.upper()
        
        road_type_mappings = {
            'RD': 'ROAD',
            'ST': 'STREET',
            'AVE': 'AVENUE',
            'BLVD': 'BOULEVARD',
            'CT': 'COURT',
            'CRES': 'CRESCENT',
            'DR': 'DRIVE',
            'HWY': 'HIGHWAY',
            'LN': 'LANE',
            'PL': 'PLACE',
            'SQ': 'SQUARE',
            'TCE': 'TERRACE',
            'WAY': 'WAY'
        }
        
        if road_type_upper in road_type_mappings:
            suggested_changes['road_type'] = road_type_mappings[road_type_upper]
            suggested_changes['_explanation'] = f'Expanded road type abbreviation {road_type} to {road_type_mappings[road_type_upper]}'
        
        return suggested_changes
        
        return suggested_changes
    
    def _fix_spi_not_found(self, record: Dict, error_message: str) -> Dict[str, str]:
        """Auto-fix SPI not found issues"""
        suggested_changes = {}
        
        spi = record.get('spi', '')
        if spi:
            # Check SPI format
            if not re.match(r'^[0-9]+\\[A-Z]{2}[0-9]+$', spi) and not re.match(r'^[A-Z]{2}[0-9]+$', spi):
                # Try to fix common SPI format issues
                if '\\' not in spi and 'TP' in spi.upper():
                    # Try to add lot number
                    parts = spi.upper().split('TP')
                    if len(parts) == 2:
                        suggested_changes['spi'] = f"1\\TP{parts[1]}"
                        suggested_changes['_explanation'] = 'Fixed SPI format by adding lot number'
        
        return suggested_changes
    
    def _fix_missing_required_field(self, record: Dict, error_message: str) -> Dict[str, str]:
        """Auto-fix missing required field issues"""
        suggested_changes = {}
        
        # Extract field name from error message
        field_match = re.search(r'field:?\s*(\w+)', error_message, re.IGNORECASE)
        if field_match:
            missing_field = field_match.group(1).lower()
            
            # Try to suggest based on edit code
            edit_code = record.get('edit_code')
            if edit_code == 'S' and missing_field in ['road_name', 'road_type', 'locality_name']:
                suggested_changes['_explanation'] = f'Edit code S requires {missing_field} - please provide this field'
            elif edit_code == 'P' and missing_field == 'propnum':
                suggested_changes['_explanation'] = f'Edit code P requires propnum - please provide this field'
        
        return suggested_changes
    
    def _fix_invalid_format(self, record: Dict, error_message: str) -> Dict[str, str]:
        """Auto-fix invalid format issues"""
        suggested_changes = {}
        
        # Check for common format issues
        for field, value in record.items():
            if not value:
                continue
                
            # Check numeric fields
            if field in ['propnum', 'property_pfi', 'parcel_pfi'] and not str(value).isdigit():
                suggested_changes['_explanation'] = f'{field} should be numeric, got: {value}'
            
            # Check SPI format
            elif field == 'spi' and not re.match(r'^([0-9]+\\[A-Z]{2}[0-9]+|[A-Z]{2}[0-9]+)$', str(value)):
                suggested_changes['_explanation'] = f'SPI format should be like "1\\TP446069" or "PC354544", got: {value}'
        
        return suggested_changes
    
    def _get_error_explanation(self, error_type: str, record: Dict) -> str:
        """Get human-readable explanation for error type"""
        explanations = {
            'road_locality_not_exist': 'The road and locality combination does not exist in VicMap. This usually means it\'s a new road that needs to be flagged as such.',
            'property_not_found': 'The property number could not be found in VicMap. This might be due to incorrect LGA code or the property not existing.',
            'spi_not_found': 'The Standard Parcel Identifier (SPI) could not be found. Check the format and ensure the parcel exists in VicMap.',
            'missing_required_field': 'A required field for this edit code is missing. Check the M1 documentation for field requirements.',
            'invalid_format': 'One or more fields have invalid format. Check the data types and formats required by VicMap.'
        }
        return explanations.get(error_type, 'Unknown error type')
    
    def _generic_error_analysis(self, error_message: str, record: Dict) -> Dict[str, any]:
        """Generic error analysis when no pattern matches"""
        analysis = {
            'error_type': 'generic',
            'confidence': 0.3,
            'solutions': [
                'Review the error message carefully',
                'Check M1 documentation for field requirements',
                'Verify data against VicMap using LASSI or VaaS',
                'Contact VicMap helpdesk for assistance'
            ],
            'auto_fix_available': False,
            'suggested_changes': {},
            'explanation': 'Generic error that requires manual review'
        }
        
        # Try to extract useful information from error message
        if 'timeout' in error_message.lower():
            analysis['solutions'].insert(0, 'API timeout - try again later or check internet connection')
        elif 'connection' in error_message.lower():
            analysis['solutions'].insert(0, 'Connection error - check internet connection')
        
        return analysis
    
    def generate_recovery_report(self, errors: List[Tuple[Dict, str]]) -> Dict[str, any]:
        """
        Generate a comprehensive recovery report for multiple errors
        
        Args:
            errors: List of (record, error_message) tuples
            
        Returns:
            Comprehensive recovery report
        """
        report = {
            'total_errors': len(errors),
            'error_types': {},
            'common_issues': [],
            'auto_fixable': 0,
            'manual_review_required': 0,
            'suggestions': []
        }
        
        error_analyses = []
        
        for record, error_message in errors:
            analysis = self.analyze_error(error_message, record)
            error_analyses.append(analysis)
            
            # Count error types
            error_type = analysis['error_type']
            report['error_types'][error_type] = report['error_types'].get(error_type, 0) + 1
            
            # Count auto-fixable errors
            if analysis['auto_fix_available']:
                report['auto_fixable'] += 1
            else:
                report['manual_review_required'] += 1
        
        # Identify common issues
        for error_type, count in report['error_types'].items():
            if count > 1:
                report['common_issues'].append(f"{error_type}: {count} occurrences")
        
        # Generate overall suggestions
        if report['error_types'].get('road_locality_not_exist', 0) > 0:
            report['suggestions'].append("Consider adding 'new_road' flag for new road/locality combinations")
        
        if report['error_types'].get('property_not_found', 0) > 0:
            report['suggestions'].append("Verify lga_code on each record matches your configured LGA_CODE")
        
        if report['auto_fixable'] > 0:
            report['suggestions'].append(f"{report['auto_fixable']} errors can be auto-fixed")
        
        return report
