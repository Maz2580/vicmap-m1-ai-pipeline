"""
Enhanced M1 Validator with Database Integration
Uses InfoProd database to enhance validation accuracy
"""
import logging
from typing import Dict, List, Any, Tuple, Optional
from .enhanced_m1_validator_v2 import EnhancedM1ValidatorV2
from .database_helper import InfoProdDatabaseHelper
from .database_relationship_validator import DatabaseRelationshipValidator

class DatabaseEnhancedM1Validator(EnhancedM1ValidatorV2):
    """
    Enhanced M1 Validator that integrates with InfoProd database
    Uses database lookups for property, parcel, and rates data
    """
    
    def __init__(self):
        """Initialize the database-enhanced validator"""
        super().__init__()
        self.logger = logging.getLogger('DatabaseEnhancedValidator')
        
        # Initialize database helper
        try:
            self.db_helper = InfoProdDatabaseHelper()
            self.logger.info("Database connection established successfully")
        except Exception as e:
            self.logger.error(f"Failed to connect to database: {e}")
            self.db_helper = None
        
        # Initialize database relationship validator
        try:
            self.relationship_validator = DatabaseRelationshipValidator(self.db_helper)
            self.logger.info("Database relationship validator initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize relationship validator: {e}")
            self.relationship_validator = None
    
    def validate_m1_file(self, file_path: str, auto_fix: bool = False) -> Dict[str, any]:
        """
        Validate M1 file with database-enhanced validation
        
        Args:
            file_path: Path to M1 file
            auto_fix: Whether to apply auto-fixes
            
        Returns:
            Validation results dictionary with database insights
        """
        # Run standard validation first
        results = super().validate_m1_file(file_path, auto_fix)
        
        # Enhance results with database lookups
        if self.db_helper:
            results = self._enhance_with_database(results)
        
        return results
    
    def _enhance_with_database(self, validation_results: Dict) -> Dict:
        """
        Enhance validation results with database lookups
        
        Args:
            validation_results: Original validation results
            
        Returns:
            Enhanced validation results with database insights
        """
        enhanced_results = validation_results.copy()
        
        # Add database validation section
        if 'validation_results' in enhanced_results and self.relationship_validator:
            database_insights = []
            
            for record in enhanced_results['validation_results']:
                # Use relationship validator for comprehensive database checks
                db_validation = self.relationship_validator.validate_m1_record(record)
                
                if db_validation:
                    database_insights.append({
                        'record_index': record.get('record_index'),
                        'valid': db_validation.get('valid'),
                        'issues': db_validation.get('issues', []),
                        'suggestions': db_validation.get('suggestions', []),
                        'verified_data': db_validation.get('verified_data', {}),
                        'database_checks': db_validation.get('database_checks', [])
                    })
            
            enhanced_results['database_insights'] = database_insights
            
            # Add database summary to overall summary
            if 'summary' not in enhanced_results:
                enhanced_results['summary'] = {}
            
            summary = self.relationship_validator.get_validation_summary(database_insights)
            enhanced_results['summary'].update(summary)
            enhanced_results['summary']['database_verified'] = summary.get('valid', 0)
            enhanced_results['summary']['database_issues'] = summary.get('invalid', 0)
        
        return enhanced_results
    
    def _analyze_record_with_database(self, record: Dict) -> Optional[Dict]:
        """
        Analyze a record using database lookups
        
        Args:
            record: M1 record to analyze
            
        Returns:
            Database insights for the record
        """
        if not self.db_helper:
            return None
        
        insights = {
            'record_index': record.get('record_index'),
            'propnum': record.get('propnum', ''),
            'verified': False,
            'issues': [],
            'suggestions': []
        }
        
        # Extract propnum for database lookup
        propnum = record.get('propnum', '').strip()
        
        if not propnum:
            insights['issues'].append('Property number (propnum) is required for database verification')
            return insights
        
        # Try to find property in database
        property_data = self.db_helper.find_property_by_propnum(propnum)
        
        if property_data:
            insights['verified'] = True
            insights['property_found'] = True
            
            # Check for data consistency
            consistency_issues = self._check_data_consistency(record, property_data)
            if consistency_issues:
                insights['issues'].extend(consistency_issues)
            
            # Check rates data
            rates_data = self.db_helper.get_rates_data(propnum)
            if rates_data:
                insights['rates_verified'] = True
                insights['rates_data'] = rates_data
            else:
                insights['issues'].append('Rates data not found for property')
        
        else:
            insights['property_found'] = False
            insights['issues'].append(f'Property {propnum} not found in InfoProd database')
        
        # Check address relationships
        if record.get('road_name') or record.get('locality_name'):
            address_data = {
                'road_name': record.get('road_name', ''),
                'locality_name': record.get('locality_name', ''),
                'house_number_1': record.get('house_number_1', '')
            }
            
            related_records = self.db_helper.find_address_relationships(address_data)
            if related_records:
                insights['address_relationships'] = len(related_records)
                
                # Check if we're creating a duplicate
                similar_properties = [r for r in related_records if r.get('propnum') == propnum]
                if similar_properties and not record.get('edit_code') == 'A':
                    insights['issues'].append('Potential duplicate property detected')
        
        return insights
    
    def _check_data_consistency(self, record: Dict, property_data: Dict) -> List[str]:
        """
        Check consistency between M1 record and database property data
        
        Args:
            record: M1 record
            property_data: Property data from database
            
        Returns:
            List of consistency issues
        """
        issues = []
        
        # Check property number consistency
        if property_data.get('TPKLPAPROP'):
            if property_data.get('TPKLPAPROP').strip() != record.get('propnum', '').strip():
                issues.append('Property number mismatch with database')
        
        # Check LGA code consistency
        if record.get('lga_code'):
            db_lga = property_data.get('LGA_CODE', property_data.get('LgaCode', ''))
            if db_lga and db_lga.strip() != record.get('lga_code', '').strip():
                issues.append(f'LGA code mismatch: DB has {db_lga}, M1 has {record.get("lga_code")}')
        
        # Check property status
        if property_data.get('STATUS'):
            status = property_data.get('STATUS').upper()
            if status in ['DELETED', 'INACTIVE', 'CANCELLED']:
                issues.append(f'Property status in database is {status}')
        
        return issues
    
    def validate_propnum_with_database(self, propnum: str) -> Tuple[bool, List[str]]:
        """
        Validate property number using database lookup
        
        Args:
            propnum: Property number to validate
            
        Returns:
            Tuple of (is_valid, issues_list)
        """
        if not self.db_helper:
            return False, ['Database connection not available']
        
        exists, issues = self.db_helper.validate_property_exists(propnum)
        
        if not exists:
            return False, issues
        
        # Additional validation if property exists
        property_data = self.db_helper.find_property_by_propnum(propnum)
        
        if property_data:
            extra_issues = self._validate_property_data(property_data)
            issues.extend(extra_issues)
        
        return True, issues
    
    def _validate_property_data(self, property_data: Dict) -> List[str]:
        """
        Validate property data from database
        
        Args:
            property_data: Property data from database
            
        Returns:
            List of validation issues
        """
        issues = []
        
        # Check property status
        status = property_data.get('STATUS', '').upper()
        if status in ['DELETED', 'INACTIVE']:
            issues.append(f'Property has status: {status}')
        
        # Check for missing essential data
        if not property_data.get('TPKLPAPROP'):
            issues.append('Property number (TPKLPAPROP) missing in database')
        
        return issues
    
    def enhance_record_with_database_insights(self, record: Dict) -> Dict:
        """
        Enhance a record with database insights
        
        Args:
            record: M1 record to enhance
            
        Returns:
            Enhanced record with database insights
        """
        if not self.db_helper:
            return record
        
        enhanced_record = record.copy()
        propnum = record.get('propnum', '').strip()
        
        if propnum:
            # Get property data
            property_data = self.db_helper.find_property_by_propnum(propnum)
            if property_data:
                enhanced_record['database_verified'] = True
                enhanced_record['property_data'] = property_data
                
                # Try to supplement missing data from database
                if not enhanced_record.get('lga_code') and property_data.get('LGA_CODE'):
                    enhanced_record['lga_code'] = property_data.get('LGA_CODE')
                
                if not enhanced_record.get('property_type') and property_data.get('PROPERTY_TYPE'):
                    enhanced_record['property_type'] = property_data.get('PROPERTY_TYPE')
                
                # Get rates data
                rates_data = self.db_helper.get_rates_data(propnum)
                if rates_data:
                    enhanced_record['rates_data'] = rates_data
            
            else:
                enhanced_record['database_verified'] = False
                enhanced_record['database_warning'] = f'Property {propnum} not found in InfoProd database'
        
        return enhanced_record
    
    def get_database_info(self) -> Dict:
        """Get database connection and structure information"""
        if not self.db_helper:
            return {'connected': False, 'error': 'Database not connected'}
        
        return {
            'connected': True,
            'server': self.db_helper.server,
            'database': self.db_helper.database,
            'tables': {
                'property': self.db_helper.property_table,
                'parcel': self.db_helper.parcel_table,
                'rates': self.db_helper.rates_table
            },
            'all_tables': self.db_helper.get_all_tables()
        }
