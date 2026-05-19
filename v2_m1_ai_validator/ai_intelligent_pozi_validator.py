#!/usr/bin/env python3
"""
AI-Powered POZI M1 Intelligent Validation System
Based on AI analysis insights, this system makes intelligent decisions about which rows to keep or reject.
"""

import pandas as pd
import logging
import json
from typing import Dict, List, Any, Tuple
import sys
import os
from collections import defaultdict

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v2_m1_ai_validator.data_processing.database_helper import InfoProdDatabaseHelper
from v2_m1_ai_validator.data_processing.database_relationship_validator import DatabaseRelationshipValidator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AIPoziIntelligentValidator:
    """AI-powered intelligent validator for POZI M1 files"""
    
    def __init__(self):
        self.db_helper = InfoProdDatabaseHelper()
        self.db_validator = DatabaseRelationshipValidator()
        self.ai_insights = {}
        self.validation_results = []
        
    def analyze_pozi_patterns(self, df: pd.DataFrame) -> Dict[str, Any]:
        """AI analysis of POZI-specific patterns and relationships"""
        logger.info("AI Pattern Analysis: Understanding POZI data relationships...")
        
        patterns = {
            'propnum_analysis': {},
            'parent_child_relationships': {},
            'comment_analysis': {},
            'duplicate_patterns': {},
            'ai_recommendations': []
        }
        
        # Analyze propnum patterns
        propnum_counts = df['propnum'].value_counts()
        patterns['propnum_analysis'] = {
            'total_unique_propnums': len(propnum_counts),
            'high_duplicate_propnums': propnum_counts[propnum_counts > 10].to_dict(),
            'moderate_duplicate_propnums': propnum_counts[(propnum_counts > 3) & (propnum_counts <= 10)].to_dict(),
            'single_occurrence_propnums': len(propnum_counts[propnum_counts == 1])
        }
        
        # Analyze parent-child relationships from comments
        parent_child_data = self._extract_parent_child_from_comments(df)
        patterns['parent_child_relationships'] = parent_child_data
        
        # Analyze comment patterns
        comment_patterns = self._analyze_comment_patterns(df)
        patterns['comment_analysis'] = comment_patterns
        
        # Analyze duplicate patterns
        duplicate_patterns = self._analyze_duplicate_patterns(df)
        patterns['duplicate_patterns'] = duplicate_patterns
        
        # Generate AI recommendations
        patterns['ai_recommendations'] = self._generate_pattern_recommendations(patterns)
        
        return patterns
    
    def _extract_parent_child_from_comments(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Extract parent-child property relationships from comments"""
        relationships = {
            'total_relationships': 0,
            'parent_properties': set(),
            'child_properties': set(),
            'relationship_details': [],
            'conflict_patterns': []
        }
        
        for idx, row in df.iterrows():
            comment = str(row.get('comments', ''))
            if 'adding propnum' in comment.lower() and 'as new multi-assessment to property' in comment.lower():
                try:
                    # Extract child property (new propnum)
                    child_start = comment.find('adding propnum') + len('adding propnum')
                    child_end = comment.find('(new)')
                    if child_start < child_end:
                        child_propnum = comment[child_start:child_end].strip()
                        
                        # Extract parent property
                        parent_start = comment.find('to property') + len('to property')
                        parent_end = comment.find('(')
                        if parent_start < parent_end:
                            parent_propnum = comment[parent_start:parent_end].strip()
                            
                            relationships['total_relationships'] += 1
                            relationships['parent_properties'].add(parent_propnum)
                            relationships['child_properties'].add(child_propnum)
                            
                            relationships['relationship_details'].append({
                                'row_index': idx,
                                'child_propnum': child_propnum,
                                'parent_propnum': parent_propnum,
                                'comment': comment,
                                'has_warning': 'WARNING' in comment
                            })
                            
                except Exception as e:
                    logger.warning(f"Error parsing comment at row {idx}: {e}")
        
        relationships['parent_properties'] = list(relationships['parent_properties'])
        relationships['child_properties'] = list(relationships['child_properties'])
        
        return relationships
    
    def _analyze_comment_patterns(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze comment patterns for insights"""
        patterns = {
            'total_comments': len(df),
            'warning_count': 0,
            'road_name_warnings': 0,
            'comment_types': defaultdict(int),
            'sample_warnings': []
        }
        
        for idx, row in df.iterrows():
            comment = str(row.get('comments', ''))
            
            if 'WARNING' in comment:
                patterns['warning_count'] += 1
                patterns['sample_warnings'].append({
                    'row_index': idx,
                    'comment': comment[:200] + '...' if len(comment) > 200 else comment
                })
                
                if 'different road names' in comment:
                    patterns['road_name_warnings'] += 1
            
            # Categorize comment types
            if 'adding propnum' in comment.lower():
                patterns['comment_types']['property_addition'] += 1
            elif 'multi-assessment' in comment.lower():
                patterns['comment_types']['multi_assessment'] += 1
            elif 'parcel' in comment.lower():
                patterns['comment_types']['parcel_related'] += 1
        
        return patterns
    
    def _analyze_duplicate_patterns(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze duplicate patterns intelligently"""
        patterns = {
            'propnum_duplicates': {},
            'spi_duplicates': {},
            'address_duplicates': {},
            'duplicate_risk_assessment': {}
        }
        
        # Analyze propnum duplicates
        propnum_counts = df['propnum'].value_counts()
        high_duplicates = propnum_counts[propnum_counts > 20]
        moderate_duplicates = propnum_counts[(propnum_counts > 5) & (propnum_counts <= 20)]
        
        patterns['propnum_duplicates'] = {
            'high_risk': high_duplicates.to_dict(),
            'moderate_risk': moderate_duplicates.to_dict(),
            'total_high_risk_rows': high_duplicates.sum(),
            'total_moderate_risk_rows': moderate_duplicates.sum()
        }
        
        # Analyze SPI duplicates
        spi_counts = df['spi'].value_counts()
        spi_duplicates = spi_counts[spi_counts > 1]
        patterns['spi_duplicates'] = spi_duplicates.to_dict()
        
        return patterns
    
    def _generate_pattern_recommendations(self, patterns: Dict) -> List[str]:
        """Generate AI recommendations based on pattern analysis"""
        recommendations = []
        
        # High duplicate recommendations
        high_duplicates = patterns['propnum_analysis']['high_duplicate_propnums']
        if high_duplicates:
            recommendations.append(f"AI Alert: {len(high_duplicates)} propnums have >10 occurrences - high duplicate risk")
        
        # Parent-child conflict recommendations
        relationships = patterns['parent_child_relationships']
        if relationships['total_relationships'] > 0:
            recommendations.append(f"AI Found: {relationships['total_relationships']} parent-child relationships to validate")
        
        # Warning recommendations
        warnings = patterns['comment_analysis']['warning_count']
        if warnings > 0:
            recommendations.append(f"AI Alert: {warnings} comments contain WARNING flags - manual review needed")
        
        return recommendations
    
    def intelligent_row_validation(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """AI-powered intelligent validation of each row"""
        logger.info("AI Intelligent Validation: Making smart decisions for each row...")
        
        # First, analyze patterns
        patterns = self.analyze_pozi_patterns(df)
        self.ai_insights = patterns
        
        validation_results = []
        
        for idx, row in df.iterrows():
            result = self._validate_single_row_intelligently(row, idx, patterns)
            validation_results.append(result)
        
        return validation_results
    
    def _validate_single_row_intelligently(self, row: pd.Series, row_index: int, patterns: Dict) -> Dict[str, Any]:
        """AI-powered validation of a single row"""
        result = {
            'row_index': row_index,
            'propnum': row.get('propnum'),
            'decision': 'KEEP',  # Default to keep
            'confidence': 1.0,
            'reasons': [],
            'ai_analysis': {},
            'database_validation': {},
            'recommendations': []
        }
        
        propnum = str(row.get('propnum', '')).replace('.0', '')
        comment = str(row.get('comments', ''))
        
        # AI Analysis 1: Duplicate Risk Assessment
        duplicate_risk = self._assess_duplicate_risk(propnum, patterns)
        result['ai_analysis']['duplicate_risk'] = duplicate_risk
        
        if duplicate_risk['risk_level'] == 'HIGH':
            result['decision'] = 'REJECT'
            result['confidence'] = 0.9
            result['reasons'].append(f"High duplicate risk: {duplicate_risk['count']} occurrences")
            result['recommendations'].append("Remove duplicate entries - keep only one instance")
        
        # AI Analysis 2: Parent-Child Conflict Detection
        if result['decision'] == 'KEEP':
            conflict_analysis = self._analyze_parent_child_conflict(row, patterns)
            result['ai_analysis']['parent_child_conflict'] = conflict_analysis
            
            if conflict_analysis and conflict_analysis.get('has_conflict', False):
                result['decision'] = 'REJECT'
                result['confidence'] = 0.95
                result['reasons'].append(f"Parent-child conflict: {conflict_analysis.get('conflict_reason', 'Unknown conflict')}")
                result['recommendations'].append("Parent property already processed - remove this row")
        
        # AI Analysis 3: Comment Warning Analysis
        if result['decision'] == 'KEEP':
            warning_analysis = self._analyze_comment_warnings(comment)
            result['ai_analysis']['warning_analysis'] = warning_analysis
            
            if warning_analysis and warning_analysis.get('has_critical_warning', False):
                result['decision'] = 'REJECT'
                result['confidence'] = 0.8
                result['reasons'].append(f"Critical warning: {warning_analysis.get('warning_type', 'Unknown warning')}")
                result['recommendations'].append("Address warning before processing")
        
        # AI Analysis 4: Database Validation
        if result['decision'] == 'KEEP':
            db_validation = self._validate_against_database(propnum)
            result['database_validation'] = db_validation
            
            if db_validation and not db_validation.get('is_valid', True):
                result['decision'] = 'REJECT'
                result['confidence'] = 0.7
                result['reasons'].append(f"Database validation failed: {db_validation.get('reason', 'Unknown error')}")
                result['recommendations'].append("Fix database issues before processing")
        
        # AI Analysis 5: Business Logic Validation
        if result['decision'] == 'KEEP':
            business_logic = self._validate_business_logic(row, patterns)
            result['ai_analysis']['business_logic'] = business_logic
            
            if business_logic and not business_logic.get('is_valid', True):
                result['decision'] = 'REJECT'
                result['confidence'] = 0.8
                result['reasons'].append(f"Business logic violation: {business_logic.get('violation', 'Unknown violation')}")
                result['recommendations'].append("Review business rules compliance")
        
        return result
    
    def _assess_duplicate_risk(self, propnum: str, patterns: Dict) -> Dict[str, Any]:
        """Assess duplicate risk for a property number"""
        high_duplicates = patterns['propnum_analysis']['high_duplicate_propnums']
        moderate_duplicates = patterns['propnum_analysis']['moderate_duplicate_propnums']
        
        if propnum in high_duplicates:
            return {
                'risk_level': 'HIGH',
                'count': high_duplicates[propnum],
                'assessment': 'Too many duplicates - likely data error'
            }
        elif propnum in moderate_duplicates:
            return {
                'risk_level': 'MODERATE',
                'count': moderate_duplicates[propnum],
                'assessment': 'Moderate duplicates - review needed'
            }
        else:
            return {
                'risk_level': 'LOW',
                'count': 1,
                'assessment': 'Single occurrence - safe to process'
            }
    
    def _analyze_parent_child_conflict(self, row: pd.Series, patterns: Dict) -> Dict[str, Any]:
        """Analyze parent-child property conflicts"""
        comment = str(row.get('comments', ''))
        
        if 'adding propnum' not in comment.lower() or 'as new multi-assessment to property' not in comment.lower():
            return {'has_conflict': False, 'conflict_reason': 'Not a parent-child relationship'}
        
        try:
            # Extract parent property number
            parent_start = comment.find('to property') + len('to property')
            parent_end = comment.find('(')
            if parent_start < parent_end:
                parent_propnum = comment[parent_start:parent_end].strip()
                
                # Check if parent property is already Status='C' (new property)
                parent_db_result = self.db_helper.find_property_by_propnum(parent_propnum)
                
                if parent_db_result and parent_db_result.get('Status') == 'C':
                    return {
                        'has_conflict': True,
                        'conflict_reason': f"Parent property {parent_propnum} is already Status='C' (new property)",
                        'parent_status': 'C',
                        'ai_assessment': 'Parent already processed as new property'
                    }
                
                return {
                    'has_conflict': False,
                    'conflict_reason': 'No conflict detected',
                    'parent_status': parent_db_result.get('Status', 'Unknown') if parent_db_result else 'Not found'
                }
        
        except Exception as e:
            logger.warning(f"Error analyzing parent-child conflict: {e}")
            return {'has_conflict': False, 'conflict_reason': f'Analysis error: {e}'}
    
    def _analyze_comment_warnings(self, comment: str) -> Dict[str, Any]:
        """Analyze comment warnings"""
        analysis = {
            'has_warning': 'WARNING' in comment,
            'has_critical_warning': False,
            'warning_type': None,
            'warning_details': []
        }
        
        if analysis['has_warning']:
            if 'different road names' in comment:
                analysis['has_critical_warning'] = True
                analysis['warning_type'] = 'Road name mismatch'
                analysis['warning_details'].append('Properties have different road names')
            
            if 'properties have different' in comment:
                analysis['has_critical_warning'] = True
                analysis['warning_type'] = 'Property mismatch'
                analysis['warning_details'].append('Properties have different characteristics')
        
        return analysis
    
    def _validate_against_database(self, propnum: str) -> Dict[str, Any]:
        """Validate property against database"""
        try:
            db_result = self.db_helper.find_property_by_propnum(propnum)
            
            if db_result:
                return {
                    'is_valid': True,
                    'status': db_result.get('Status', 'Unknown'),
                    'found_in_database': True,
                    'reason': 'Property found in database'
                }
            else:
                return {
                    'is_valid': False,
                    'found_in_database': False,
                    'reason': 'Property not found in database'
                }
        
        except Exception as e:
            return {
                'is_valid': False,
                'found_in_database': False,
                'reason': f'Database validation error: {e}'
            }
    
    def _validate_business_logic(self, row: pd.Series, patterns: Dict) -> Dict[str, Any]:
        """Validate business logic rules"""
        validation = {
            'is_valid': True,
            'violation': None,
            'checks_performed': []
        }
        
        # Check 1: Edit code validation
        edit_code = str(row.get('edit_code', ''))
        if edit_code == 'A' and not str(row.get('comments', '')).strip():
            validation['is_valid'] = False
            validation['violation'] = 'Edit code A requires comments'
            validation['checks_performed'].append('Edit code A comment check')
        
        # Check 2: Required fields
        required_fields = ['propnum', 'edit_code']
        for field in required_fields:
            if pd.isna(row.get(field)) or str(row.get(field)).strip() == '':
                validation['is_valid'] = False
                validation['violation'] = f'Required field {field} is missing'
                validation['checks_performed'].append(f'Required field check: {field}')
                break
        
        return validation
    
    def generate_intelligent_report(self, csv_file: str) -> Dict[str, Any]:
        """Generate comprehensive AI-powered validation report"""
        logger.info("AI Intelligent Report: Generating comprehensive analysis...")
        
        df = pd.read_csv(csv_file)
        
        # Run intelligent validation
        validation_results = self.intelligent_row_validation(df)
        
        # Generate summary statistics
        summary = self._generate_summary_statistics(validation_results)
        
        # Generate detailed report
        report = {
            'ai_analysis_summary': {
                'total_rows': len(df),
                'rows_kept': summary['kept_count'],
                'rows_rejected': summary['rejected_count'],
                'ai_confidence': summary['average_confidence'],
                'pattern_analysis': self.ai_insights
            },
            'validation_results': validation_results,
            'summary_statistics': summary,
            'ai_recommendations': self._generate_final_recommendations(summary, self.ai_insights),
            'next_steps': self._generate_next_steps(summary)
        }
        
        return report
    
    def _generate_summary_statistics(self, validation_results: List[Dict]) -> Dict[str, Any]:
        """Generate summary statistics from validation results"""
        summary = {
            'total_rows': len(validation_results),
            'kept_count': 0,
            'rejected_count': 0,
            'average_confidence': 0.0,
            'rejection_reasons': defaultdict(int),
            'ai_insights': defaultdict(int)
        }
        
        total_confidence = 0
        
        for result in validation_results:
            if result['decision'] == 'KEEP':
                summary['kept_count'] += 1
            else:
                summary['rejected_count'] += 1
                for reason in result['reasons']:
                    summary['rejection_reasons'][reason] += 1
            
            total_confidence += result['confidence']
        
        summary['average_confidence'] = total_confidence / len(validation_results) if validation_results else 0
        
        return summary
    
    def _generate_final_recommendations(self, summary: Dict, insights: Dict) -> List[str]:
        """Generate final AI recommendations"""
        recommendations = []
        
        # Duplicate recommendations
        if summary['rejection_reasons'].get('High duplicate risk', 0) > 0:
            recommendations.append("AI Recommendation: Implement duplicate detection and removal")
        
        # Parent-child conflict recommendations
        if summary['rejection_reasons'].get('Parent-child conflict', 0) > 0:
            recommendations.append("AI Recommendation: Review parent-child property relationships")
        
        # Database validation recommendations
        if summary['rejection_reasons'].get('Database validation failed', 0) > 0:
            recommendations.append("AI Recommendation: Fix database connectivity and validation")
        
        # Warning recommendations
        if insights.get('comment_analysis', {}).get('warning_count', 0) > 0:
            recommendations.append("AI Recommendation: Address warning flags in comments")
        
        return recommendations
    
    def _generate_next_steps(self, summary: Dict) -> List[str]:
        """Generate next steps based on analysis"""
        next_steps = []
        
        if summary['rejected_count'] > 0:
            next_steps.append("Review and fix rejected rows")
            next_steps.append("Implement recommended fixes")
        
        next_steps.append("Process approved rows")
        next_steps.append("Monitor validation results")
        
        return next_steps

def main():
    """Main execution function"""
    csv_file = os.getenv("SAMPLE_M1_CSV", "tests/fixtures/sample_m1.csv")
    
    if not os.path.exists(csv_file):
        logger.error(f"CSV file not found: {csv_file}")
        return
    
    logger.info("AI Intelligent POZI M1 Validation: Starting comprehensive analysis...")
    
    validator = AIPoziIntelligentValidator()
    
    try:
        # Generate intelligent validation report
        report = validator.generate_intelligent_report(csv_file)
        
        # Save detailed report
        with open('ai_intelligent_validation_report.json', 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        # Save CSV results
        results_df = pd.DataFrame(report['validation_results'])
        results_df.to_csv('ai_intelligent_validation_results.csv', index=False)
        
        logger.info("AI Intelligent Validation Complete!")
        logger.info(f"Report saved to: ai_intelligent_validation_report.json")
        logger.info(f"Results saved to: ai_intelligent_validation_results.csv")
        
        # Print summary
        print("\n" + "="*70)
        print("AI INTELLIGENT POZI M1 VALIDATION SUMMARY")
        print("="*70)
        
        summary = report['summary_statistics']
        print(f"Total Rows Analyzed: {summary['total_rows']}")
        print(f"Rows to KEEP: {summary['kept_count']} ({summary['kept_count']/summary['total_rows']*100:.1f}%)")
        print(f"Rows to REJECT: {summary['rejected_count']} ({summary['rejected_count']/summary['total_rows']*100:.1f}%)")
        print(f"AI Average Confidence: {summary['average_confidence']:.1%}")
        
        print(f"\nTop Rejection Reasons:")
        for reason, count in sorted(summary['rejection_reasons'].items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  - {reason}: {count} rows")
        
        print(f"\nAI Recommendations:")
        for rec in report['ai_recommendations']:
            print(f"  - {rec}")
        
        print(f"\nNext Steps:")
        for step in report['next_steps']:
            print(f"  - {step}")
        
        print("\n" + "="*70)
        
    except Exception as e:
        logger.error(f"AI Intelligent Validation failed: {e}")
        raise

if __name__ == "__main__":
    main()
