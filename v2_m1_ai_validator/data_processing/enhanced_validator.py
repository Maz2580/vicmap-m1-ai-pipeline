"""
Enhanced M1 Validator with AI-powered features
Integrates all AI components for comprehensive validation
"""
import logging
import pandas as pd
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import os
import sys
import time
import hashlib
import json

# Add the parent directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from .validator import M1Validator
from .ai_field_mapper import AIFieldMapper
from .ai_error_recovery import AIErrorRecovery
from .ai_comment_enhancer import AICommentEnhancer
# Import ValidationCache directly
from utils.query_optimizer import ValidationCache

class EnhancedM1Validator:
    """Enhanced M1 Validator with AI-powered features"""
    
    def __init__(self, confidence_threshold=0.7, enable_caching=True):
        self.logger = logging.getLogger('EnhancedM1Validator')
        
        # Initialize components
        self.base_validator = M1Validator()
        self.field_mapper = AIFieldMapper()
        self.error_recovery = AIErrorRecovery()
        self.comment_enhancer = AICommentEnhancer()
        
        # Confidence threshold for auto-fixes (0.0 to 1.0)
        # Higher values mean more conservative auto-fixing
        self.confidence_threshold = confidence_threshold
        
        # Initialize caching system
        self.enable_caching = enable_caching
        self.validation_cache = ValidationCache(max_size=2000, ttl=3600) if enable_caching else None
        
        # Validation statistics
        self.stats = {
            'total_records': 0,
            'valid_records': 0,
            'invalid_records': 0,
            'auto_fixed': 0,
            'manual_review_required': 0,
            'error_types': {},
            'processing_time': 0,
            'auto_fix_attempts': 0,
            'auto_fix_skipped': 0,  # Skipped due to low confidence
            'cache_hits': 0,
            'cache_misses': 0
        }
    
    def validate_data(self, data: pd.DataFrame, layer_type: str, auto_fix: bool = True) -> Tuple[pd.DataFrame, Dict]:
        """
        Validate data with AI enhancements
        
        Args:
            data: DataFrame containing records to validate
            layer_type: Type of layer ('property', 'parcel', 'address')
            auto_fix: Whether to attempt automatic fixes
            
        Returns:
            Tuple of (validated DataFrame, statistics)
        """
        start_time = time.time()
        
        # Reset statistics
        self.stats = {
            'total_records': 0,
            'valid_records': 0,
            'invalid_records': 0,
            'auto_fixed': 0,
            'manual_review_required': 0,
            'error_types': {},
            'processing_time': 0,
            'auto_fix_attempts': 0,
            'auto_fix_skipped': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }
        
        self.stats['total_records'] = len(data)
        
        # Create a copy of the data to add validation results
        result_df = data.copy()
        result_df['validation_status'] = 'valid'
        result_df['validation_issues'] = None
        result_df['suggested_fixes'] = None
        
        # Validate each record
        for i, row in data.iterrows():
            record = row.to_dict()
            record_result = self._validate_record_with_ai(record, i, auto_fix, layer_type)
            
            # Update result DataFrame
            if record_result['issues']:
                result_df.at[i, 'validation_status'] = 'invalid'
                result_df.at[i, 'validation_issues'] = '; '.join(record_result['issues'])
                
                if record_result.get('suggested_fixes'):
                    result_df.at[i, 'suggested_fixes'] = '; '.join(record_result['suggested_fixes'])
        
        # Update statistics
        self.stats['processing_time'] = time.time() - start_time
        
        # Add cache efficiency to report if caching is enabled
        if self.enable_caching:
            total_cache_requests = self.stats['cache_hits'] + self.stats['cache_misses']
            if total_cache_requests > 0:
                self.stats['cache_efficiency'] = (self.stats['cache_hits'] / total_cache_requests) * 100
            else:
                self.stats['cache_efficiency'] = 0
        
        return result_df, self.stats
        
    def validate_m1_file(self, file_path: str, auto_fix: bool = True) -> Dict[str, any]:
        """
        Validate M1 file with AI enhancements
        
        Args:
            file_path: Path to M1 file (CSV or Excel)
            auto_fix: Whether to attempt automatic fixes
            
        Returns:
            Comprehensive validation results
        """
        start_time = datetime.now()
        
        try:
            # Load M1 data
            m1_data = self._load_m1_data(file_path)
            self.stats['total_records'] = len(m1_data)
            
            # Validate each record
            validation_results = []
            errors = []
            
            for i, record in enumerate(m1_data):
                record_result = self._validate_record_with_ai(record, i, auto_fix)
                validation_results.append(record_result)
                
                if record_result['issues']:
                    errors.append((record, record_result['issues']))
            
            # Generate comprehensive report
            report = self._generate_validation_report(validation_results, errors)
            
            # Update statistics
            self.stats['processing_time'] = (datetime.now() - start_time).total_seconds()
            
            return report
            
        except Exception as e:
            self.logger.error(f"Error validating M1 file: {e}")
            return {
                'success': False,
                'error': str(e),
                'records_processed': 0,
                'validation_results': []
            }
    
    def _load_m1_data(self, file_path: str) -> List[Dict]:
        """Load M1 data from file"""
        try:
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path)
            elif file_path.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_path)
            else:
                raise ValueError("Unsupported file format. Use CSV or Excel files.")
            
            # Convert to list of dictionaries
            return df.to_dict('records')
            
        except Exception as e:
            self.logger.error(f"Error loading M1 data: {e}")
            raise
    
    def _validate_record_with_ai(self, record: Dict, index: int, auto_fix: bool, layer_type: str = 'property') -> Dict[str, any]:
        """Validate single record with AI enhancements"""
        result = {
            'index': index,
            'record': record.copy(),
            'issues': [],
            'suggestions': [],
            'auto_fixes': {},
            'enhanced_comment': None,
            'field_mappings': {},
            'validation_passed': False
        }
        
        # Check cache if enabled
        if self.enable_caching and self.validation_cache:
            # Create a cache key from record data and layer type
            cache_data = {
                'record': record,
                'layer_type': layer_type
            }
            cached_result = self.validation_cache.get(cache_data)
            
            if cached_result:
                self.stats['cache_hits'] += 1
                return cached_result
            else:
                self.stats['cache_misses'] += 1
        
        try:
            # Check cache first if enabled
            if self.enable_caching:
                # Create a hash of the record for cache key
                record_str = json.dumps(record, sort_keys=True)
                cache_key = hashlib.md5(record_str.encode()).hexdigest()
                
                # Try to get from cache
                cached_result = self.validation_cache.get(cache_key)
                if cached_result:
                    self.stats['cache_hits'] += 1
                    return cached_result
                else:
                    self.stats['cache_misses'] += 1
            
            # Clean record data - convert NaN and None to empty strings, handle floats
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
            
            # 1. Field mapping analysis
            field_analysis = self._analyze_field_mappings(cleaned_record)
            result['field_mappings'] = field_analysis
            
            # 2. Basic validation
            issues = self.base_validator.validate_row(cleaned_record)
            result['issues'] = issues
            
            # 3. AI-powered error analysis and recovery
            if issues:
                for issue in issues:
                    error_analysis = self.error_recovery.analyze_error(issue, cleaned_record)
                    result['suggestions'].extend(error_analysis['solutions'])
                    
                    self.stats['auto_fix_attempts'] += 1
                    
                    # Only apply auto-fixes if confidence exceeds threshold
                    if (error_analysis['auto_fix_available'] and 
                        auto_fix and 
                        error_analysis['confidence'] >= self.confidence_threshold):
                        result['auto_fixes'].update(error_analysis['suggested_changes'])
                    elif error_analysis['auto_fix_available'] and auto_fix:
                        # Track skipped auto-fixes due to low confidence
                        self.stats['auto_fix_skipped'] += 1
                        result['suggestions'].append(f"Auto-fix available but skipped due to low confidence ({error_analysis['confidence']:.2f} < {self.confidence_threshold:.2f})")
            
            # 4. Comment enhancement
            enhanced_comment = self.comment_enhancer.enhance_comment(cleaned_record)
            if enhanced_comment != cleaned_record.get('comments', ''):
                result['enhanced_comment'] = enhanced_comment
                result['suggestions'].append("Consider using the enhanced comment")
            
            # 5. Determine if validation passed
            result['validation_passed'] = len(issues) == 0
            
            # Update statistics
            if result['validation_passed']:
                self.stats['valid_records'] += 1
            else:
                self.stats['invalid_records'] += 1
                
                # Count error types
                for issue in issues:
                    error_type = self._classify_error_type(issue)
                    self.stats['error_types'][error_type] = self.stats['error_types'].get(error_type, 0) + 1
            
            if result['auto_fixes']:
                self.stats['auto_fixed'] += 1
            
            # Store in cache if enabled
            if self.enable_caching and self.validation_cache:
                cache_data = {
                    'record': record,
                    'layer_type': layer_type
                }
                self.validation_cache.set(cache_data, result)
            
        except Exception as e:
            self.logger.error(f"Error validating record {index}: {e}")
            result['issues'].append(f"Validation error: {str(e)}")
            result['suggestions'].append("Manual review required due to validation error")
        
        return result
    
    def _analyze_field_mappings(self, record: Dict) -> Dict[str, any]:
        """Analyze field mappings for the record"""
        analysis = {}
        
        # Analyze each layer type
        for layer_type in ['property', 'parcel', 'address']:
            layer_analysis = {}
            
            for field, value in record.items():
                if value and str(value).strip() and str(value).lower() != 'nan':  # Only analyze non-empty fields
                    is_valid, correct_field, suggestions = self.field_mapper.validate_field_name(field, layer_type)
                    layer_analysis[field] = {
                        'is_valid': is_valid,
                        'correct_field': correct_field,
                        'suggestions': suggestions
                    }
            
            if layer_analysis:
                analysis[layer_type] = layer_analysis
        
        return analysis
    
    def _classify_error_type(self, error_message: str) -> str:
        """Classify error type for statistics"""
        error_lower = error_message.lower()
        
        if 'road-locality' in error_lower:
            return 'road_locality_issue'
        elif 'not found' in error_lower:
            return 'not_found'
        elif 'missing' in error_lower:
            return 'missing_field'
        elif 'invalid' in error_lower:
            return 'invalid_format'
        elif 'timeout' in error_lower:
            return 'timeout'
        else:
            return 'other'
    
    def _generate_validation_report(self, validation_results: List[Dict], errors: List[Tuple]) -> Dict[str, any]:
        """Generate comprehensive validation report"""
        report = {
            'success': True,
            'summary': {
                'total_records': self.stats['total_records'],
                'valid_records': self.stats['valid_records'],
                'invalid_records': self.stats['invalid_records'],
                'auto_fixed': self.stats['auto_fixed'],
                'manual_review_required': self.stats['invalid_records'] - self.stats['auto_fixed'],
                'validation_rate': (self.stats['valid_records'] / max(1, self.stats['total_records'])) * 100,
                'processing_time': self.stats['processing_time'],
                'cache_hits': self.stats.get('cache_hits', 0),
                'cache_misses': self.stats.get('cache_misses', 0)
            },
            'error_analysis': {
                'error_types': self.stats['error_types'],
                'common_issues': self._identify_common_issues(validation_results),
                'error_recovery_report': self.error_recovery.generate_recovery_report(errors)
            },
            'ai_insights': {
                'field_mapping_issues': self._analyze_field_mapping_issues(validation_results),
                'comment_quality': self._analyze_comment_quality(validation_results),
                'suggestions': self._generate_ai_suggestions(validation_results)
            },
            'validation_results': validation_results,
            'recommendations': self._generate_recommendations(validation_results)
        }
        
        # Add cache statistics if caching is enabled
        if self.enable_caching and self.validation_cache:
            report['summary']['cache_efficiency'] = (self.stats.get('cache_hits', 0) / max(1, self.stats.get('cache_hits', 0) + self.stats.get('cache_misses', 0))) * 100
        
        return report
    
    def _identify_common_issues(self, validation_results: List[Dict]) -> List[str]:
        """Identify common issues across records"""
        issue_counts = {}
        
        for result in validation_results:
            for issue in result['issues']:
                issue_type = self._classify_error_type(issue)
                issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1
        
        # Sort by frequency
        sorted_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)
        
        return [f"{issue_type}: {count} occurrences" for issue_type, count in sorted_issues[:5]]
    
    def _analyze_field_mapping_issues(self, validation_results: List[Dict]) -> Dict[str, any]:
        """Analyze field mapping issues"""
        mapping_issues = 0
        total_fields = 0
        
        for result in validation_results:
            for layer_type, field_analysis in result.get('field_mappings', {}).items():
                for field, analysis in field_analysis.items():
                    total_fields += 1
                    if not analysis['is_valid']:
                        mapping_issues += 1
        
        return {
            'total_fields_analyzed': total_fields,
            'mapping_issues': mapping_issues,
            'mapping_accuracy': ((total_fields - mapping_issues) / max(1, total_fields)) * 100
        }
    
    def _analyze_comment_quality(self, validation_results: List[Dict]) -> Dict[str, any]:
        """Analyze comment quality"""
        comments = [result['record'].get('comments', '') for result in validation_results]
        return self.comment_enhancer.analyze_comment_quality(comments)
    
    def _generate_ai_suggestions(self, validation_results: List[Dict]) -> List[str]:
        """Generate AI-powered suggestions"""
        suggestions = []
        
        # Analyze patterns
        auto_fixable_count = sum(1 for result in validation_results if result['auto_fixes'])
        if auto_fixable_count > 0:
            suggestions.append(f"{auto_fixable_count} records can be auto-fixed")
        
        # Check for common patterns
        lga_issues = sum(1 for result in validation_results 
                        if any('lga' in issue.lower() for issue in result['issues']))
        if lga_issues > 0:
            suggestions.append(f"{lga_issues} records have LGA code issues - verify each lga_code matches your configured LGA_CODE")
        
        road_issues = sum(1 for result in validation_results 
                         if any('road' in issue.lower() for issue in result['issues']))
        if road_issues > 0:
            suggestions.append(f"{road_issues} records have road/locality issues - consider adding 'new_road' flag")
        
        return suggestions
    
    def _generate_recommendations(self, validation_results: List[Dict]) -> List[str]:
        """Generate recommendations for improving M1 data"""
        recommendations = []
        
        # Check validation rate
        validation_rate = (self.stats['valid_records'] / max(1, self.stats['total_records'])) * 100
        if validation_rate < 80:
            recommendations.append("Validation rate is below 80% - review common error patterns")
        
        # Check for field mapping issues
        mapping_issues = self._analyze_field_mapping_issues(validation_results)
        if mapping_issues['mapping_accuracy'] < 95:
            recommendations.append("Field mapping accuracy is below 95% - verify field names against VicMap schema")
        
        # Check comment quality
        comment_quality = self._analyze_comment_quality(validation_results)
        if comment_quality['quality_score'] < 70:
            recommendations.append("Comment quality is below 70% - use AI comment enhancement")
        
        return recommendations
    
    def export_validation_report(self, report: Dict[str, any], output_path: str):
        """Export validation report to file"""
        try:
            # Create detailed report
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("M1 Validation Report\n")
                f.write("=" * 50 + "\n\n")
                
                # Summary
                summary = report['summary']
                f.write("SUMMARY\n")
                f.write("-" * 20 + "\n")
                f.write(f"Total Records: {summary['total_records']}\n")
                f.write(f"Valid Records: {summary['valid_records']}\n")
                f.write(f"Invalid Records: {summary['invalid_records']}\n")
                f.write(f"Auto-fixed: {summary['auto_fixed']}\n")
                f.write(f"Manual Review Required: {summary['manual_review_required']}\n")
                f.write(f"Validation Rate: {summary['validation_rate']:.1f}%\n")
                f.write(f"Processing Time: {summary['processing_time']:.2f} seconds\n\n")
                
                # Error Analysis
                f.write("ERROR ANALYSIS\n")
                f.write("-" * 20 + "\n")
                for error_type, count in report['error_analysis']['error_types'].items():
                    f.write(f"{error_type}: {count}\n")
                f.write("\n")
                
                # AI Insights
                f.write("AI INSIGHTS\n")
                f.write("-" * 20 + "\n")
                for suggestion in report['ai_insights']['suggestions']:
                    f.write(f"- {suggestion}\n")
                f.write("\n")
                
                # Recommendations
                f.write("RECOMMENDATIONS\n")
                f.write("-" * 20 + "\n")
                for recommendation in report['recommendations']:
                    f.write(f"- {recommendation}\n")
                f.write("\n")
                
                # Detailed Results
                f.write("DETAILED RESULTS\n")
                f.write("-" * 20 + "\n")
                for result in report['validation_results']:
                    if result['issues']:
                        f.write(f"Record {result['index']}:\n")
                        for issue in result['issues']:
                            f.write(f"  - {issue}\n")
                        if result['suggestions']:
                            f.write("  Suggestions:\n")
                            for suggestion in result['suggestions']:
                                f.write(f"    - {suggestion}\n")
                        f.write("\n")
            
            self.logger.info(f"Validation report exported to {output_path}")
            
        except Exception as e:
            self.logger.error(f"Error exporting validation report: {e}")
            raise
            
    def get_validation_report(self) -> Dict:
        """Get a comprehensive validation report"""
        report = {
            'summary': {
                'total_records': self.stats['total_records'],
                'valid_records': self.stats['valid_records'],
                'invalid_records': self.stats['invalid_records'],
                'auto_fixed': self.stats['auto_fixed'],
                'manual_review_required': self.stats['invalid_records'] - self.stats['auto_fixed'],
                'validation_rate': (self.stats['valid_records'] / max(1, self.stats['total_records'])) * 100,
                'processing_time': self.stats['processing_time'],
                'cache_hits': self.stats.get('cache_hits', 0),
                'cache_misses': self.stats.get('cache_misses', 0)
            },
            'error_analysis': {
                'error_types': self.stats['error_types'],
                'auto_fix_attempts': self.stats.get('auto_fix_attempts', 0),
                'auto_fix_success_rate': (self.stats['auto_fixed'] / max(1, self.stats.get('auto_fix_attempts', 0))) * 100,
                'auto_fix_skipped': self.stats.get('auto_fix_skipped', 0)
            },
            'performance': {
                'records_per_second': self.stats['total_records'] / max(0.001, self.stats['processing_time']),
                'average_time_per_record': self.stats['processing_time'] / max(1, self.stats['total_records'])
            }
        }
        
        # Add cache statistics if caching is enabled
        if self.enable_caching and self.validation_cache:
            report['summary']['cache_efficiency'] = (self.stats.get('cache_hits', 0) / max(1, self.stats.get('cache_hits', 0) + self.stats.get('cache_misses', 0))) * 100
        
        return report
        
    def clear_cache(self) -> None:
        """Clear the validation cache"""
        if self.enable_caching and self.validation_cache:
            self.validation_cache.clear()
            self.logger.info("Validation cache cleared")
            
    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        if self.enable_caching and self.validation_cache:
            return self.validation_cache.get_stats()
        return {"enabled": False}
        
    def set_caching(self, enable: bool) -> None:
        """Enable or disable caching"""
        if enable and not self.enable_caching:
            self.enable_caching = True
            self.validation_cache = ValidationCache(max_size=2000, ttl=3600)
            self.logger.info("Validation caching enabled")
        elif not enable and self.enable_caching:
            self.enable_caching = False
            self.validation_cache = None
            self.logger.info("Validation caching disabled")
