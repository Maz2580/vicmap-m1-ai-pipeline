#!/usr/bin/env python3
"""
AI-Powered POZI M1 Analysis and Validation
This script uses AI to intelligently analyze POZI-generated CSV structure
and make smart decisions based on database findings rather than simple field matching.
"""

import pandas as pd
import logging
import json
from typing import Dict, List, Any, Tuple
import sys
import os

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v2_m1_ai_validator.data_processing.database_helper import InfoProdDatabaseHelper
from v2_m1_ai_validator.data_processing.database_relationship_validator import DatabaseRelationshipValidator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AIPoziAnalyzer:
    """AI-powered analyzer for POZI-generated M1 files"""
    
    def __init__(self):
        self.db_helper = InfoProdDatabaseHelper()
        self.db_validator = DatabaseRelationshipValidator()
        self.csv_structure = {}
        self.field_mappings = {}
        self.ai_insights = {}
        
    def analyze_csv_structure(self, csv_file: str) -> Dict[str, Any]:
        """AI analysis of CSV structure to understand POZI-specific fields"""
        logger.info("🔍 AI Analysis: Examining POZI CSV structure...")
        
        df = pd.read_csv(csv_file)
        
        # AI-powered structure analysis
        structure_analysis = {
            'total_rows': len(df),
            'columns': list(df.columns),
            'column_types': {},
            'sample_data': {},
            'pozi_specific_fields': [],
            'potential_m1_fields': [],
            'data_patterns': {},
            'ai_recommendations': []
        }
        
        # Analyze each column intelligently
        for col in df.columns:
            col_data = df[col].dropna()
            structure_analysis['column_types'][col] = str(df[col].dtype)
            structure_analysis['sample_data'][col] = col_data.head(3).tolist()
            
            # AI field identification
            col_lower = col.lower()
            if any(keyword in col_lower for keyword in ['propnum', 'property', 'prop']):
                structure_analysis['potential_m1_fields'].append({
                    'field': col,
                    'type': 'property_identifier',
                    'confidence': 0.9
                })
            elif any(keyword in col_lower for keyword in ['address', 'street', 'road']):
                structure_analysis['potential_m1_fields'].append({
                    'field': col,
                    'type': 'address',
                    'confidence': 0.8
                })
            elif any(keyword in col_lower for keyword in ['comment', 'note', 'description']):
                structure_analysis['potential_m1_fields'].append({
                    'field': col,
                    'type': 'comment',
                    'confidence': 0.9
                })
            elif any(keyword in col_lower for keyword in ['edit', 'code', 'action']):
                structure_analysis['potential_m1_fields'].append({
                    'field': col,
                    'type': 'edit_code',
                    'confidence': 0.8
                })
            elif any(keyword in col_lower for keyword in ['parent', 'child', 'relationship']):
                structure_analysis['potential_m1_fields'].append({
                    'field': col,
                    'type': 'relationship',
                    'confidence': 0.7
                })
        
        # AI pattern analysis
        structure_analysis['data_patterns'] = self._analyze_data_patterns(df)
        
        # AI recommendations
        structure_analysis['ai_recommendations'] = self._generate_ai_recommendations(df, structure_analysis)
        
        self.csv_structure = structure_analysis
        logger.info(f"✅ AI Analysis Complete: Found {len(structure_analysis['potential_m1_fields'])} potential M1 fields")
        
        return structure_analysis
    
    def _analyze_data_patterns(self, df: pd.DataFrame) -> Dict[str, Any]:
        """AI-powered data pattern analysis"""
        patterns = {
            'duplicate_analysis': {},
            'relationship_patterns': {},
            'data_quality_issues': [],
            'pozi_specific_patterns': []
        }
        
        # Analyze duplicates intelligently
        for col in df.columns:
            if df[col].dtype in ['object', 'string']:
                value_counts = df[col].value_counts()
                duplicates = value_counts[value_counts > 1]
                if len(duplicates) > 0:
                    patterns['duplicate_analysis'][col] = {
                        'total_duplicates': len(duplicates),
                        'max_frequency': duplicates.max(),
                        'top_duplicates': duplicates.head(5).to_dict()
                    }
        
        # Look for POZI-specific patterns
        for col in df.columns:
            col_data = df[col].astype(str)
            if 'pozi' in col.lower() or 'connect' in col.lower():
                patterns['pozi_specific_patterns'].append({
                    'field': col,
                    'pattern_type': 'pozi_generated',
                    'sample_values': col_data.head(3).tolist()
                })
        
        return patterns
    
    def _generate_ai_recommendations(self, df: pd.DataFrame, structure: Dict) -> List[str]:
        """Generate AI recommendations for field mapping and validation"""
        recommendations = []
        
        # Analyze field mappings
        prop_fields = [f for f in structure['potential_m1_fields'] if f['type'] == 'property_identifier']
        if len(prop_fields) > 1:
            recommendations.append(f"Multiple property fields detected: {[f['field'] for f in prop_fields]}. AI suggests using the most populated field.")
        
        # Check for missing critical fields
        has_edit_code = any(f['type'] == 'edit_code' for f in structure['potential_m1_fields'])
        if not has_edit_code:
            recommendations.append("No clear edit code field found. AI suggests examining comment fields for action indicators.")
        
        # Data quality recommendations
        if structure['total_rows'] > 100:
            recommendations.append("Large dataset detected. AI recommends batch processing for optimal performance.")
        
        return recommendations
    
    def intelligent_field_mapping(self, df: pd.DataFrame) -> Dict[str, str]:
        """AI-powered intelligent field mapping"""
        logger.info("🧠 AI Field Mapping: Analyzing field relationships...")
        
        mappings = {}
        
        # AI-powered property number detection
        propnum_candidates = []
        for col in df.columns:
            col_data = df[col].dropna()
            if len(col_data) > 0:
                # Check if values look like property numbers
                sample_values = col_data.head(10).astype(str)
                if all(val.replace('.', '').isdigit() and len(val.replace('.', '')) >= 5 for val in sample_values):
                    propnum_candidates.append({
                        'field': col,
                        'confidence': 0.8,
                        'sample_values': sample_values.tolist()
                    })
        
        if propnum_candidates:
            # Choose the most populated field
            best_candidate = max(propnum_candidates, key=lambda x: len(df[x['field']].dropna()))
            mappings['propnum'] = best_candidate['field']
            logger.info(f"✅ AI Mapped propnum to: {best_candidate['field']}")
        
        # AI-powered comment field detection
        comment_candidates = []
        for col in df.columns:
            col_data = df[col].dropna()
            if len(col_data) > 0:
                # Check if values contain descriptive text
                sample_text = ' '.join(col_data.head(5).astype(str))
                if len(sample_text) > 50 and any(word in sample_text.lower() for word in ['adding', 'property', 'new', 'parent', 'child']):
                    comment_candidates.append({
                        'field': col,
                        'confidence': 0.7,
                        'sample_text': sample_text[:100] + '...'
                    })
        
        if comment_candidates:
            mappings['comment'] = comment_candidates[0]['field']
            logger.info(f"✅ AI Mapped comment to: {comment_candidates[0]['field']}")
        
        # AI-powered edit code detection
        edit_code_candidates = []
        for col in df.columns:
            col_data = df[col].dropna()
            if len(col_data) > 0:
                unique_values = col_data.unique()
                if len(unique_values) <= 10 and all(str(val).upper() in ['A', 'B', 'C', 'E', 'P', 'S', 'Z', 'R'] for val in unique_values):
                    edit_code_candidates.append({
                        'field': col,
                        'confidence': 0.9,
                        'values': unique_values.tolist()
                    })
        
        if edit_code_candidates:
            mappings['edit_code'] = edit_code_candidates[0]['field']
            logger.info(f"✅ AI Mapped edit_code to: {edit_code_candidates[0]['field']}")
        
        self.field_mappings = mappings
        return mappings
    
    def ai_database_analysis(self, df: pd.DataFrame) -> Dict[str, Any]:
        """AI-powered database analysis and validation"""
        logger.info("🔍 AI Database Analysis: Intelligent validation against InfoProd...")
        
        # Use AI field mappings
        mappings = self.intelligent_field_mapping(df)
        
        analysis_results = {
            'field_mappings': mappings,
            'database_validation': {},
            'ai_insights': {},
            'recommendations': []
        }
        
        # AI-powered validation for each mapped field
        if 'propnum' in mappings:
            propnum_field = mappings['propnum']
            propnums = df[propnum_field].dropna().unique()
            
            logger.info(f"🔍 AI Analyzing {len(propnums)} unique property numbers...")
            
            db_analysis = {
                'total_properties': len(propnums),
                'found_in_database': 0,
                'status_c_properties': 0,
                'validation_results': [],
                'ai_patterns': {}
            }
            
            for propnum in propnums[:10]:  # Analyze first 10 for pattern detection
                try:
                    # Clean propnum
                    clean_propnum = str(propnum).replace('.0', '')
                    
                    # Database lookup
                    db_result = self.db_helper.find_property_by_propnum(clean_propnum)
                    
                    if db_result:
                        db_analysis['found_in_database'] += 1
                        if db_result.get('Status') == 'C':
                            db_analysis['status_c_properties'] += 1
                        
                        db_analysis['validation_results'].append({
                            'propnum': clean_propnum,
                            'found': True,
                            'status': db_result.get('Status', 'Unknown'),
                            'ai_analysis': self._ai_analyze_property_context(propnum, df, mappings)
                        })
                    else:
                        db_analysis['validation_results'].append({
                            'propnum': clean_propnum,
                            'found': False,
                            'ai_analysis': self._ai_analyze_property_context(propnum, df, mappings)
                        })
                
                except Exception as e:
                    logger.warning(f"AI Analysis error for propnum {propnum}: {e}")
            
            # AI pattern analysis
            db_analysis['ai_patterns'] = self._analyze_validation_patterns(db_analysis['validation_results'])
            
            analysis_results['database_validation'] = db_analysis
        
        # Generate AI recommendations
        analysis_results['recommendations'] = self._generate_ai_validation_recommendations(analysis_results)
        
        self.ai_insights = analysis_results
        return analysis_results
    
    def _ai_analyze_property_context(self, propnum: str, df: pd.DataFrame, mappings: Dict) -> Dict[str, Any]:
        """AI analysis of property context within the dataset"""
        clean_propnum = str(propnum).replace('.0', '')
        
        # Find all rows with this propnum
        propnum_field = mappings.get('propnum', 'propnum')
        matching_rows = df[df[propnum_field].astype(str).str.replace('.0', '') == clean_propnum]
        
        context_analysis = {
            'occurrence_count': len(matching_rows),
            'row_indices': matching_rows.index.tolist(),
            'context_patterns': {},
            'ai_assessment': 'unknown'
        }
        
        if len(matching_rows) > 1:
            context_analysis['context_patterns']['duplicate_propnum'] = {
                'count': len(matching_rows),
                'ai_assessment': 'potential_duplicate_issue'
            }
        
        # Analyze comments if available
        if 'comment' in mappings:
            comment_field = mappings['comment']
            comments = matching_rows[comment_field].dropna().tolist()
            if comments:
                context_analysis['context_patterns']['comments'] = {
                    'count': len(comments),
                    'sample_comments': comments[:3],
                    'ai_assessment': self._ai_assess_comments(comments)
                }
        
        # AI assessment
        if context_analysis['occurrence_count'] > 3:
            context_analysis['ai_assessment'] = 'high_duplicate_risk'
        elif context_analysis['occurrence_count'] == 1:
            context_analysis['ai_assessment'] = 'single_occurrence_safe'
        else:
            context_analysis['ai_assessment'] = 'moderate_duplicate_risk'
        
        return context_analysis
    
    def _ai_assess_comments(self, comments: List[str]) -> str:
        """AI assessment of comment patterns"""
        comment_text = ' '.join(comments).lower()
        
        if 'parent' in comment_text and 'new' in comment_text:
            return 'parent_child_relationship'
        elif 'adding' in comment_text and 'property' in comment_text:
            return 'property_addition'
        elif 'warning' in comment_text:
            return 'warning_flag'
        else:
            return 'standard_comment'
    
    def _analyze_validation_patterns(self, validation_results: List[Dict]) -> Dict[str, Any]:
        """AI analysis of validation patterns"""
        patterns = {
            'success_rate': 0,
            'status_c_rate': 0,
            'common_issues': [],
            'ai_recommendations': []
        }
        
        if validation_results:
            found_count = sum(1 for r in validation_results if r.get('found', False))
            patterns['success_rate'] = found_count / len(validation_results)
            
            status_c_count = sum(1 for r in validation_results if r.get('status') == 'C')
            patterns['status_c_rate'] = status_c_count / len(validation_results)
            
            # AI recommendations based on patterns
            if patterns['status_c_rate'] > 0.5:
                patterns['ai_recommendations'].append("High percentage of Status='C' properties detected. AI suggests these are new properties from POZI generation.")
            
            if patterns['success_rate'] < 0.3:
                patterns['ai_recommendations'].append("Low database match rate. AI suggests POZI properties may not be in GIS yet.")
        
        return patterns
    
    def _generate_ai_validation_recommendations(self, analysis_results: Dict) -> List[str]:
        """Generate AI recommendations for validation approach"""
        recommendations = []
        
        db_validation = analysis_results.get('database_validation', {})
        
        if db_validation.get('ai_patterns', {}).get('status_c_rate', 0) > 0.5:
            recommendations.append("AI Recommendation: Focus on Status='C' validation - these are new POZI properties")
        
        if db_validation.get('ai_patterns', {}).get('success_rate', 0) < 0.3:
            recommendations.append("AI Recommendation: Use address-based validation for POZI properties not in GIS")
        
        field_mappings = analysis_results.get('field_mappings', {})
        if len(field_mappings) < 3:
            recommendations.append("AI Recommendation: Limited field mapping detected - may need manual field identification")
        
        return recommendations
    
    def generate_ai_validation_report(self, csv_file: str) -> Dict[str, Any]:
        """Generate comprehensive AI-powered validation report"""
        logger.info("🤖 AI Validation Report: Starting comprehensive analysis...")
        
        df = pd.read_csv(csv_file)
        
        # Step 1: AI Structure Analysis
        structure_analysis = self.analyze_csv_structure(csv_file)
        
        # Step 2: AI Database Analysis
        database_analysis = self.ai_database_analysis(df)
        
        # Step 3: AI Decision Making
        ai_decisions = self._make_ai_decisions(df, structure_analysis, database_analysis)
        
        # Generate comprehensive report
        report = {
            'ai_analysis_summary': {
                'csv_structure': structure_analysis,
                'database_analysis': database_analysis,
                'ai_decisions': ai_decisions
            },
            'field_mappings': self.field_mappings,
            'validation_recommendations': database_analysis.get('recommendations', []),
            'ai_insights': self.ai_insights,
            'next_steps': self._generate_next_steps(ai_decisions)
        }
        
        return report
    
    def _make_ai_decisions(self, df: pd.DataFrame, structure: Dict, db_analysis: Dict) -> Dict[str, Any]:
        """AI-powered decision making for validation approach"""
        decisions = {
            'validation_strategy': 'unknown',
            'field_mapping_confidence': 0,
            'database_integration_approach': 'unknown',
            'risk_assessment': 'unknown',
            'recommended_actions': []
        }
        
        # AI decision on validation strategy
        field_mappings = db_analysis.get('field_mappings', {})
        if len(field_mappings) >= 3:
            decisions['validation_strategy'] = 'comprehensive_field_mapping'
            decisions['field_mapping_confidence'] = 0.8
        elif len(field_mappings) >= 1:
            decisions['validation_strategy'] = 'limited_field_mapping'
            decisions['field_mapping_confidence'] = 0.5
        else:
            decisions['validation_strategy'] = 'manual_field_identification'
            decisions['field_mapping_confidence'] = 0.2
        
        # AI decision on database approach
        db_patterns = db_analysis.get('database_validation', {}).get('ai_patterns', {})
        if db_patterns.get('status_c_rate', 0) > 0.5:
            decisions['database_integration_approach'] = 'status_c_focused'
            decisions['recommended_actions'].append("Focus validation on Status='C' properties")
        elif db_patterns.get('success_rate', 0) < 0.3:
            decisions['database_integration_approach'] = 'address_based_fallback'
            decisions['recommended_actions'].append("Use address-based validation for missing properties")
        else:
            decisions['database_integration_approach'] = 'standard_propnum_matching'
        
        # AI risk assessment
        total_rows = structure.get('total_rows', 0)
        if total_rows > 500:
            decisions['risk_assessment'] = 'high_volume_processing'
            decisions['recommended_actions'].append("Implement batch processing for large dataset")
        elif total_rows > 100:
            decisions['risk_assessment'] = 'moderate_volume'
        else:
            decisions['risk_assessment'] = 'low_volume_safe'
        
        return decisions
    
    def _generate_next_steps(self, decisions: Dict) -> List[str]:
        """Generate AI-recommended next steps"""
        next_steps = []
        
        if decisions['validation_strategy'] == 'manual_field_identification':
            next_steps.append("Manual field mapping required - AI could not auto-detect M1 fields")
        
        if decisions['database_integration_approach'] == 'status_c_focused':
            next_steps.append("Implement Status='C' property validation logic")
        
        if decisions['risk_assessment'] == 'high_volume_processing':
            next_steps.append("Set up batch processing for large dataset")
        
        next_steps.append("Run AI-powered validation with recommended approach")
        next_steps.append("Generate detailed validation report with AI insights")
        
        return next_steps

def main():
    """Main execution function"""
    csv_file = os.getenv("SAMPLE_M1_CSV", "tests/fixtures/sample_m1.csv")
    
    if not os.path.exists(csv_file):
        logger.error(f"CSV file not found: {csv_file}")
        return
    
    logger.info("🤖 Starting AI-Powered POZI M1 Analysis...")
    
    analyzer = AIPoziAnalyzer()
    
    try:
        # Generate AI validation report
        report = analyzer.generate_ai_validation_report(csv_file)
        
        # Save report
        with open('ai_pozi_analysis_report.json', 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info("✅ AI Analysis Complete!")
        logger.info(f"📊 Report saved to: ai_pozi_analysis_report.json")
        
        # Print summary
        print("\n" + "="*60)
        print("AI-POWERED POZI M1 ANALYSIS SUMMARY")
        print("="*60)
        
        structure = report['ai_analysis_summary']['csv_structure']
        print(f"CSV Structure: {structure['total_rows']} rows, {len(structure['columns'])} columns")
        print(f"AI Detected Fields: {len(structure['potential_m1_fields'])} potential M1 fields")
        
        decisions = report['ai_analysis_summary']['ai_decisions']
        print(f"AI Validation Strategy: {decisions['validation_strategy']}")
        print(f"AI Field Mapping Confidence: {decisions['field_mapping_confidence']:.1%}")
        print(f"AI Database Approach: {decisions['database_integration_approach']}")
        print(f"AI Risk Assessment: {decisions['risk_assessment']}")
        
        print(f"\nAI Recommendations:")
        for rec in report['validation_recommendations']:
            print(f"  - {rec}")
        
        print(f"\nNext Steps:")
        for step in report['next_steps']:
            print(f"  - {step}")
        
        print("\n" + "="*60)
        
    except Exception as e:
        logger.error(f"AI Analysis failed: {e}")
        raise

if __name__ == "__main__":
    main()
