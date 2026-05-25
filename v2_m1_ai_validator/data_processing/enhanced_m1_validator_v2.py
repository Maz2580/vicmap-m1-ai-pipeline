"""
Enhanced M1 Validator V2 - Based on Real M1 Documentation and Training Data
This version incorporates actual M1 field names, patterns, and common error types
from the official M1 documentation and training data analysis.
"""
import os
import pandas as pd
import re
import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
import json

from .validator import M1Validator
from .ai_field_mapper import AIFieldMapper
from .ai_error_recovery import AIErrorRecovery
from .ai_comment_enhancer import AICommentEnhancer
from .enhanced_vicmap_validator import EnhancedVicmapValidator

class EnhancedM1ValidatorV2:
    """
    Enhanced M1 Validator V2 with real M1 field mappings and patterns
    Based on M1 Version 12 Documentation and actual training data
    """
    
    def __init__(self):
        self.logger = logging.getLogger('EnhancedM1ValidatorV2')
        
        # Initialize components
        self.validator = M1Validator()
        self.field_mapper = AIFieldMapper()
        self.error_recovery = AIErrorRecovery()
        self.comment_enhancer = AICommentEnhancer()
        self.vicmap_validator = EnhancedVicmapValidator()
        
        # Real M1 field mappings based on documentation
        self.m1_field_mappings = {
            # Administrative Section
            'LgaCode': 'lga_code',
            'NewSub': 'new_sub',
            
            # Vicmap LAT Link
            'PropertyPfi': 'property_pfi',
            'ParcelPfi': 'parcel_pfi', 
            'AddressPfi': 'address_pfi',
            'Spi': 'spi',
            'PlanNumber': 'plan_number',
            'LotNumber': 'lot_number',
            
            # Property Details
            'BasePropnum': 'base_propnum',
            'Propnum': 'propnum',
            'CrefNo': 'crefno',
            
            # Address - Building Sub Unit
            'HsaFlag': 'hsa_flag',
            'HsaUnitId': 'hsa_unit_id',
            'BlgUnitType': 'blg_unit_type',
            'BlgUnitPrefix1': 'blg_unit_prefix_1',
            'BlgUnitId1': 'blg_unit_id_1',
            'BlgUnitSuffix1': 'blg_unit_suffix_1',
            'BlgUnitPrefix2': 'blg_unit_prefix_2',
            'BlgUnitId2': 'blg_unit_id_2',
            'BlgUnitSuffix2': 'blg_unit_suffix_2',
            
            # Address - Floor
            'FloorType': 'floor_type',
            'FloorPrefix1': 'floor_prefix_1',
            'FloorNo1': 'floor_no_1',
            'FloorSuffix1': 'floor_suffix_1',
            'FloorPrefix2': 'floor_prefix_2',
            'FloorNo2': 'floor_no_2',
            'FloorSuffix2': 'floor_suffix_2',
            
            # Address - Property Name & Locator
            'BuildingName': 'building_name',
            'ComplexName': 'complex_name',
            'LocationDescriptor': 'location_descriptor',
            
            # Address - House No.
            'HousePrefix1': 'house_prefix_1',
            'HouseNumber1': 'house_number_1',
            'HouseSuffix1': 'house_suffix_1',
            'HousePrefix2': 'house_prefix_2',
            'HouseNumber2': 'house_number_2',
            'HouseSuffix2': 'house_suffix_2',
            
            # Address - Access Type
            'AccessType': 'access_type',
            
            # Address - Road and Locality Information
            'NewRoad': 'new_road',
            'RoadName': 'road_name',
            'RoadType': 'road_type',
            'RoadSuffix': 'road_suffix',
            'LocalityName': 'locality_name',
            
            # Address - Location
            'DistanceRelatedFlag': 'distance_related_flag',
            'IsPrimary': 'is_primary',
            'Easting': 'easting',
            'Northing': 'northing',
            'DatumProj': 'datum_proj',
            'OutsideProperty': 'outside_property',
            
            # Edit Type
            'EditCode': 'edit_code',
            'Comments': 'comments'
        }
        
        # Reverse mapping for field name correction
        self.reverse_mappings = {v: k for k, v in self.m1_field_mappings.items()}
        
        # Common error patterns from training data
        self.common_error_patterns = {
            'road_locality_not_found': {
                'pattern': r'Road-Locality combination does not exist and not a new road',
                'solution': 'Add "Y" to NewRoad field for new road-locality combinations',
                'auto_fix': {'new_road': 'Y'}
            },
            'property_not_found': {
                'pattern': r'Property Identifier has no matches',
                'solution': 'Verify property PFI exists in VicMap or use correct identifier',
                'auto_fix': None
            },
            'multiple_properties': {
                'pattern': r'Cannot Determine Property Pfi > 1 Property Found For Parcel',
                'solution': 'Use specific property PFI instead of parcel identifier',
                'auto_fix': None
            },
            'lga_code_mismatch': {
                'pattern': r'LGA code mismatch',
                'solution': 'Set lga_code to your configured LGA_CODE',
                'auto_fix': None  # generic tool must not rewrite to a hardcoded code
            }
        }
        
        # Edit code specific requirements from documentation
        self.edit_code_requirements = {
            'A': {
                'required_fields': ['property_pfi', 'propnum'],
                'description': 'Add property to multi-assessment',
                'comment_patterns': ['adding propnum', 'multi-assessment', 'new']
            },
            'B': {
                'required_fields': ['property_pfi'],
                'description': 'Remove primary property from base or retire whole base',
                'comment_patterns': ['removing', 'retiring', 'base property']
            },
            'C': {
                'required_fields': ['parcel_pfi', 'spi', 'crefno'],
                'description': 'Update parcel-based Council Reference number',
                'comment_patterns': ['updating crefno', 'parcel', 'reference number']
            },
            'E': {
                'required_fields': ['property_pfi', 'propnum', 'road_name', 'locality_name'],
                'description': 'Update both property and address details',
                'comment_patterns': ['updating property', 'updating address', 'property and address']
            },
            'P': {
                'required_fields': ['property_pfi', 'propnum'],
                'description': 'Update property details only',
                'comment_patterns': ['updating property', 'property details']
            },
            'S': {
                'required_fields': ['address_pfi', 'road_name', 'locality_name'],
                'description': 'Update address details only',
                'comment_patterns': ['updating address', 'address details']
            },
            'Z': {
                'required_fields': ['address_pfi'],
                'description': 'Remove secondary addresses or downgrade distance-based address',
                'comment_patterns': ['removing address', 'downgrading', 'secondary address']
            },
            'R': {
                'required_fields': ['property_pfi'],
                'description': 'Remove property from multi-assessment',
                'comment_patterns': ['removing property', 'multi-assessment']
            }
        }
    
    def validate_m1_file(self, file_path: str, auto_fix: bool = False) -> Dict[str, Any]:
        """
        Validate M1 file with enhanced AI features based on real M1 patterns
        """
        self.logger.info(f"Starting enhanced M1 validation for: {file_path}")
        
        try:
            # Load M1 file
            df = pd.read_csv(file_path)
            self.logger.info(f"Loaded {len(df)} records from M1 file")
            
            # Convert M1 field names to our internal format
            df = self._convert_m1_field_names(df)
            
            # Validate each record
            validation_results = []
            total_records = len(df)
            valid_records = 0
            auto_fixed_records = 0
            
            for index, row in df.iterrows():
                result = self._validate_record_with_ai_v2(row, index, auto_fix)
                validation_results.append(result)
                
                if result['validation_passed']:
                    valid_records += 1
                if result.get('auto_fixed', False):
                    auto_fixed_records += 1
            
            # Generate comprehensive report
            report = self._generate_validation_report_v2(
                validation_results, total_records, valid_records, auto_fixed_records
            )
            
            self.logger.info(f"Validation completed: {valid_records}/{total_records} records passed")
            return report
            
        except Exception as e:
            self.logger.error(f"Error validating M1 file: {str(e)}")
            return {
                'error': str(e),
                'summary': {'total_records': 0, 'valid_records': 0, 'validation_rate': 0}
            }
    
    def _convert_m1_field_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Convert M1 field names to our internal format
        """
        # Create mapping for actual M1 field names to our internal names
        field_mapping = {}
        for m1_field, internal_field in self.m1_field_mappings.items():
            if m1_field in df.columns:
                field_mapping[m1_field] = internal_field
        
        # Rename columns
        df = df.rename(columns=field_mapping)
        
        # Fill missing columns with empty strings
        for internal_field in self.m1_field_mappings.values():
            if internal_field not in df.columns:
                df[internal_field] = ''
        
        return df
    
    def _validate_record_with_ai_v2(self, record: Dict, index: int, auto_fix: bool) -> Dict[str, Any]:
        """
        Enhanced record validation with real M1 patterns
        """
        result = {
            'record_index': index,
            'edit_code': record.get('edit_code', ''),
            'validation_passed': False,
            'issues': [],
            'suggestions': [],
            'field_mappings': {},
            'ai_insights': {},
            'auto_fixed': False
        }
        
        try:
            # Clean record data
            cleaned_record = self._clean_record_data(record)
            
            # 1. Field mapping analysis
            field_analysis = self._analyze_field_mappings_v2(cleaned_record)
            result['field_mappings'] = field_analysis
            
            # 2. Basic validation
            basic_issues = self.validator.validate_row(cleaned_record)
            result['issues'].extend(basic_issues)
            
            # 3. Edit code specific validation
            edit_code_issues = self._validate_edit_code_requirements(cleaned_record)
            result['issues'].extend(edit_code_issues)
            
            # 4. Common error pattern detection
            pattern_issues = self._detect_common_error_patterns(cleaned_record)
            result['issues'].extend(pattern_issues)
            
            # 5. AI-powered error recovery
            if result['issues']:
                error_analysis = self.error_recovery.analyze_error(
                    '; '.join(result['issues']), cleaned_record
                )
                result['suggestions'].extend(error_analysis['suggestions'])
                
                # Apply auto-fixes if enabled
                if auto_fix and error_analysis.get('auto_fixes'):
                    cleaned_record = self._apply_auto_fixes(cleaned_record, error_analysis['auto_fixes'])
                    result['auto_fixed'] = True
            
            # 6. Comment enhancement
            if cleaned_record.get('comments'):
                comment_analysis = self.comment_enhancer.enhance_comment(
                    cleaned_record['edit_code'], 
                    cleaned_record['comments'], 
                    cleaned_record
                )
                result['ai_insights']['enhanced_comment'] = comment_analysis['enhanced_comment']
                result['ai_insights']['comment_quality'] = comment_analysis['quality_score']
            
            # 7. Determine if validation passed
            result['validation_passed'] = len(result['issues']) == 0
            
            # 8. Generate AI insights
            result['ai_insights'].update({
                'field_mapping_accuracy': field_analysis.get('accuracy', 0),
                'edit_code_compliance': self._check_edit_code_compliance(cleaned_record),
                'data_quality_score': self._calculate_data_quality_score(cleaned_record)
            })
            
        except Exception as e:
            self.logger.error(f"Error validating record {index}: {str(e)}")
            result['issues'].append(f"Validation error: {str(e)}")
        
        return result
    
    def _clean_record_data(self, record: Dict) -> Dict:
        """
        Clean and standardize record data
        """
        cleaned_record = {}
        for key, value in record.items():
            if pd.isna(value) or value is None:
                cleaned_record[key] = ''
            else:
                # Convert to string and clean up
                str_value = str(value).strip()
                # Remove .0 from float values that are actually integers
                if str_value.endswith('.0') and str_value.replace('.0', '').isdigit():
                    str_value = str_value.replace('.0', '')
                cleaned_record[key] = str_value
        return cleaned_record
    
    def _analyze_field_mappings_v2(self, record: Dict) -> Dict[str, Any]:
        """
        Enhanced field mapping analysis based on real M1 patterns
        """
        analysis = {
            'mapped_fields': {},
            'unmapped_fields': [],
            'suggestions': {},
            'accuracy': 0
        }
        
        total_fields = 0
        correctly_mapped = 0
        
        for field, value in record.items():
            if value and str(value).strip() and str(value).lower() != 'nan':
                total_fields += 1
                
                # Check if field name is correct
                if field in self.reverse_mappings:
                    analysis['mapped_fields'][field] = {
                        'status': 'correct',
                        'm1_field': self.reverse_mappings[field]
                    }
                    correctly_mapped += 1
                else:
                    analysis['unmapped_fields'].append(field)
                    
                    # Get suggestions for incorrect field names
                    suggestions = self.field_mapper.suggest_field_mapping(field, 'address')
                    if suggestions:
                        analysis['suggestions'][field] = suggestions[:3]  # Top 3 suggestions
        
        if total_fields > 0:
            analysis['accuracy'] = (correctly_mapped / total_fields) * 100
        
        return analysis
    
    def _validate_edit_code_requirements(self, record: Dict) -> List[str]:
        """
        Validate edit code specific requirements based on M1 documentation
        """
        issues = []
        edit_code = record.get('edit_code', '')
        
        if not edit_code:
            issues.append("Edit code is mandatory for every M1 record")
            return issues
        
        if edit_code not in self.edit_code_requirements:
            issues.append(f"Invalid edit code: {edit_code}")
            return issues
        
        requirements = self.edit_code_requirements[edit_code]
        
        # Check required fields
        for field in requirements['required_fields']:
            if not record.get(field) or str(record.get(field)).strip() == '':
                issues.append(f"Required field '{field}' missing for edit code {edit_code}")
        
        # Check comment patterns
        comment = record.get('comments', '')
        if comment:
            comment_lower = comment.lower()
            expected_patterns = requirements['comment_patterns']
            if not any(pattern in comment_lower for pattern in expected_patterns):
                issues.append(f"Comment should better describe the {requirements['description']}")
        
        return issues
    
    def _detect_common_error_patterns(self, record: Dict) -> List[str]:
        """
        Detect common error patterns from training data
        """
        issues = []
        
        # Check for road-locality combination issues
        road_name = record.get('road_name', '')
        locality_name = record.get('locality_name', '')
        new_road = record.get('new_road', '')
        
        if road_name and locality_name and not new_road:
            # This is a potential road-locality combination issue
            issues.append("Consider adding 'Y' to new_road field for new road-locality combinations")
        
        # Check LGA code against the configured LGA_CODE (no hardcoded value).
        expected_lga = os.getenv('LGA_CODE', '')
        lga_code = record.get('lga_code', '')
        if expected_lga and lga_code and lga_code != expected_lga:
            issues.append(f"LGA code {lga_code} does not match configured LGA_CODE {expected_lga}")
        
        # Check for missing coordinates when required
        distance_related = record.get('distance_related_flag', '')
        is_primary = record.get('is_primary', '')
        easting = record.get('easting', '')
        northing = record.get('northing', '')
        
        if distance_related == 'Y' or is_primary == 'N':
            if not easting or not northing:
                issues.append("Coordinates (easting/northing) required for distance-based or secondary addresses")
        
        return issues
    
    def _apply_auto_fixes(self, record: Dict, auto_fixes: Dict) -> Dict:
        """
        Apply auto-fixes to record
        """
        for field, value in auto_fixes.items():
            if field in record:
                record[field] = value
        return record
    
    def _check_edit_code_compliance(self, record: Dict) -> float:
        """
        Check compliance with edit code requirements
        """
        edit_code = record.get('edit_code', '')
        if not edit_code or edit_code not in self.edit_code_requirements:
            return 0.0
        
        requirements = self.edit_code_requirements[edit_code]
        required_fields = requirements['required_fields']
        
        present_fields = sum(1 for field in required_fields if record.get(field))
        return (present_fields / len(required_fields)) * 100
    
    def _calculate_data_quality_score(self, record: Dict) -> float:
        """
        Calculate overall data quality score
        """
        total_fields = len([v for v in record.values() if v and str(v).strip()])
        if total_fields == 0:
            return 0.0
        
        # Check for common data quality issues
        quality_issues = 0
        
        # Check for empty required fields
        required_fields = ['edit_code', 'lga_code']
        for field in required_fields:
            if not record.get(field) or str(record.get(field)).strip() == '':
                quality_issues += 1
        
        # Check for numeric fields that should be numeric
        numeric_fields = ['house_number_1', 'propnum', 'crefno']
        for field in numeric_fields:
            value = record.get(field, '')
            if value and not str(value).replace('.', '').isdigit():
                quality_issues += 1
        
        return max(0, (total_fields - quality_issues) / total_fields * 100)
    
    def _generate_validation_report_v2(self, validation_results: List[Dict], 
                                     total_records: int, valid_records: int, 
                                     auto_fixed_records: int) -> Dict[str, Any]:
        """
        Generate comprehensive validation report
        """
        validation_rate = (valid_records / total_records * 100) if total_records > 0 else 0
        
        # Analyze error patterns
        error_analysis = {}
        for result in validation_results:
            for issue in result['issues']:
                error_type = self._categorize_error(issue)
                error_analysis[error_type] = error_analysis.get(error_type, 0) + 1
        
        # Calculate AI insights
        field_mapping_scores = [r['ai_insights'].get('field_mapping_accuracy', 0) for r in validation_results]
        comment_quality_scores = [r['ai_insights'].get('comment_quality', 0) for r in validation_results]
        
        avg_field_mapping = sum(field_mapping_scores) / len(field_mapping_scores) if field_mapping_scores else 0
        avg_comment_quality = sum(comment_quality_scores) / len(comment_quality_scores) if comment_quality_scores else 0
        
        return {
            'summary': {
                'total_records': total_records,
                'valid_records': valid_records,
                'invalid_records': total_records - valid_records,
                'auto_fixed': auto_fixed_records,
                'validation_rate': round(validation_rate, 1),
                'processing_time': 0.0  # Could be calculated if needed
            },
            'error_analysis': error_analysis,
            'ai_insights': {
                'field_mapping_accuracy': round(avg_field_mapping, 1),
                'comment_quality_score': round(avg_comment_quality, 1),
                'edit_code_compliance': round(sum(r['ai_insights'].get('edit_code_compliance', 0) for r in validation_results) / len(validation_results), 1) if validation_results else 0,
                'data_quality_score': round(sum(r['ai_insights'].get('data_quality_score', 0) for r in validation_results) / len(validation_results), 1) if validation_results else 0
            },
            'validation_results': validation_results,
            'recommendations': self._generate_recommendations(validation_rate, error_analysis, avg_field_mapping)
        }
    
    def _categorize_error(self, error_message: str) -> str:
        """
        Categorize error message
        """
        error_lower = error_message.lower()
        
        if 'road-locality' in error_lower:
            return 'road_locality_not_found'
        elif 'property' in error_lower and 'not found' in error_lower:
            return 'property_not_found'
        elif 'timeout' in error_lower:
            return 'timeout'
        elif 'required field' in error_lower:
            return 'missing_field'
        elif 'invalid' in error_lower:
            return 'invalid_format'
        else:
            return 'other'
    
    def _generate_recommendations(self, validation_rate: float, error_analysis: Dict, 
                                field_mapping_accuracy: float) -> List[str]:
        """
        Generate recommendations based on validation results
        """
        recommendations = []
        
        if validation_rate < 80:
            recommendations.append("Validation rate is below 80% - review common error patterns")
        
        if field_mapping_accuracy < 95:
            recommendations.append("Field mapping accuracy is below 95% - verify field names against M1 documentation")
        
        if error_analysis.get('road_locality_not_found', 0) > 0:
            recommendations.append("Multiple road-locality errors detected - consider adding 'Y' to new_road field")
        
        if error_analysis.get('missing_field', 0) > 0:
            recommendations.append("Missing required fields detected - review edit code requirements")
        
        return recommendations
