#!/usr/bin/env python3
"""
AI-Powered POZI M1 Intelligent Validator
Uses free AI providers (Groq primary, OpenRouter fallback) to learn from training data
and make intelligent decisions
"""

import pandas as pd
import logging
import json
import os
from typing import Dict, List, Any, Tuple
import sys
from dotenv import load_dotenv
from openai import OpenAI

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v2_m1_ai_validator.data_processing.database_helper import InfoProdDatabaseHelper

# Load environment variables
load_dotenv()

# Reuse the same AI client factory from smart_openai_validator
from v2_m1_ai_validator.smart_openai_validator import _create_ai_client, _create_fallback_client

client, AI_MODEL, AI_PROVIDER = _create_ai_client()
fallback_client, FALLBACK_MODEL, FALLBACK_PROVIDER = _create_fallback_client()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class OpenAIPoziValidator:
    """OpenAI-powered intelligent validator for POZI M1 files"""
    
    def __init__(self):
        self.db_helper = InfoProdDatabaseHelper()
        self.training_data = None
        self.ai_patterns = {}
        self.validation_rules = {}
        
    def load_training_data(self, csv_file: str) -> pd.DataFrame:
        """Load and analyze training data"""
        logger.info("Loading training data for AI learning...")
        
        df = pd.read_csv(csv_file)
        self.training_data = df
        
        logger.info(f"Loaded {len(df)} rows of training data")
        return df
    
    def analyze_training_patterns_with_openai(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Use OpenAI to analyze training patterns and learn validation rules"""
        logger.info("Using OpenAI to analyze training patterns...")
        
        # Prepare training data for OpenAI analysis
        training_samples = self._prepare_training_samples(df)
        
        # Create OpenAI prompt for pattern analysis
        prompt = self._create_pattern_analysis_prompt(training_samples)
        
        try:
            response = client.chat.completions.create(
                model=AI_MODEL,
                messages=[
                    {"role": "system", "content": "You are an expert M1 validation specialist with deep knowledge of property data validation and POZI systems."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.1
            )

            ai_analysis = response.choices[0].message.content
            logger.info(f"AI analysis completed successfully via {AI_PROVIDER}")

            # Parse AI response
            patterns = self._parse_ai_analysis(ai_analysis)

            return patterns

        except Exception as e:
            logger.warning(f"{AI_PROVIDER} failed: {e}")
            # Try fallback
            if fallback_client and FALLBACK_PROVIDER != AI_PROVIDER:
                try:
                    response = fallback_client.chat.completions.create(
                        model=FALLBACK_MODEL,
                        messages=[
                            {"role": "system", "content": "You are an expert M1 validation specialist with deep knowledge of property data validation and POZI systems."},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=2000,
                        temperature=0.1
                    )
                    ai_analysis = response.choices[0].message.content
                    logger.info(f"AI fallback successful via {FALLBACK_PROVIDER}")
                    return self._parse_ai_analysis(ai_analysis)
                except Exception as e2:
                    logger.error(f"Fallback {FALLBACK_PROVIDER} also failed: {e2}")
            return self._fallback_pattern_analysis(df)
    
    def _prepare_training_samples(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Prepare training samples for OpenAI analysis"""
        
        # Define correct and incorrect row ranges based on user feedback
        incorrect_ranges = [
            (2, 74),   # row 2 to row 74
            (76, 78),  # row 76 to 78
            (529, 556) # row 529 to 556
        ]
        
        correct_ranges = [
            (82, 313),  # row 82 to 313
            (316, 318), # row 316 to 318
            (320, 364), # row 320 to 364
            (368, 445), # row 368 to 445
            (448, 511)  # row 448 to 511
        ]
        
        # Extract samples from each category
        incorrect_samples = []
        correct_samples = []
        
        for start, end in incorrect_ranges:
            for i in range(start, min(end + 1, len(df))):
                if i < len(df):
                    sample = self._extract_sample_data(df.iloc[i], i)
                    incorrect_samples.append(sample)
        
        for start, end in correct_ranges:
            for i in range(start, min(end + 1, len(df))):
                if i < len(df):
                    sample = self._extract_sample_data(df.iloc[i], i)
                    correct_samples.append(sample)
        
        return {
            'incorrect_samples': incorrect_samples[:20],  # Limit to 20 samples for API
            'correct_samples': correct_samples[:20],      # Limit to 20 samples for API
            'total_incorrect': len(incorrect_samples),
            'total_correct': len(correct_samples)
        }
    
    def _extract_sample_data(self, row: pd.Series, row_index: int) -> Dict[str, Any]:
        """Extract relevant data from a row for analysis"""
        return {
            'row_index': row_index,
            'propnum': str(row.get('propnum', '')).replace('.0', ''),
            'edit_code': str(row.get('edit_code', '')),
            'comments': str(row.get('comments', ''))[:200] + '...' if len(str(row.get('comments', ''))) > 200 else str(row.get('comments', '')),
            'spi': str(row.get('spi', '')),
            'road_name': str(row.get('road_name', '')),
            'locality_name': str(row.get('locality_name', '')),
            'house_number_1': str(row.get('house_number_1', '')),
            'property_pfi': str(row.get('property_pfi', '')),
            'parcel_pfi': str(row.get('parcel_pfi', ''))
        }
    
    def _create_pattern_analysis_prompt(self, training_samples: Dict[str, Any]) -> str:
        """Create OpenAI prompt for pattern analysis"""
        
        prompt = f"""
I need you to analyze M1 property validation data and identify patterns that distinguish correct from incorrect records.

## Training Data Summary:
- Total Incorrect Records: {training_samples['total_incorrect']}
- Total Correct Records: {training_samples['total_correct']}

## Sample Incorrect Records (should be rejected):
{json.dumps(training_samples['incorrect_samples'][:5], indent=2)}

## Sample Correct Records (should be accepted):
{json.dumps(training_samples['correct_samples'][:5], indent=2)}

## Task:
Analyze these samples and identify the key patterns that distinguish incorrect records from correct ones. Focus on:

1. **Comment Analysis**: What warning patterns indicate problems?
2. **Property Relationships**: What parent-child property conflicts exist?
3. **Data Quality Issues**: What data inconsistencies cause rejections?
4. **Business Logic Violations**: What M1 rules are being violated?

## Expected Output Format:
Please provide a JSON response with:
{{
    "patterns": {{
        "comment_warnings": ["list of warning patterns"],
        "property_conflicts": ["list of conflict patterns"],
        "data_quality_issues": ["list of data issues"],
        "business_logic_violations": ["list of rule violations"]
    }},
    "validation_rules": {{
        "reject_if": ["list of rejection criteria"],
        "accept_if": ["list of acceptance criteria"]
    }},
    "confidence": 0.95,
    "reasoning": "explanation of the analysis"
}}
"""
        return prompt
    
    def _parse_ai_analysis(self, ai_response: str) -> Dict[str, Any]:
        """Parse OpenAI response into structured patterns"""
        try:
            # Extract JSON from response
            start_idx = ai_response.find('{')
            end_idx = ai_response.rfind('}') + 1
            
            if start_idx != -1 and end_idx != -1:
                json_str = ai_response[start_idx:end_idx]
                patterns = json.loads(json_str)
                return patterns
            else:
                logger.warning("Could not extract JSON from OpenAI response")
                return self._fallback_pattern_analysis(self.training_data)
                
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parsing error: {e}")
            return self._fallback_pattern_analysis(self.training_data)
    
    def _fallback_pattern_analysis(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Fallback pattern analysis if OpenAI fails"""
        logger.info("Using fallback pattern analysis...")
        
        return {
            "patterns": {
                "comment_warnings": ["WARNING", "different road names", "property mismatch"],
                "property_conflicts": ["parent property already processed", "Status='C' conflicts"],
                "data_quality_issues": ["missing propnum", "invalid data"],
                "business_logic_violations": ["duplicate entries", "inconsistent data"]
            },
            "validation_rules": {
                "reject_if": ["WARNING in comments", "duplicate propnum", "parent conflict"],
                "accept_if": ["clean comments", "valid propnum", "no conflicts"]
            },
            "confidence": 0.7,
            "reasoning": "Fallback analysis based on common patterns"
        }
    
    def validate_with_openai(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Use OpenAI to validate each row intelligently"""
        logger.info("Using OpenAI for intelligent row validation...")
        
        validation_results = []
        
        # Process in batches to avoid API limits
        batch_size = 50
        total_batches = (len(df) + batch_size - 1) // batch_size
        
        for batch_idx in range(total_batches):
            start_idx = batch_idx * batch_size
            end_idx = min((batch_idx + 1) * batch_size, len(df))
            
            logger.info(f"Processing batch {batch_idx + 1}/{total_batches} (rows {start_idx}-{end_idx})")
            
            batch_df = df.iloc[start_idx:end_idx]
            batch_results = self._validate_batch_with_openai(batch_df, start_idx)
            validation_results.extend(batch_results)
        
        return validation_results
    
    def _validate_batch_with_openai(self, batch_df: pd.DataFrame, start_idx: int) -> List[Dict[str, Any]]:
        """Validate a batch of rows using OpenAI"""
        
        # Prepare batch data for OpenAI
        batch_data = []
        for idx, row in batch_df.iterrows():
            sample = self._extract_sample_data(row, idx)
            batch_data.append(sample)
        
        # Create validation prompt
        prompt = self._create_validation_prompt(batch_data)
        
        try:
            response = client.chat.completions.create(
                model=AI_MODEL,
                messages=[
                    {"role": "system", "content": "You are an expert M1 validation specialist. Analyze each record and determine if it should be KEPT or REJECTED based on the learned patterns."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=3000,
                temperature=0.1
            )

            ai_response = response.choices[0].message.content
            results = self._parse_validation_response(ai_response, batch_data)

            return results

        except Exception as e:
            logger.warning(f"{AI_PROVIDER} validation error: {e}")
            # Try fallback
            if fallback_client and FALLBACK_PROVIDER != AI_PROVIDER:
                try:
                    response = fallback_client.chat.completions.create(
                        model=FALLBACK_MODEL,
                        messages=[
                            {"role": "system", "content": "You are an expert M1 validation specialist. Analyze each record and determine if it should be KEPT or REJECTED based on the learned patterns."},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=3000,
                        temperature=0.1
                    )
                    ai_response = response.choices[0].message.content
                    return self._parse_validation_response(ai_response, batch_data)
                except Exception as e2:
                    logger.error(f"Fallback {FALLBACK_PROVIDER} also failed: {e2}")
            return self._fallback_batch_validation(batch_df, start_idx)
    
    def _create_validation_prompt(self, batch_data: List[Dict[str, Any]]) -> str:
        """Create OpenAI prompt for batch validation"""
        
        prompt = f"""
Based on the learned patterns, validate each of these M1 records. For each record, determine if it should be KEPT or REJECTED.

## Learned Patterns:
- Reject records with WARNING flags in comments
- Reject records with parent-child property conflicts
- Reject records with duplicate propnums
- Accept records with clean data and no conflicts

## Records to Validate:
{json.dumps(batch_data, indent=2)}

## Expected Output Format:
Provide a JSON array with validation results:
[
    {{
        "row_index": 0,
        "propnum": "172249",
        "decision": "KEEP",
        "confidence": 0.95,
        "reason": "Clean record with no conflicts",
        "ai_analysis": "No warnings detected, valid property relationship"
    }},
    ...
]

Analyze each record carefully and provide detailed reasoning for each decision.
"""
        return prompt
    
    def _parse_validation_response(self, ai_response: str, batch_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Parse OpenAI validation response"""
        try:
            # Extract JSON array from response
            start_idx = ai_response.find('[')
            end_idx = ai_response.rfind(']') + 1
            
            if start_idx != -1 and end_idx != -1:
                json_str = ai_response[start_idx:end_idx]
                results = json.loads(json_str)
                return results
            else:
                logger.warning("Could not extract JSON array from OpenAI response")
                return self._fallback_batch_validation(pd.DataFrame(batch_data), 0)
                
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parsing error: {e}")
            return self._fallback_batch_validation(pd.DataFrame(batch_data), 0)
    
    def _fallback_batch_validation(self, batch_df: pd.DataFrame, start_idx: int) -> List[Dict[str, Any]]:
        """Fallback validation if OpenAI fails"""
        results = []
        
        for idx, row in batch_df.iterrows():
            result = {
                'row_index': idx,
                'propnum': str(row.get('propnum', '')).replace('.0', ''),
                'decision': 'KEEP',  # Default to keep
                'confidence': 0.5,
                'reason': 'Fallback validation - manual review needed',
                'ai_analysis': 'OpenAI validation failed, using fallback'
            }
            
            # Simple fallback logic
            comment = str(row.get('comments', ''))
            if 'WARNING' in comment:
                result['decision'] = 'REJECT'
                result['reason'] = 'WARNING detected in comments'
                result['confidence'] = 0.8
            
            results.append(result)
        
        return results
    
    def generate_openai_report(self, csv_file: str) -> Dict[str, Any]:
        """Generate comprehensive OpenAI-powered validation report"""
        logger.info("Generating OpenAI-powered validation report...")
        
        # Load training data
        df = self.load_training_data(csv_file)
        
        # Analyze patterns with OpenAI
        patterns = self.analyze_training_patterns_with_openai(df)
        self.ai_patterns = patterns
        
        # Validate all rows with OpenAI
        validation_results = self.validate_with_openai(df)
        
        # Generate summary statistics
        summary = self._generate_summary_statistics(validation_results)
        
        # Create comprehensive report
        report = {
            'openai_analysis': {
                'patterns_learned': patterns,
                'training_data_size': len(df),
                'ai_confidence': patterns.get('confidence', 0.8)
            },
            'validation_results': validation_results,
            'summary_statistics': summary,
            'ai_recommendations': self._generate_ai_recommendations(summary, patterns),
            'next_steps': self._generate_next_steps(summary)
        }
        
        return report
    
    def _generate_summary_statistics(self, validation_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate summary statistics from validation results"""
        summary = {
            'total_rows': len(validation_results),
            'kept_count': 0,
            'rejected_count': 0,
            'average_confidence': 0.0,
            'rejection_reasons': {},
            'ai_insights': {}
        }
        
        total_confidence = 0
        
        for result in validation_results:
            if result.get('decision') == 'KEEP':
                summary['kept_count'] += 1
            else:
                summary['rejected_count'] += 1
                reason = result.get('reason', 'Unknown')
                summary['rejection_reasons'][reason] = summary['rejection_reasons'].get(reason, 0) + 1
            
            total_confidence += result.get('confidence', 0.5)
        
        summary['average_confidence'] = total_confidence / len(validation_results) if validation_results else 0
        
        return summary
    
    def _generate_ai_recommendations(self, summary: Dict, patterns: Dict) -> List[str]:
        """Generate AI recommendations based on analysis"""
        recommendations = []
        
        # Pattern-based recommendations
        if patterns.get('patterns', {}).get('comment_warnings'):
            recommendations.append("AI Recommendation: Implement automated warning detection in comments")
        
        if patterns.get('patterns', {}).get('property_conflicts'):
            recommendations.append("AI Recommendation: Add parent-child property conflict detection")
        
        # Summary-based recommendations
        if summary['rejected_count'] > summary['kept_count']:
            recommendations.append("AI Recommendation: High rejection rate - review data quality")
        
        if summary['average_confidence'] < 0.8:
            recommendations.append("AI Recommendation: Low confidence - consider additional training data")
        
        return recommendations
    
    def _generate_next_steps(self, summary: Dict) -> List[str]:
        """Generate next steps based on analysis"""
        next_steps = []
        
        if summary['rejected_count'] > 0:
            next_steps.append("Review rejected rows for pattern validation")
            next_steps.append("Implement recommended fixes")
        
        next_steps.append("Process approved rows")
        next_steps.append("Monitor AI validation performance")
        next_steps.append("Retrain AI with additional data if needed")
        
        return next_steps

def main():
    """Main execution function"""
    csv_file = os.getenv("SAMPLE_M1_CSV", "tests/fixtures/sample_m1.csv")
    
    if not os.path.exists(csv_file):
        logger.error(f"CSV file not found: {csv_file}")
        return
    
    # Check for AI API key
    if not (os.getenv('GROQ_API_KEY') or os.getenv('OPENROUTER_API_KEY') or os.getenv('OPENAI_API_KEY')):
        logger.error("No AI API key found. Set GROQ_API_KEY or OPENROUTER_API_KEY in .env")
        return

    logger.info(f"AI-Powered POZI M1 Validation: Starting intelligent analysis via {AI_PROVIDER}...")
    
    validator = OpenAIPoziValidator()
    
    try:
        # Generate OpenAI-powered validation report
        report = validator.generate_openai_report(csv_file)
        
        # Save detailed report
        with open('openai_validation_report.json', 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        # Save CSV results
        results_df = pd.DataFrame(report['validation_results'])
        results_df.to_csv('openai_validation_results.csv', index=False)
        
        logger.info("OpenAI Validation Complete!")
        logger.info(f"Report saved to: openai_validation_report.json")
        logger.info(f"Results saved to: openai_validation_results.csv")
        
        # Print summary
        print("\n" + "="*70)
        print("OPENAI-POWERED POZI M1 VALIDATION SUMMARY")
        print("="*70)
        
        summary = report['summary_statistics']
        print(f"Total Rows Analyzed: {summary['total_rows']}")
        print(f"Rows to KEEP: {summary['kept_count']} ({summary['kept_count']/summary['total_rows']*100:.1f}%)")
        print(f"Rows to REJECT: {summary['rejected_count']} ({summary['rejected_count']/summary['total_rows']*100:.1f}%)")
        print(f"AI Average Confidence: {summary['average_confidence']:.1%}")
        
        print(f"\nTop Rejection Reasons:")
        for reason, count in sorted(summary['rejection_reasons'].items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  - {reason}: {count} rows")
        
        print(f"\nAI Patterns Learned:")
        patterns = report['openai_analysis']['patterns_learned']
        if patterns.get('patterns'):
            for pattern_type, pattern_list in patterns['patterns'].items():
                print(f"  - {pattern_type}: {len(pattern_list)} patterns")
        
        print(f"\nAI Recommendations:")
        for rec in report['ai_recommendations']:
            print(f"  - {rec}")
        
        print(f"\nNext Steps:")
        for step in report['next_steps']:
            print(f"  - {step}")
        
        print("\n" + "="*70)
        
    except Exception as e:
        logger.error(f"OpenAI Validation failed: {e}")
        raise

if __name__ == "__main__":
    main()
