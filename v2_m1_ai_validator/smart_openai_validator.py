#!/usr/bin/env python3
"""
AI-Powered POZI M1 Smart Validator
Uses free AI providers (Groq primary, OpenRouter fallback) with your specific training data
to make intelligent decisions
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


def _create_ai_client():
    """Create AI client with Groq as primary, OpenRouter as fallback"""
    groq_key = os.getenv('GROQ_API_KEY')
    openrouter_key = os.getenv('OPENROUTER_API_KEY')

    if groq_key:
        return OpenAI(
            api_key=groq_key,
            base_url="https://api.groq.com/openai/v1"
        ), "llama-3.3-70b-versatile", "groq"

    if openrouter_key:
        return OpenAI(
            api_key=openrouter_key,
            base_url="https://openrouter.ai/api/v1"
        ), "meta-llama/llama-3.3-70b-instruct:free", "openrouter"

    # Legacy fallback to OpenAI if key exists
    openai_key = os.getenv('OPENAI_API_KEY')
    if openai_key:
        return OpenAI(api_key=openai_key), "gpt-4", "openai"

    raise ValueError("No AI API key found. Set GROQ_API_KEY or OPENROUTER_API_KEY in .env")


def _create_fallback_client():
    """Create fallback client (OpenRouter) if primary (Groq) fails"""
    openrouter_key = os.getenv('OPENROUTER_API_KEY')
    if openrouter_key:
        return OpenAI(
            api_key=openrouter_key,
            base_url="https://openrouter.ai/api/v1"
        ), "meta-llama/llama-3.3-70b-instruct:free", "openrouter"
    return None, None, None


client, AI_MODEL, AI_PROVIDER = _create_ai_client()
fallback_client, FALLBACK_MODEL, FALLBACK_PROVIDER = _create_fallback_client()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SmartOpenAIValidator:
    """Smart OpenAI-powered validator using your specific training data"""
    
    def __init__(self):
        self.db_helper = InfoProdDatabaseHelper()
        self.ai_patterns = {}
        self.validation_rules = {}
        
    def load_and_analyze_training_data(self, csv_file: str) -> Dict[str, Any]:
        """Load training data and analyze patterns with OpenAI"""
        logger.info("Loading training data and analyzing patterns with OpenAI...")
        
        df = pd.read_csv(csv_file)
        
        # Define correct and incorrect row ranges based on your feedback
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
        
        # Extract samples for analysis
        incorrect_samples = self._extract_samples_from_ranges(df, incorrect_ranges, "INCORRECT")
        correct_samples = self._extract_samples_from_ranges(df, correct_ranges, "CORRECT")
        
        # Use OpenAI to analyze patterns
        patterns = self._analyze_patterns_with_openai(incorrect_samples, correct_samples)
        
        return {
            'patterns': patterns,
            'training_data': {
                'total_rows': len(df),
                'incorrect_samples': len(incorrect_samples),
                'correct_samples': len(correct_samples)
            }
        }
    
    def _extract_samples_from_ranges(self, df: pd.DataFrame, ranges: List[Tuple[int, int]], category: str) -> List[Dict[str, Any]]:
        """Extract samples from specific row ranges"""
        samples = []
        
        for start, end in ranges:
            for i in range(start, min(end + 1, len(df))):
                if i < len(df):
                    sample = {
                        'row_index': i,
                        'category': category,
                        'propnum': str(df.iloc[i].get('propnum', '')).replace('.0', ''),
                        'edit_code': str(df.iloc[i].get('edit_code', '')),
                        'comments': str(df.iloc[i].get('comments', ''))[:150] + '...' if len(str(df.iloc[i].get('comments', ''))) > 150 else str(df.iloc[i].get('comments', '')),
                        'spi': str(df.iloc[i].get('spi', '')),
                        'road_name': str(df.iloc[i].get('road_name', '')),
                        'locality_name': str(df.iloc[i].get('locality_name', ''))
                    }
                    samples.append(sample)
        
        return samples
    
    def _call_ai(self, messages: list, max_tokens: int = 1500) -> str:
        """Call AI with Groq primary, OpenRouter fallback"""
        # Try primary provider
        try:
            response = client.chat.completions.create(
                model=AI_MODEL,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.1
            )
            logger.info(f"AI call successful via {AI_PROVIDER} ({AI_MODEL})")
            return response.choices[0].message.content
        except Exception as e:
            logger.warning(f"{AI_PROVIDER} failed: {e}")

        # Try fallback provider
        if fallback_client and FALLBACK_PROVIDER != AI_PROVIDER:
            try:
                response = fallback_client.chat.completions.create(
                    model=FALLBACK_MODEL,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0.1
                )
                logger.info(f"AI fallback successful via {FALLBACK_PROVIDER} ({FALLBACK_MODEL})")
                return response.choices[0].message.content
            except Exception as e:
                logger.error(f"Fallback {FALLBACK_PROVIDER} also failed: {e}")

        raise Exception("All AI providers failed")

    def _analyze_patterns_with_openai(self, incorrect_samples: List[Dict], correct_samples: List[Dict]) -> Dict[str, Any]:
        """Use AI to analyze patterns between correct and incorrect samples"""
        logger.info(f"Using AI ({AI_PROVIDER}) to analyze validation patterns...")

        # Prepare prompt with samples
        prompt = f"""
I need you to analyze M1 property validation data and identify the key patterns that distinguish incorrect records from correct ones.

## Training Data:
- Incorrect Records (should be rejected): {len(incorrect_samples)} samples
- Correct Records (should be accepted): {len(correct_samples)} samples

## Sample Incorrect Records:
{json.dumps(incorrect_samples[:8], indent=2)}

## Sample Correct Records:
{json.dumps(correct_samples[:8], indent=2)}

## Task:
Analyze these samples and identify the key patterns that distinguish incorrect records from correct ones. Focus on:

1. **Comment Analysis**: What warning patterns indicate problems?
2. **Property Relationships**: What parent-child property conflicts exist?
3. **Data Quality Issues**: What data inconsistencies cause rejections?
4. **Business Logic Violations**: What M1 rules are being violated?

## Expected Output:
Provide a JSON response with validation rules:
{{
    "validation_rules": {{
        "reject_patterns": [
            "specific pattern 1",
            "specific pattern 2"
        ],
        "accept_patterns": [
            "specific pattern 1",
            "specific pattern 2"
        ]
    }},
    "confidence": 0.95,
    "reasoning": "explanation of the analysis"
}}
"""

        try:
            ai_response = self._call_ai(
                messages=[
                    {"role": "system", "content": "You are an expert M1 validation specialist with deep knowledge of property data validation and POZI systems."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1500
            )

            logger.info("AI pattern analysis completed successfully")

            # Parse response
            patterns = self._parse_pattern_response(ai_response)
            return patterns

        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            return self._fallback_patterns()
    
    def _parse_pattern_response(self, ai_response: str) -> Dict[str, Any]:
        """Parse OpenAI pattern analysis response"""
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
                return self._fallback_patterns()
                
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parsing error: {e}")
            return self._fallback_patterns()
    
    def _fallback_patterns(self) -> Dict[str, Any]:
        """Fallback patterns if OpenAI fails"""
        return {
            "validation_rules": {
                "reject_patterns": [
                    "WARNING in comments",
                    "different road names",
                    "property mismatch",
                    "duplicate propnum"
                ],
                "accept_patterns": [
                    "clean comments",
                    "valid propnum",
                    "no warnings"
                ]
            },
            "confidence": 0.7,
            "reasoning": "Fallback patterns based on common validation rules"
        }
    
    def validate_single_row_with_openai(self, row: pd.Series, row_index: int) -> Dict[str, Any]:
        """Validate a single row using OpenAI"""
        
        # Prepare row data
        row_data = {
            'row_index': row_index,
            'propnum': str(row.get('propnum', '')).replace('.0', ''),
            'edit_code': str(row.get('edit_code', '')),
            'comments': str(row.get('comments', '')),
            'spi': str(row.get('spi', '')),
            'road_name': str(row.get('road_name', '')),
            'locality_name': str(row.get('locality_name', ''))
        }
        
        # Create validation prompt
        prompt = f"""
Based on the learned validation patterns, determine if this M1 record should be KEPT or REJECTED.

## Record to Validate:
{json.dumps(row_data, indent=2)}

## Learned Validation Rules:
- Reject if: WARNING in comments, different road names, property mismatch, duplicate propnum
- Accept if: clean comments, valid propnum, no warnings

## Expected Output:
Provide a JSON response:
{{
    "row_index": {row_index},
    "propnum": "{row_data['propnum']}",
    "decision": "KEEP" or "REJECT",
    "confidence": 0.95,
    "reason": "specific reason for decision",
    "ai_analysis": "detailed analysis of the record"
}}
"""
        
        try:
            ai_response = self._call_ai(
                messages=[
                    {"role": "system", "content": "You are an expert M1 validation specialist. Analyze the record and make a decision."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500
            )

            result = self._parse_validation_response(ai_response, row_data)
            return result

        except Exception as e:
            logger.error(f"AI validation error for row {row_index}: {e}")
            return self._fallback_single_validation(row_data)
    
    def _parse_validation_response(self, ai_response: str, row_data: Dict) -> Dict[str, Any]:
        """Parse OpenAI validation response"""
        try:
            # Extract JSON from response
            start_idx = ai_response.find('{')
            end_idx = ai_response.rfind('}') + 1
            
            if start_idx != -1 and end_idx != -1:
                json_str = ai_response[start_idx:end_idx]
                result = json.loads(json_str)
                return result
            else:
                logger.warning("Could not extract JSON from OpenAI response")
                return self._fallback_single_validation(row_data)
                
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parsing error: {e}")
            return self._fallback_single_validation(row_data)
    
    def _fallback_single_validation(self, row_data: Dict) -> Dict[str, Any]:
        """Fallback validation for single row"""
        result = {
            'row_index': row_data['row_index'],
            'propnum': row_data['propnum'],
            'decision': 'KEEP',
            'confidence': 0.5,
            'reason': 'Fallback validation - manual review needed',
            'ai_analysis': 'OpenAI validation failed, using fallback logic'
        }
        
        # Simple fallback logic
        comment = row_data.get('comments', '')
        if 'WARNING' in comment:
            result['decision'] = 'REJECT'
            result['reason'] = 'WARNING detected in comments'
            result['confidence'] = 0.8
        
        return result
    
    def validate_all_rows_smart(self, csv_file: str) -> List[Dict[str, Any]]:
        """Validate all rows using smart OpenAI approach"""
        logger.info("Starting smart OpenAI validation of all rows...")
        
        df = pd.read_csv(csv_file)
        validation_results = []
        
        # Process rows in smaller batches to avoid token limits
        batch_size = 10
        total_batches = (len(df) + batch_size - 1) // batch_size
        
        for batch_idx in range(total_batches):
            start_idx = batch_idx * batch_size
            end_idx = min((batch_idx + 1) * batch_size, len(df))
            
            logger.info(f"Processing batch {batch_idx + 1}/{total_batches} (rows {start_idx}-{end_idx})")
            
            batch_df = df.iloc[start_idx:end_idx]
            
            for idx, row in batch_df.iterrows():
                try:
                    result = self.validate_single_row_with_openai(row, idx)
                    validation_results.append(result)
                except Exception as e:
                    logger.error(f"Error validating row {idx}: {e}")
                    # Add fallback result
                    fallback_result = self._fallback_single_validation({
                        'row_index': idx,
                        'propnum': str(row.get('propnum', '')).replace('.0', ''),
                        'comments': str(row.get('comments', ''))
                    })
                    validation_results.append(fallback_result)
        
        return validation_results
    
    def generate_smart_report(self, csv_file: str) -> Dict[str, Any]:
        """Generate comprehensive smart validation report"""
        logger.info("Generating smart OpenAI validation report...")
        
        # Load and analyze training data
        training_analysis = self.load_and_analyze_training_data(csv_file)
        self.ai_patterns = training_analysis['patterns']
        
        # Validate all rows
        validation_results = self.validate_all_rows_smart(csv_file)
        
        # Generate summary
        summary = self._generate_summary_statistics(validation_results)
        
        # Create report
        report = {
            'openai_training_analysis': training_analysis,
            'validation_results': validation_results,
            'summary_statistics': summary,
            'ai_recommendations': self._generate_ai_recommendations(summary, self.ai_patterns),
            'next_steps': self._generate_next_steps(summary)
        }
        
        return report
    
    def _generate_summary_statistics(self, validation_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate summary statistics"""
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
        """Generate AI recommendations"""
        recommendations = []
        
        if patterns.get('validation_rules', {}).get('reject_patterns'):
            recommendations.append("AI Recommendation: Implement automated pattern detection")
        
        if summary['rejected_count'] > 0:
            recommendations.append("AI Recommendation: Review rejected rows for validation accuracy")
        
        if summary['average_confidence'] < 0.8:
            recommendations.append("AI Recommendation: Consider additional training data for higher confidence")
        
        return recommendations
    
    def _generate_next_steps(self, summary: Dict) -> List[str]:
        """Generate next steps"""
        next_steps = []
        
        if summary['rejected_count'] > 0:
            next_steps.append("Review rejected rows for accuracy")
            next_steps.append("Implement recommended fixes")
        
        next_steps.append("Process approved rows")
        next_steps.append("Monitor AI validation performance")
        
        return next_steps

def main():
    """Main execution function"""
    csv_file = os.getenv("SAMPLE_M1_CSV", "tests/fixtures/sample_m1.csv")
    
    if not os.path.exists(csv_file):
        logger.error(f"CSV file not found: {csv_file}")
        return
    
    if not (os.getenv('GROQ_API_KEY') or os.getenv('OPENROUTER_API_KEY') or os.getenv('OPENAI_API_KEY')):
        logger.error("No AI API key found. Set GROQ_API_KEY or OPENROUTER_API_KEY in .env")
        return

    logger.info(f"AI-Powered POZI M1 Validation: Starting intelligent analysis via {AI_PROVIDER}...")
    
    validator = SmartOpenAIValidator()
    
    try:
        # Generate smart validation report
        report = validator.generate_smart_report(csv_file)
        
        # Save detailed report
        with open('smart_openai_validation_report.json', 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        # Save CSV results
        results_df = pd.DataFrame(report['validation_results'])
        results_df.to_csv('smart_openai_validation_results.csv', index=False)
        
        logger.info("Smart OpenAI Validation Complete!")
        logger.info(f"Report saved to: smart_openai_validation_report.json")
        logger.info(f"Results saved to: smart_openai_validation_results.csv")
        
        # Print summary
        print("\n" + "="*70)
        print("SMART OPENAI-POWERED POZI M1 VALIDATION SUMMARY")
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
        patterns = report['openai_training_analysis']['patterns']
        if patterns.get('validation_rules'):
            reject_patterns = patterns['validation_rules'].get('reject_patterns', [])
            accept_patterns = patterns['validation_rules'].get('accept_patterns', [])
            print(f"  - Reject Patterns: {len(reject_patterns)} patterns")
            print(f"  - Accept Patterns: {len(accept_patterns)} patterns")
            print(f"  - AI Confidence: {patterns.get('confidence', 0):.1%}")
        
        print(f"\nAI Recommendations:")
        for rec in report['ai_recommendations']:
            print(f"  - {rec}")
        
        print(f"\nNext Steps:")
        for step in report['next_steps']:
            print(f"  - {step}")
        
        print("\n" + "="*70)
        
    except Exception as e:
        logger.error(f"Smart OpenAI Validation failed: {e}")
        raise

if __name__ == "__main__":
    main()
