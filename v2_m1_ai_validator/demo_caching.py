"""
Demo script to showcase the caching benefits of the Enhanced M1 Validator
"""
import pandas as pd
import time
import logging
import sys
import os

# Import directly from the current package
from data_processing.enhanced_validator import EnhancedM1Validator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('CachingDemo')

def create_sample_data(num_records=100):
    """Create sample data for testing"""
    data = []
    for i in range(num_records):
        # Create some duplicate records to demonstrate caching benefits
        record_type = i % 5  # This creates 5 different record types that repeat
        
        if record_type == 0:
            data.append({
                'property_pfi': f'P{i}',
                'propnum': f'123{i % 10}',
                'address': f'123 Main St {i % 10}',
                'edit_code': 'I',
                'comments': 'New property'
            })
        elif record_type == 1:
            data.append({
                'property_pfi': f'P{i}',
                'propnum': f'456{i % 10}',
                'address': f'456 Oak Ave {i % 10}',
                'edit_code': 'U',
                'comments': 'Updated property'
            })
        elif record_type == 2:
            data.append({
                'property_pfi': f'P{i}',
                'propnum': f'789{i % 10}',
                'address': f'789 Pine Rd {i % 10}',
                'edit_code': 'R',
                'comments': 'Retired property'
            })
        elif record_type == 3:
            data.append({
                'property_pfi': f'P{i}',
                'propnum': f'101{i % 10}',
                'address': f'101 Elm St {i % 10}',
                'edit_code': 'A',
                'comments': 'Address change'
            })
        else:
            data.append({
                'property_pfi': f'P{i}',
                'propnum': f'202{i % 10}',
                'address': f'202 Cedar Ln {i % 10}',
                'edit_code': 'E',
                'comments': 'Edit property'
            })
    
    return pd.DataFrame(data)

def run_validation_test(with_cache=True):
    """Run validation test with or without caching"""
    validator = EnhancedM1Validator(confidence_threshold=0.7, enable_caching=with_cache)
    
    # Create sample data
    data = create_sample_data(200)
    
    # First run - should be similar for both cached and non-cached
    logger.info(f"Running first validation pass ({'with cache' if with_cache else 'without cache'})")
    start_time = time.time()
    result_df, stats = validator.validate_data(data, 'property')
    first_run_time = time.time() - start_time
    
    # Second run - should be faster with caching
    logger.info(f"Running second validation pass ({'with cache' if with_cache else 'without cache'})")
    start_time = time.time()
    result_df, stats = validator.validate_data(data, 'property')
    second_run_time = time.time() - start_time
    
    # Display cache stats if enabled
    if with_cache:
        cache_stats = validator.get_cache_stats()
        logger.info(f"Cache stats: {cache_stats}")
    
    return {
        'first_run_time': first_run_time,
        'second_run_time': second_run_time,
        'improvement': (first_run_time - second_run_time) / first_run_time * 100 if first_run_time > 0 else 0,
        'cache_hits': stats.get('cache_hits', 0),
        'cache_misses': stats.get('cache_misses', 0)
    }

def main():
    """Main function to run the demo"""
    logger.info("Starting caching demo")
    
    # Run without cache
    logger.info("=== Testing without cache ===")
    no_cache_results = run_validation_test(with_cache=False)
    
    # Run with cache
    logger.info("=== Testing with cache ===")
    cache_results = run_validation_test(with_cache=True)
    
    # Compare results
    logger.info("\n=== Results Comparison ===")
    logger.info(f"Without cache:")
    logger.info(f"  First run: {no_cache_results['first_run_time']:.4f} seconds")
    logger.info(f"  Second run: {no_cache_results['second_run_time']:.4f} seconds")
    logger.info(f"  Improvement: {no_cache_results['improvement']:.2f}%")
    
    logger.info(f"With cache:")
    logger.info(f"  First run: {cache_results['first_run_time']:.4f} seconds")
    logger.info(f"  Second run: {cache_results['second_run_time']:.4f} seconds")
    logger.info(f"  Improvement: {cache_results['improvement']:.2f}%")
    logger.info(f"  Cache hits: {cache_results['cache_hits']}")
    logger.info(f"  Cache misses: {cache_results['cache_misses']}")
    
    # Calculate overall benefit
    cache_benefit = ((no_cache_results['second_run_time'] - cache_results['second_run_time']) 
                     / no_cache_results['second_run_time'] * 100)
    logger.info(f"\nOverall cache benefit: {cache_benefit:.2f}% faster with caching")

if __name__ == "__main__":
    main()