"""
AI-Powered Field Mapper for M1 Validation
Automatically detects and suggests correct field mappings
"""
import re
import logging
from typing import Dict, List, Tuple, Optional
from difflib import SequenceMatcher

class AIFieldMapper:
    """AI-powered field mapping and validation"""
    
    def __init__(self):
        self.logger = logging.getLogger('AIFieldMapper')
        
        # VicMap field mappings based on actual schema
        self.vicmap_fields = {
            'property': {
                'prop_pfi': 'Property PFI',
                'prop_propnum': 'Property Number', 
                'prop_lga_code': 'LGA Code',
                'prop_status': 'Property Status',
                'prop_multi_assessment': 'Multi Assessment Flag'
            },
            'parcel': {
                'parcel_pfi': 'Parcel PFI',
                'parcel_spi': 'Standard Parcel Identifier',
                'parcel_lga_code': 'LGA Code',
                'parcel_status': 'Parcel Status',
                'parcel_road': 'Is Road Parcel',
                'parcel_lot_number': 'Lot Number',
                'parcel_plan_number': 'Plan Number',
                'parcel_crefno': 'Council Reference Number'
            },
            'address': {
                'pfi': 'Address PFI',
                'property_pfi': 'Property PFI',
                'house_number_1': 'House Number',
                'road_name': 'Road Name',
                'road_type': 'Road Type',
                'locality_name': 'Locality Name',
                'lga_code': 'LGA Code',
                'is_primary': 'Is Primary Address',
                'property_status': 'Property Status',
                'distance_related_flag': 'Distance Related Flag'
            }
        }
        
        # Common field name variations based on actual VicMap schema
        self.field_variations = {
            'house_number_1': ['house_nbr_1', 'house_no_1', 'house_num_1', 'housenumber1', 'num_address', 'house_number', 'address_number', 'street_number', 'building_number'],
            'road_name': ['street_name', 'roadname', 'streetname', 'thoroughfare_name', 'road', 'street', 'rd_name'],
            'road_type': ['street_type', 'roadtype', 'streettype', 'thoroughfare_type', 'rd_type', 'st_type'],
            'locality_name': ['locality', 'suburb', 'town', 'localityname', 'city', 'district', 'place_name'],
            'propnum': ['property_number', 'prop_num', 'propertynum', 'prop_propnum', 'property_id', 'property_identifier', 'prop_id'],
            'property_pfi': ['prop_pfi', 'propertypfi', 'property_pfi', 'property_persistent_feature_id', 'prop_persistent_id'],
            'parcel_pfi': ['parcelpfi', 'parcel_pfi', 'parcel_persistent_feature_id', 'parcel_persistent_id'],
            'spi': ['standard_parcel_id', 'parcel_id', 'spi_id', 'parcel_spi', 'standard_parcel_identifier', 'parcel_identifier'],
            'lga_code': ['lga', 'lga_code', 'prop_lga_code', 'parcel_lga_code', 'local_government_area', 'council_code', 'municipality_code'],
            'is_primary': ['primary_address', 'is_primary_address', 'primary', 'main_address', 'is_main'],
            'distance_related_flag': ['distance_related', 'is_distance_related', 'distance_flag', 'rural_address'],
            'property_status': ['prop_status', 'status', 'property_state', 'prop_state']
        }
    
    def suggest_field_mapping(self, input_field: str, layer_type: str) -> List[Tuple[str, float]]:
        """
        Suggest correct field mappings for input field
        
        Args:
            input_field: The field name to map
            layer_type: Type of layer ('property', 'parcel', 'address')
            
        Returns:
            List of (suggested_field, confidence_score) tuples
        """
        suggestions = []
        input_lower = input_field.lower().replace('_', '').replace('-', '')
        
        # Check direct matches first
        for field, description in self.vicmap_fields.get(layer_type, {}).items():
            field_lower = field.lower().replace('_', '').replace('-', '')
            if input_lower == field_lower:
                suggestions.append((field, 1.0))
        
        # Check variations
        for correct_field, variations in self.field_variations.items():
            if correct_field in self.vicmap_fields.get(layer_type, {}):
                for variation in variations:
                    variation_lower = variation.lower().replace('_', '').replace('-', '')
                    similarity = SequenceMatcher(None, input_lower, variation_lower).ratio()
                    if similarity > 0.7:  # 70% similarity threshold
                        suggestions.append((correct_field, similarity))
        
        # Check fuzzy matches
        for field, description in self.vicmap_fields.get(layer_type, {}).items():
            field_lower = field.lower().replace('_', '').replace('-', '')
            similarity = SequenceMatcher(None, input_lower, field_lower).ratio()
            if similarity > 0.6:  # 60% similarity threshold
                suggestions.append((field, similarity))
        
        # Sort by confidence score
        suggestions.sort(key=lambda x: x[1], reverse=True)
        return suggestions[:3]  # Return top 3 suggestions
    
    def validate_field_name(self, field_name: str, layer_type: str) -> Tuple[bool, str, List[str]]:
        """
        Validate if field name is correct for the layer
        
        Args:
            field_name: Field name to validate
            layer_type: Type of layer
            
        Returns:
            Tuple of (is_valid, correct_field, suggestions)
        """
        if field_name in self.vicmap_fields.get(layer_type, {}):
            return True, field_name, []
        
        suggestions = self.suggest_field_mapping(field_name, layer_type)
        if suggestions:
            return False, suggestions[0][0], [s[0] for s in suggestions]
        
        return False, field_name, []
    
    def auto_correct_field_mapping(self, data: Dict[str, str], layer_type: str) -> Dict[str, str]:
        """
        Automatically correct field mappings in data
        
        Args:
            data: Dictionary with field names and values
            layer_type: Type of layer
            
        Returns:
            Dictionary with corrected field names
        """
        corrected_data = {}
        corrections_made = []
        
        for field, value in data.items():
            is_valid, correct_field, suggestions = self.validate_field_name(field, layer_type)
            
            if is_valid:
                corrected_data[field] = value
            else:
                corrected_data[correct_field] = value
                corrections_made.append(f"'{field}' → '{correct_field}'")
        
        if corrections_made:
            self.logger.info(f"Field corrections made: {', '.join(corrections_made)}")
        
        return corrected_data
    
    def get_field_suggestions_for_edit_code(self, edit_code: str) -> Dict[str, List[str]]:
        """
        Get field suggestions based on edit code
        
        Args:
            edit_code: M1 edit code
            
        Returns:
            Dictionary of field suggestions by layer type
        """
        suggestions = {
            'property': [],
            'parcel': [],
            'address': []
        }
        
        if edit_code in ['A', 'P', 'E']:  # Property operations
            suggestions['property'].extend(['prop_pfi', 'prop_propnum', 'prop_status'])
            suggestions['parcel'].extend(['parcel_pfi', 'parcel_spi', 'parcel_crefno'])
        
        if edit_code in ['S', 'E']:  # Address operations
            suggestions['address'].extend(['house_number_1', 'road_name', 'road_type', 'locality_name'])
        
        if edit_code == 'C':  # Crefno operations
            suggestions['parcel'].extend(['parcel_pfi', 'parcel_spi', 'parcel_crefno'])
        
        return suggestions
    
    def analyze_m1_structure(self, m1_data: List[Dict]) -> Dict[str, any]:
        """
        Analyze M1 data structure and provide insights
        
        Args:
            m1_data: List of M1 records
            
        Returns:
            Analysis results
        """
        analysis = {
            'total_records': len(m1_data),
            'edit_codes': {},
            'field_usage': {},
            'potential_issues': [],
            'suggestions': []
        }
        
        # Analyze edit codes
        for record in m1_data:
            edit_code = record.get('edit_code', 'Unknown')
            analysis['edit_codes'][edit_code] = analysis['edit_codes'].get(edit_code, 0) + 1
        
        # Analyze field usage
        all_fields = set()
        for record in m1_data:
            all_fields.update(record.keys())
        
        for field in all_fields:
            usage_count = sum(1 for record in m1_data if record.get(field))
            analysis['field_usage'][field] = usage_count
        
        # Check for common issues
        for record in m1_data:
            # Check for LGA code consistency
            lga_code = record.get('lga_code')
            if lga_code and lga_code != '346':
                analysis['potential_issues'].append(f"LGA code {lga_code} - should be 346 for Greater Shepparton")
            
            # Check for missing new_road flag
            if record.get('edit_code') == 'S' and not record.get('new_road'):
                road_name = record.get('road_name')
                if road_name:
                    analysis['potential_issues'].append(f"Missing 'new_road' flag for road: {road_name}")
        
        return analysis
