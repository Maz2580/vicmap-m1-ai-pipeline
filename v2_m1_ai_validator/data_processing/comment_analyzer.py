"""
Comment analyzer for M1 validation
"""
import re
from typing import Dict, List, Tuple
import logging
import os
import sys

# Add the parent directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import EDIT_CODE_RULES

class M1CommentAnalyzer:
    def __init__(self):
        self.logger = logging.getLogger('M1CommentAnalyzer')
    
    def analyze_comment(self, edit_code: str, comment: str, row_data: Dict) -> List[str]:
        """Analyze comment for consistency with edit code and data"""
        issues = []
        
        if not comment:
            return ["No comment provided to explain the change"]
        
        # Get edit code rules
        rules = EDIT_CODE_RULES.get(edit_code)
        if not rules:
            return [f"Unknown edit code: {edit_code}"]
            
        # Check if comment matches common patterns for this edit code
        # Make pattern matching more flexible by looking for key terms
        comment_lower = comment.lower()
        matches_pattern = False
        for pattern in rules['common_patterns']:
            pattern_terms = pattern.lower().split()
            # Consider it a match if any two words from the pattern appear in the comment
            matched_terms = sum(1 for term in pattern_terms if term in comment_lower)
            if matched_terms >= 2:
                matches_pattern = True
                break
                
        if not matches_pattern:
            issues.append(
                f"Comment should better describe the {rules['description'].lower()}"
            )
        
        # Specific validations based on edit code
        if edit_code == 'A':  # Multi-assessment
            if 'multi-assessment' not in comment.lower():
                issues.append("Multi-assessment operation should mention 'multi-assessment' in comment")
            if row_data.get('propnum') and str(row_data['propnum']) not in comment:
                issues.append("Comment should include the propnum being added to multi-assessment")
                
        elif edit_code == 'B':  # Base property
            if 'base' not in comment.lower():
                issues.append("Base property operation should mention 'base' in comment")
            if row_data.get('base_propnum') and str(row_data['base_propnum']) not in comment:
                issues.append("Comment should include the base_propnum being modified")
                
        elif edit_code == 'C':  # Crefno
            if 'crefno' not in comment.lower() and 'council reference' not in comment.lower():
                issues.append("Crefno update should mention 'crefno' or 'council reference' in comment")
            
        elif edit_code == 'E':  # Property and address
            has_address = any(term in comment.lower() for term in ['address', 'road', 'street'])
            has_property = 'property' in comment.lower() or 'prop' in comment.lower()
            if not (has_address and has_property):
                issues.append("Comment should mention both property and address changes")
                
        elif edit_code == 'P':  # Property
            property_terms = ['property', 'prop', 'details', 'information']
            if not any(term in comment.lower() for term in property_terms):
                issues.append("Property update should mention property details being changed")
                
        elif edit_code == 'S':  # Address
            address_terms = ['address', 'location', 'street', 'road']
            if not any(term in comment.lower() for term in address_terms):
                issues.append("Address update should describe the address change")
            # Check for distance-based address comments
            if row_data.get('distance_related_flag') == 'Y':
                distance_terms = ['distance', 'rural', 'meters', 'metres', 'km', 'kilometers']
                if not any(term in comment.lower() for term in distance_terms):
                    issues.append(
                        "Distance-based address should explain the distance or rural nature "
                        "(e.g., distance from road, rural address, etc.)"
                    )
                    
        elif edit_code == 'Z':  # Remove secondary
            if 'secondary' not in comment.lower() and 'remove' not in comment.lower():
                issues.append("Secondary address removal should mention 'secondary' or 'remove' in comment")
                
        elif edit_code == 'R':  # Remove from multi-assessment
            if 'multi' not in comment.lower():
                issues.append("Multi-assessment removal should mention 'multi' in comment")
        
        # Check for any property identifiers mentioned - make PFI check optional
        if row_data.get('property_pfi') and edit_code in ['B', 'C']:  # Only require PFI for base and crefno updates
            pfi_pattern = r'pfi[:\s]*' + str(row_data['property_pfi'])
            if not re.search(pfi_pattern, comment, re.I):
                issues.append("Comment should reference the property_pfi being modified")
        
        # For most edit codes, having either propnum or PFI in the comment is sufficient
        has_identifier = False
        if row_data.get('propnum'):
            has_identifier = str(row_data['propnum']) in comment
        if row_data.get('property_pfi'):
            pfi_pattern = r'pfi[:\s]*' + str(row_data['property_pfi'])
            has_identifier = has_identifier or re.search(pfi_pattern, comment, re.I)
            
        if not has_identifier and edit_code in ['A', 'P', 'E']:  # These operations should reference the property
            issues.append("Comment should include either the propnum or PFI being modified")
                
        return issues