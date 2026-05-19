"""
Database Relationship Validator
Analyzes database relationships and validates M1 records against actual database data
"""
import logging
import pyodbc
import pandas as pd
from typing import Dict, List, Optional, Tuple
from .database_helper import InfoProdDatabaseHelper


class DatabaseRelationshipValidator:
    """
    Validates M1 records by checking relationships in InfoProd database
    Ensures data consistency and correctness based on actual database records
    """
    
    def __init__(self, db_helper: InfoProdDatabaseHelper = None):
        """
        Initialize the validator
        
        Args:
            db_helper: Database helper instance (optional)
        """
        self.db_helper = db_helper or InfoProdDatabaseHelper()
        self.logger = logging.getLogger('DatabaseRelationshipValidator')
        
        # Cache for database analysis
        self.table_relationships = {}
        self.column_mappings = {}
        self.validation_rules = []
        
        # Analyze database structure on initialization
        self._analyze_database_structure()
    
    def _analyze_database_structure(self):
        """Analyze database structure to understand relationships"""
        try:
            connection = self.db_helper._get_connection()
            cursor = connection.cursor()
            
            # Get all tables with foreign keys to understand relationships
            relationships_query = """
                SELECT 
                    fk.TABLE_SCHEMA,
                    fk.TABLE_NAME AS FK_Table,
                    ccu.COLUMN_NAME AS FK_Column,
                    rc.UNIQUE_CONSTRAINT_NAME,
                    rc.TABLE_SCHEMA AS REF_TABLE_SCHEMA,
                    rc.TABLE_NAME AS REF_Table,
                    kcu.COLUMN_NAME AS REF_Column
                FROM INFORMATION_SCHEMA.FOREIGN_KEY_COLUMNS ccu
                INNER JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
                    ON ccu.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
                INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                    ON rc.UNIQUE_CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                INNER JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS fk
                    ON ccu.CONSTRAINT_NAME = fk.CONSTRAINT_NAME
                WHERE fk.CONSTRAINT_TYPE = 'FOREIGN KEY'
            """
            
            cursor.execute(relationships_query)
            rows = cursor.fetchall()
            
            # Build relationship map
            for row in rows:
                fk_schema, fk_table, fk_column, _, ref_schema, ref_table, ref_column = row
                fk_table_full = f"{fk_schema}.{fk_table}"
                ref_table_full = f"{ref_schema}.{ref_table}"
                
                if fk_table_full not in self.table_relationships:
                    self.table_relationships[fk_table_full] = []
                
                self.table_relationships[fk_table_full].append({
                    'fk_column': fk_column,
                    'ref_table': ref_table_full,
                    'ref_column': ref_column
                })
            
            cursor.close()
            connection.close()
            
            self.logger.info(f"Analyzed {len(self.table_relationships)} table relationships")
            
        except Exception as e:
            self.logger.error(f"Error analyzing database structure: {e}")
    
    def validate_m1_record(self, m1_record: Dict) -> Dict:
        """
        Validate an M1 record against database relationships
        
        Args:
            m1_record: M1 record to validate
            
        Returns:
            Validation results dictionary
        """
        results = {
            'valid': True,
            'issues': [],
            'suggestions': [],
            'verified_data': {},
            'database_checks': []
        }
        
        # Extract key fields from M1 record - handle float values
        def clean_field(value):
            if pd.isna(value) or value is None:
                return ''
            if isinstance(value, float):
                if value.is_integer():
                    return str(int(value))
                else:
                    return str(value)
            return str(value).strip()
        
        propnum = clean_field(m1_record.get('propnum', ''))
        property_pfi = clean_field(m1_record.get('property_pfi', ''))
        parcel_pfi = clean_field(m1_record.get('parcel_pfi', ''))
        address_pfi = clean_field(m1_record.get('address_pfi', ''))
        spi = clean_field(m1_record.get('spi', ''))
        
        # 1. Validate Property Number
        if propnum:
            propnum_check = self._check_property_number(propnum, m1_record)
            results['database_checks'].append({
                'check': 'property_number',
                'field': 'propnum',
                'value': propnum,
                'result': propnum_check
            })
            
            if not propnum_check['valid']:
                # If property not found by propnum, try to find by address and plan
                # This is for new properties (Status='C')
                plan_number = m1_record.get('plan_number', '').strip()
                address_data = {
                    'road_name': m1_record.get('road_name', ''),
                    'locality_name': m1_record.get('locality_name', ''),
                    'house_number_1': m1_record.get('house_number_1', '')
                }
                
                if any(address_data.values()) or plan_number:
                    # Try to find by address and plan
                    property_by_address = self.db_helper.find_property_by_address_and_plan(
                        address_data, 
                        plan_number=plan_number
                    )
                    
                    if property_by_address:
                        propnum_check['valid'] = True
                        propnum_check['issues'] = []
                        propnum_check['data'] = property_by_address
                        propnum_check['_found_by_address'] = True
                        results['verified_data'].update(propnum_check.get('data', {}))
            
            if not propnum_check['valid']:
                results['valid'] = False
                results['issues'].extend(propnum_check['issues'])
            else:
                results['verified_data'].update(propnum_check.get('data', {}))
        
        # 2. Validate Property-Parcel Relationship
        if property_pfi and parcel_pfi:
            relationship_check = self._check_property_parcel_relationship(property_pfi, parcel_pfi)
            results['database_checks'].append({
                'check': 'property_parcel_relationship',
                'fields': ['property_pfi', 'parcel_pfi'],
                'values': [property_pfi, parcel_pfi],
                'result': relationship_check
            })
            
            if not relationship_check['valid']:
                results['valid'] = False
                results['issues'].extend(relationship_check['issues'])
        
        # 3. Validate Parcel SPI
        if spi:
            spi_check = self._check_parcel_spi(spi, m1_record)
            results['database_checks'].append({
                'check': 'parcel_spi',
                'field': 'spi',
                'value': spi,
                'result': spi_check
            })
            
            if not spi_check['valid']:
                results['valid'] = False
                results['issues'].extend(spi_check['issues'])
        
        # 4. Validate Address
        if m1_record.get('road_name') or m1_record.get('locality_name'):
            address_check = self._check_address(m1_record)
            results['database_checks'].append({
                'check': 'address',
                'fields': ['road_name', 'locality_name', 'house_number_1'],
                'result': address_check
            })
            
            if not address_check['valid']:
                results['valid'] = False
                results['issues'].extend(address_check['issues'])
        
        # 5. Validate Rates Data
        if propnum:
            rates_check = self._check_rates_data(propnum, m1_record)
            results['database_checks'].append({
                'check': 'rates_data',
                'field': 'propnum',
                'value': propnum,
                'result': rates_check
            })
            
            if rates_check.get('data'):
                results['verified_data']['rates'] = rates_check['data']
        
        return results
    
    def _check_property_number(self, propnum: str, m1_record: Dict) -> Dict:
        """
        Check property number against database
        
        Args:
            propnum: Property number to check
            m1_record: Full M1 record for context
            
        Returns:
            Check results dictionary
        """
        result = {
            'valid': False,
            'issues': [],
            'data': {}
        }
        
        try:
            # Try to find property in database
            property_data = self.db_helper.find_property_by_propnum(propnum)
            
            if not property_data:
                result['issues'].append(f'Property number {propnum} not found in InfoProd database')
                return result
            
            result['valid'] = True
            result['data'] = property_data
            
            # Check LGA code consistency
            if 'lga_code' in m1_record and m1_record['lga_code']:
                db_lga = property_data.get('LGA_CODE', property_data.get('LgaCode', ''))
                if db_lga and str(db_lga).strip() != str(m1_record['lga_code']).strip():
                    result['issues'].append(
                        f'LGA code mismatch: M1 has {m1_record["lga_code"]}, '
                        f'database has {db_lga}'
                    )
                    result['valid'] = False
            
            # Check property status
            status = property_data.get('STATUS', '').upper()
            if status in ['DELETED', 'INACTIVE', 'CANCELLED']:
                result['issues'].append(f'Property has inactive status: {status}')
                result['valid'] = False
            
            # Store verified property data
            result['data'] = {
                'property_number': propnum,
                'status': status,
                'address': property_data.get('Formatted_Address', property_data.get('Address', '')),
                'verified': True
            }
            
        except Exception as e:
            self.logger.error(f"Error checking property number {propnum}: {e}")
            result['issues'].append(f'Error validating property number: {str(e)}')
        
        return result
    
    def _check_property_parcel_relationship(self, property_pfi: str, parcel_pfi: str) -> Dict:
        """
        Check property-parcel relationship
        
        Args:
            property_pfi: Property PFI
            parcel_pfi: Parcel PFI
            
        Returns:
            Check results dictionary
        """
        result = {
            'valid': True,
            'issues': []
        }
        
        try:
            # This would check if the property and parcel are related in the database
            # Implementation depends on specific database schema
            pass
            
        except Exception as e:
            self.logger.error(f"Error checking property-parcel relationship: {e}")
            result['issues'].append(f'Error checking relationship: {str(e)}')
            result['valid'] = False
        
        return result
    
    def _check_parcel_spi(self, spi: str, m1_record: Dict) -> Dict:
        """
        Check parcel SPI
        
        Args:
            spi: Standard Parcel Identifier
            m1_record: Full M1 record for context
            
        Returns:
            Check results dictionary
        """
        result = {
            'valid': False,
            'issues': []
        }
        
        try:
            # Try to find parcel by SPI
            parcel_data = self.db_helper.validate_spi(spi)
            
            if not parcel_data[0]:  # validate_spi returns (bool, issues)
                result['issues'].extend(parcel_data[1])
                return result
            
            result['valid'] = True
            
        except Exception as e:
            self.logger.error(f"Error checking parcel SPI {spi}: {e}")
            result['issues'].append(f'Error validating SPI: {str(e)}')
        
        return result
    
    def _check_address(self, m1_record: Dict) -> Dict:
        """
        Check address against database
        
        Args:
            m1_record: M1 record with address fields
            
        Returns:
            Check results dictionary
        """
        result = {
            'valid': True,
            'issues': [],
            'suggestions': []
        }
        
        try:
            address_data = {
                'road_name': m1_record.get('road_name', '').upper(),
                'locality_name': m1_record.get('locality_name', '').upper(),
                'house_number_1': m1_record.get('house_number_1', '')
            }
            
            # Find related records by address
            related_records = self.db_helper.find_address_relationships(address_data)
            
            if related_records:
                result['suggestions'].append(
                    f'Found {len(related_records)} related records with similar address'
                )
                
                # Check for potential duplicates
                if m1_record.get('edit_code') != 'A':  # Not a new property
                    similar_properties = [
                        r for r in related_records 
                        if r.get('propnum') == m1_record.get('propnum')
                    ]
                    
                    if similar_properties:
                        result['issues'].append('Potential duplicate property found with same address')
                        result['valid'] = False
            else:
                # No address found in database
                if m1_record.get('new_road') != 'Y':
                    result['issues'].append(
                        'Address not found in database and new_road flag not set'
                    )
                    result['valid'] = False
                    result['suggestions'].append(
                        'Consider setting new_road flag if this is a new road'
                    )
        
        except Exception as e:
            self.logger.error(f"Error checking address: {e}")
            result['issues'].append(f'Error validating address: {str(e)}')
            result['valid'] = False
        
        return result
    
    def _check_rates_data(self, propnum: str, m1_record: Dict) -> Dict:
        """
        Check rates/valuation data for property
        
        Args:
            propnum: Property number
            m1_record: Full M1 record for context
            
        Returns:
            Check results dictionary
        """
        result = {
            'valid': True,
            'issues': [],
            'data': None
        }
        
        try:
            # Get rates data from database
            rates_data = self.db_helper.get_rates_data(propnum)
            
            if rates_data:
                result['data'] = rates_data
                result['valid'] = True
            else:
                result['issues'].append('No rates data found for this property')
        
        except Exception as e:
            self.logger.error(f"Error checking rates data: {e}")
            # Don't fail validation if rates data is missing
        
        return result
    
    def get_validation_summary(self, validation_results: List[Dict]) -> Dict:
        """
        Get summary of validation results
        
        Args:
            validation_results: List of validation results
            
        Returns:
            Summary dictionary
        """
        total = len(validation_results)
        valid = sum(1 for r in validation_results if r.get('valid'))
        
        return {
            'total_records': total,
            'valid': valid,
            'invalid': total - valid,
            'validation_rate': (valid / total * 100) if total > 0 else 0,
            'common_issues': self._get_common_issues(validation_results)
        }
    
    def _get_common_issues(self, validation_results: List[Dict]) -> List[str]:
        """Extract common issues from validation results"""
        all_issues = []
        
        for result in validation_results:
            all_issues.extend(result.get('issues', []))
        
        # Count issue frequency
        issue_counts = {}
        for issue in all_issues:
            issue_key = issue.split(':')[0] if ':' in issue else issue
            issue_counts[issue_key] = issue_counts.get(issue_key, 0) + 1
        
        # Return top 5 most common issues
        sorted_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)
        return [issue[0] for issue in sorted_issues[:5]]
