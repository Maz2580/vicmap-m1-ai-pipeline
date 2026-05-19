#!/usr/bin/env python3
"""
Comprehensive POZI M1 Validation with Row Decision Logic
Analyzes which rows to keep/reject based on property relationships
"""

import os
import sys
import pandas as pd
import logging
from datetime import datetime
import re

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v2_m1_ai_validator.data_processing.enhanced_validator_with_database import DatabaseEnhancedM1Validator
from v2_m1_ai_validator.data_processing.database_helper import InfoProdDatabaseHelper

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('POZI_Comprehensive_Test')

class POZIRowValidator:
    """Enhanced validator for POZI M1 rows with keep/reject logic"""
    
    def __init__(self):
        self.db_helper = InfoProdDatabaseHelper()
        self.validator = DatabaseEnhancedM1Validator()
        
        # Track property relationships
        self.property_relationships = {}
        self.parent_properties = set()
        self.child_properties = set()
        
    def analyze_property_relationships(self, df):
        """Analyze property relationships from comments"""
        logger.info("Analyzing property relationships from comments...")
        
        for idx, row in df.iterrows():
            comment = str(row.get('comments', ''))
            propnum = str(row.get('propnum', ''))
            
            if comment and propnum:
                # Extract parent property from comment
                # Pattern: "as new multi-assessment to property XXXXX"
                parent_match = re.search(r'to property (\d+)', comment)
                if parent_match:
                    parent_prop = parent_match.group(1)
                    
                    if propnum not in self.property_relationships:
                        self.property_relationships[propnum] = []
                    
                    self.property_relationships[propnum].append({
                        'parent': parent_prop,
                        'row': idx,
                        'comment': comment
                    })
                    
                    self.parent_properties.add(parent_prop)
                    self.child_properties.add(propnum)
        
        logger.info(f"Found {len(self.property_relationships)} property relationships")
        logger.info(f"Parent properties: {len(self.parent_properties)}")
        logger.info(f"Child properties: {len(self.child_properties)}")
        
        return self.property_relationships
    
    def validate_row_decision(self, row, row_idx):
        """Determine if a row should be kept or rejected"""
        propnum = str(row.get('propnum', ''))
        comment = str(row.get('comments', ''))
        edit_code = str(row.get('edit_code', ''))
        
        decision = {
            'row_index': row_idx,
            'propnum': propnum,
            'edit_code': edit_code,
            'decision': 'KEEP',  # Default to keep
            'reason': '',
            'issues': [],
            'suggestions': []
        }
        
        # Check if this is a child property trying to add to old parent
        if propnum in self.property_relationships:
            relationships = self.property_relationships[propnum]
            
            for rel in relationships:
                parent_prop = rel['parent']
                
                # Check if parent property exists in database
                try:
                    parent_result = self.db_helper.find_property_by_propnum(parent_prop, check_new_properties=True)
                    
                    if parent_result:
                        parent_status = parent_result.get('Status', '')
                        parent_tpklpaprop = parent_result.get('TPKLPAPROP', '')
                        
                        # If parent is Status='C' (new), this is likely a duplicate/conflict
                        if parent_status == 'C':
                            decision['decision'] = 'REJECT'
                            decision['reason'] = f"Parent property {parent_prop} is already Status='C' (new property)"
                            decision['issues'].append(f"Conflict: Parent property {parent_prop} is already marked as new")
                            decision['suggestions'].append("Remove this row - parent property already processed")
                            
                        # If parent exists but child is also Status='C', potential conflict
                        elif parent_tpklpaprop and parent_tpklpaprop != parent_prop:
                            decision['decision'] = 'REJECT'
                            decision['reason'] = f"Parent property {parent_prop} has different TPKLPAPROP ({parent_tpklpaprop})"
                            decision['issues'].append(f"Data inconsistency: Parent property mismatch")
                            decision['suggestions'].append("Verify parent property relationship")
                    
                    else:
                        # Parent not found - might be legitimate new relationship
                        decision['reason'] = f"Parent property {parent_prop} not found in database"
                        decision['suggestions'].append("Verify parent property exists")
                        
                except Exception as e:
                    decision['issues'].append(f"Error checking parent property: {e}")
        
        # Additional validation rules
        if edit_code == 'A' and not comment:
            decision['decision'] = 'REJECT'
            decision['reason'] = "Edit code 'A' requires comment"
            decision['issues'].append("Missing required comment for edit code A")
        
        # Check for duplicate propnums in same batch
        if propnum in self.child_properties:
            # Count how many times this propnum appears
            propnum_count = sum(1 for rel in self.property_relationships.get(propnum, []) 
                              if rel['row'] != row_idx)
            
            if propnum_count > 0:
                decision['issues'].append(f"Duplicate propnum {propnum} appears {propnum_count + 1} times")
                if propnum_count > 2:  # More than 3 total occurrences
                    decision['decision'] = 'REJECT'
                    decision['reason'] = f"Too many duplicate propnums ({propnum_count + 1})"
        
        return decision
    
    def validate_all_rows(self, df):
        """Validate all rows and provide keep/reject decisions"""
        logger.info(f"Validating {len(df)} rows...")
        
        # First, analyze relationships
        self.analyze_property_relationships(df)
        
        results = []
        
        for idx, row in df.iterrows():
            if idx % 100 == 0:
                logger.info(f"Processing row {idx}/{len(df)}")
            
            # Get row decision
            decision = self.validate_row_decision(row, idx)
            
            # Add database validation
            try:
                # Clean row data
                clean_row = {}
                for key, value in row.items():
                    if pd.isna(value) or value is None:
                        clean_row[key] = ''
                    elif isinstance(value, float):
                        if value.is_integer():
                            clean_row[key] = str(int(value))
                        else:
                            clean_row[key] = str(value)
                    else:
                        clean_row[key] = str(value).strip()
                
                # Database validation
                if self.validator.relationship_validator:
                    db_result = self.validator.relationship_validator.validate_m1_record(clean_row)
                    if db_result:
                        decision['database_valid'] = db_result.get('valid', False)
                        decision['database_issues'] = db_result.get('issues', [])
                        decision['verified_data'] = db_result.get('verified_data', {})
                    else:
                        decision['database_valid'] = False
                        decision['database_issues'] = ['Database validation failed']
                
            except Exception as e:
                decision['database_valid'] = False
                decision['database_issues'] = [f'Database validation error: {e}']
            
            results.append(decision)
        
        return results
    
    def generate_summary_report(self, results):
        """Generate comprehensive summary report"""
        logger.info("Generating summary report...")
        
        total_rows = len(results)
        keep_rows = sum(1 for r in results if r['decision'] == 'KEEP')
        reject_rows = sum(1 for r in results if r['decision'] == 'REJECT')
        
        # Analyze reasons for rejection
        rejection_reasons = {}
        for result in results:
            if result['decision'] == 'REJECT':
                reason = result['reason']
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
        
        # Analyze issues
        all_issues = []
        for result in results:
            all_issues.extend(result.get('issues', []))
        
        issue_counts = {}
        for issue in all_issues:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1
        
        # Database validation stats
        db_valid = sum(1 for r in results if r.get('database_valid', False))
        db_invalid = total_rows - db_valid
        
        summary = {
            'total_rows': total_rows,
            'keep_rows': keep_rows,
            'reject_rows': reject_rows,
            'keep_percentage': (keep_rows / total_rows) * 100,
            'rejection_reasons': rejection_reasons,
            'common_issues': dict(sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
            'database_stats': {
                'valid': db_valid,
                'invalid': db_invalid,
                'valid_percentage': (db_valid / total_rows) * 100
            },
            'property_relationships': {
                'total_relationships': len(self.property_relationships),
                'parent_properties': len(self.parent_properties),
                'child_properties': len(self.child_properties)
            }
        }
        
        return summary

def main():
    """Main validation function"""
    logger.info("🚀 POZI M1 COMPREHENSIVE VALIDATION TEST")
    logger.info("=" * 60)
    
    # Load POZI M1 file
    file_path = os.getenv("SAMPLE_M1_CSV", "tests/fixtures/sample_m1.csv")
    
    logger.info(f"Loading POZI M1 file: {file_path}")
    df = pd.read_csv(file_path)
    logger.info(f"File loaded: {len(df)} records")
    
    # Initialize validator
    validator = POZIRowValidator()
    
    # Validate all rows
    logger.info("Starting comprehensive validation...")
    results = validator.validate_all_rows(df)
    
    # Generate summary
    summary = validator.generate_summary_report(results)
    
    # Print detailed results
    logger.info(f"\n{'='*60}")
    logger.info("COMPREHENSIVE VALIDATION RESULTS")
    logger.info(f"{'='*60}")
    
    logger.info(f"Total Rows: {summary['total_rows']}")
    logger.info(f"Keep Rows: {summary['keep_rows']} ({summary['keep_percentage']:.1f}%)")
    logger.info(f"Reject Rows: {summary['reject_rows']} ({100-summary['keep_percentage']:.1f}%)")
    
    logger.info(f"\nDatabase Validation:")
    logger.info(f"  Valid: {summary['database_stats']['valid']} ({summary['database_stats']['valid_percentage']:.1f}%)")
    logger.info(f"  Invalid: {summary['database_stats']['invalid']} ({100-summary['database_stats']['valid_percentage']:.1f}%)")
    
    logger.info(f"\nProperty Relationships:")
    logger.info(f"  Total Relationships: {summary['property_relationships']['total_relationships']}")
    logger.info(f"  Parent Properties: {summary['property_relationships']['parent_properties']}")
    logger.info(f"  Child Properties: {summary['property_relationships']['child_properties']}")
    
    logger.info(f"\nRejection Reasons:")
    for reason, count in summary['rejection_reasons'].items():
        logger.info(f"  {reason}: {count} rows")
    
    logger.info(f"\nCommon Issues:")
    for issue, count in list(summary['common_issues'].items())[:5]:
        logger.info(f"  {issue}: {count} times")
    
    # Show specific examples of rejected rows
    logger.info(f"\nSample Rejected Rows:")
    rejected_samples = [r for r in results if r['decision'] == 'REJECT'][:5]
    for sample in rejected_samples:
        logger.info(f"  Row {sample['row_index']}: propnum {sample['propnum']} - {sample['reason']}")
    
    # Show specific examples of kept rows
    logger.info(f"\nSample Kept Rows:")
    kept_samples = [r for r in results if r['decision'] == 'KEEP'][:5]
    for sample in kept_samples:
        logger.info(f"  Row {sample['row_index']}: propnum {sample['propnum']} - {sample['reason'] or 'No issues found'}")
    
    logger.info(f"\n{'='*60}")
    logger.info("🎯 VALIDATION COMPLETE")
    logger.info(f"{'='*60}")
    
    # Save detailed results to CSV
    results_df = pd.DataFrame(results)
    output_file = "pozi_validation_results.csv"
    results_df.to_csv(output_file, index=False)
    logger.info(f"Detailed results saved to: {output_file}")
    
    return results, summary

if __name__ == "__main__":
    main()
