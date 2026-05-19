"""
Query optimization utilities for VicMap API and validation caching
"""
import logging
import hashlib
import json
import time
from typing import Dict, List, Optional, Any
from functools import lru_cache

logger = logging.getLogger(__name__)

class ValidationCache:
    """Cache for validation results to improve performance"""
    
    def __init__(self, max_size=1000, ttl=3600):
        """
        Initialize the validation cache
        
        Args:
            max_size: Maximum number of items to store in cache
            ttl: Time-to-live in seconds for cache entries
        """
        self.logger = logging.getLogger('ValidationCache')
        self.cache = {}
        self.max_size = max_size
        self.ttl = ttl
        self.hits = 0
        self.misses = 0
    
    def _generate_key(self, data: Dict) -> str:
        """Generate a unique key for the data"""
        # Sort the dictionary to ensure consistent keys
        sorted_data = json.dumps(data, sort_keys=True)
        return hashlib.md5(sorted_data.encode()).hexdigest()
    
    def get(self, data: Dict) -> Optional[Dict]:
        """
        Get cached result for data
        
        Args:
            data: The data to look up in cache
            
        Returns:
            Cached result or None if not found
        """
        key = self._generate_key(data)
        cache_entry = self.cache.get(key)
        
        if not cache_entry:
            self.misses += 1
            return None
        
        # Check if entry has expired
        timestamp, result = cache_entry
        if time.time() - timestamp > self.ttl:
            # Remove expired entry
            del self.cache[key]
            self.misses += 1
            return None
        
        self.hits += 1
        return result
    
    def set(self, data: Dict, result: Dict) -> None:
        """
        Store result in cache
        
        Args:
            data: The data to cache
            result: The result to cache
        """
        key = self._generate_key(data)
        
        # Evict oldest entries if cache is full
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][0])
            del self.cache[oldest_key]
        
        self.cache[key] = (time.time(), result)
    
    def clear(self) -> None:
        """Clear the cache"""
        self.cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests) * 100 if total_requests > 0 else 0
        
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': hit_rate,
            'ttl': self.ttl
        }

class QueryOptimizer:
    """Optimize VicMap queries for better performance"""
    
    # Field cardinality hints (lower = more selective)
    # These help determine the best order for WHERE conditions
    FIELD_SELECTIVITY = {
        'property': {
            'prop_pfi': 1,          # Unique identifier - most selective
            'prop_propnum': 1,      # Property number - very selective
            'prop_lga_code': 1000,  # LGA code - less selective
        },
        'parcel': {
            'parcel_pfi': 1,
            'parcel_spi': 1,
            'parcel_lga_code': 1000,
        },
        'address': {
            'address_pfi': 1,
            'house_nbr_1': 10,
            'road_name': 100,
            'road_type': 500,
            'locality_name': 200,
            'lga_code': 1000,
        }
    }
    
    @staticmethod
    def optimize_where_clause(layer_type: str, conditions: Dict[str, str]) -> str:
        """
        Optimize WHERE clause by ordering conditions by selectivity
        
        Args:
            layer_type: Type of layer ('property', 'parcel', 'address')
            conditions: Dictionary of field: value pairs
            
        Returns:
            Optimized WHERE clause string
        """
        selectivity = QueryOptimizer.FIELD_SELECTIVITY.get(layer_type, {})
        
        # Sort conditions by selectivity (most selective first)
        sorted_conditions = sorted(
            conditions.items(),
            key=lambda x: selectivity.get(x[0], 999)
        )
        
        # Build WHERE clause
        where_parts = []
        for field, value in sorted_conditions:
            if value:  # Skip empty values
                # Escape single quotes
                escaped_value = str(value).replace("'", "''")
                where_parts.append(f"{field}='{escaped_value}'")
        
        return ' AND '.join(where_parts) if where_parts else '1=1'
    
    @staticmethod
    def get_minimal_fields(layer_type: str, operation: str = 'validate') -> str:
        """
        Get minimal set of fields needed for an operation
        
        Args:
            layer_type: Type of layer
            operation: Operation being performed ('validate', 'details', 'all')
            
        Returns:
            Comma-separated list of field names
        """
        minimal_fields = {
            'property': {
                'validate': 'prop_pfi,prop_propnum',
                'details': 'prop_pfi,prop_propnum,prop_status,prop_lga_code',
                'all': '*'
            },
            'parcel': {
                'validate': 'parcel_pfi,parcel_spi,parcel_status',
                'details': 'parcel_pfi,parcel_spi,parcel_status,parcel_lga_code,parcel_road',
                'all': '*'
            },
            'address': {
                'validate': 'address_pfi,house_nbr_1,road_name',
                'details': 'address_pfi,house_nbr_1,road_name,road_type,locality_name',
                'all': '*'
            }
        }
        
        return minimal_fields.get(layer_type, {}).get(operation, '*')
    
    @staticmethod
    @lru_cache(maxsize=128)
    def build_optimized_query(layer_type: str, **kwargs) -> Dict:
        """
        Build an optimized query with caching
        
        Args:
            layer_type: Type of layer
            **kwargs: Query parameters
            
        Returns:
            Optimized query parameters dictionary
        """
        conditions = {k: v for k, v in kwargs.items() if v is not None}
        
        return {
            'where': QueryOptimizer.optimize_where_clause(layer_type, conditions),
            'outFields': QueryOptimizer.get_minimal_fields(layer_type, 'validate'),
            'returnGeometry': 'false',
            'f': 'json',
            'resultRecordCount': 10
        }
    
    @staticmethod
    def estimate_query_time(layer_type: str, conditions: Dict[str, str]) -> float:
        """
        Estimate query execution time based on conditions
        
        Args:
            layer_type: Type of layer
            conditions: Query conditions
            
        Returns:
            Estimated time in seconds
        """
        selectivity = QueryOptimizer.FIELD_SELECTIVITY.get(layer_type, {})
        
        # Base time
        base_time = 0.5
        
        # If we have a highly selective field, it's fast
        has_selective = any(
            selectivity.get(field, 999) == 1 
            for field in conditions.keys()
        )
        
        if has_selective:
            return base_time
        
        # Otherwise, estimate based on number of records to scan
        avg_selectivity = sum(
            selectivity.get(field, 999) 
            for field in conditions.keys()
        ) / max(len(conditions), 1)
        
        return base_time + (avg_selectivity / 100)


class QueryBatchProcessor:
    """Process multiple queries efficiently"""
    
    def __init__(self, max_batch_size: int = 50):
        self.max_batch_size = max_batch_size
        self.logger = logging.getLogger('QueryBatchProcessor')
    
    def batch_validate(self, validator, items: List[Dict], 
                      validation_type: str = 'propnum') -> Dict[str, tuple]:
        """
        Validate multiple items in batch
        
        Args:
            validator: VicmapValidator instance
            items: List of items to validate
            validation_type: Type of validation ('propnum', 'spi', 'address')
            
        Returns:
            Dictionary mapping item key to (exists, messages) tuple
        """
        results = {}
        
        for item in items:
            try:
                if validation_type == 'propnum':
                    key = item['propnum']
                    exists, messages = validator.validate_propnum(key)
                elif validation_type == 'spi':
                    key = item['spi']
                    exists, messages = validator.validate_spi(key)
                elif validation_type == 'address':
                    key = f"{item.get('house_number_1', '')}_{item.get('street_name', '')}"
                    exists, messages = validator.validate_address(item)
                else:
                    self.logger.error(f"Unknown validation type: {validation_type}")
                    continue
                
                results[key] = (exists, messages)
            except Exception as e:
                self.logger.error(f"Error validating {item}: {e}")
                results.get(str(item), (False, [str(e)]))
        
        return results