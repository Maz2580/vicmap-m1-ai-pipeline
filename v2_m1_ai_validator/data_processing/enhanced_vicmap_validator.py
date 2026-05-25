"""
Enhanced VicMap Validator with improved timeout handling and retry logic
Designed for large M1 datasets with 5-7 minute processing times
"""
import os
import logging
import requests
import json
import time
from typing import Dict, List, Optional, Tuple
from .feature_layer import FeatureLayer

logger = logging.getLogger(__name__)

class EnhancedVicmapValidator:
    """
    Enhanced VicMap validator with robust timeout handling and retry logic
    Designed to handle large M1 datasets with extended processing times
    """
    
    # Set LGA_CODE env var to your council's 3-digit Victorian LGA code (find it
    # at https://www.land.vic.gov.au). Default empty — adopters must set this.
    LGA_CODE = os.getenv('LGA_CODE', '')
    
    # REST API endpoints
    ENDPOINTS = {
        'address': 'https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/arcgis/rest/services/Vicmap_Address/FeatureServer/0',
        'property': 'https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/arcgis/rest/services/Vicmap_Property/FeatureServer/0',
        'parcel': 'https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/arcgis/rest/services/Vicmap_Parcel/FeatureServer/0',
        'planning': 'https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/arcgis/rest/services/Vicmap_Planning/FeatureServer/0'
    }
    
    # Timeout settings for large datasets
    TIMEOUT_SETTINGS = {
        'default': 300,      # 5 minutes
        'property_query': 300,  # 5 minutes
        'address_query': 300,   # 5 minutes
        'parcel_query': 300,    # 5 minutes
        'retry_delay': 5,       # 5 seconds between retries
        'max_retries': 3        # Maximum retry attempts
    }

    def __init__(self):
        """Initialize the enhanced validator"""
        self.logger = logging.getLogger('EnhancedVicmapValidator')
        self.cache = {}  # Simple cache to store recent queries
        self.session = requests.Session()
        
        # Set session timeout
        self.session.timeout = self.TIMEOUT_SETTINGS['default']
        
        # Initialize feature layers with enhanced timeouts
        self.address_layer = FeatureLayer(self.ENDPOINTS['address'], 'address')
        self.property_layer = FeatureLayer(self.ENDPOINTS['property'], 'property')
        self.parcel_layer = FeatureLayer(self.ENDPOINTS['parcel'], 'parcel')

    def _make_request_with_retry(self, url: str, params: Dict, timeout: int = None, 
                                operation_name: str = "API request") -> Optional[Dict]:
        """
        Make API request with retry logic and enhanced timeout handling
        
        Args:
            url: API endpoint URL
            params: Query parameters
            timeout: Request timeout (defaults to TIMEOUT_SETTINGS['default'])
            operation_name: Name of operation for logging
            
        Returns:
            JSON response data or None if failed
        """
        if timeout is None:
            timeout = self.TIMEOUT_SETTINGS['default']
            
        for attempt in range(self.TIMEOUT_SETTINGS['max_retries']):
            try:
                self.logger.info(f"{operation_name} - Attempt {attempt + 1}/{self.TIMEOUT_SETTINGS['max_retries']}")
                self.logger.info(f"Requesting: {url}")
                self.logger.info(f"Timeout: {timeout} seconds")
                
                response = self.session.get(url, params=params, timeout=timeout)
                
                if response.status_code == 200:
                    data = response.json()
                    if 'error' in data:
                        self.logger.warning(f"API returned error: {data['error']}")
                        return None
                    return data
                else:
                    self.logger.warning(f"HTTP {response.status_code}: {response.text}")
                    if attempt < self.TIMEOUT_SETTINGS['max_retries'] - 1:
                        time.sleep(self.TIMEOUT_SETTINGS['retry_delay'])
                        continue
                    return None
                    
            except requests.exceptions.Timeout:
                self.logger.warning(f"Timeout on attempt {attempt + 1} for {operation_name}")
                if attempt < self.TIMEOUT_SETTINGS['max_retries'] - 1:
                    self.logger.info(f"Retrying in {self.TIMEOUT_SETTINGS['retry_delay']} seconds...")
                    time.sleep(self.TIMEOUT_SETTINGS['retry_delay'])
                    continue
                else:
                    self.logger.error(f"All retry attempts failed for {operation_name}")
                    return None
                    
            except requests.exceptions.ConnectionError as e:
                self.logger.error(f"Connection error on attempt {attempt + 1}: {e}")
                if attempt < self.TIMEOUT_SETTINGS['max_retries'] - 1:
                    time.sleep(self.TIMEOUT_SETTINGS['retry_delay'])
                    continue
                return None
                
            except Exception as e:
                self.logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
                return None
        
        return None

    def validate_propnum_batch(self, propnums: List[str]) -> Dict[str, Tuple[bool, List[str]]]:
        """
        Validate multiple property numbers in batch for efficiency
        
        Args:
            propnums: List of property numbers to validate
            
        Returns:
            Dictionary mapping propnum to (exists, messages) tuple
        """
        self.logger.info(f"Validating {len(propnums)} property numbers in batch")
        
        results = {}
        
        # Process in smaller batches to avoid overwhelming the API
        batch_size = 50
        for i in range(0, len(propnums), batch_size):
            batch = propnums[i:i + batch_size]
            self.logger.info(f"Processing batch {i//batch_size + 1}/{(len(propnums) + batch_size - 1)//batch_size}")
            
            for propnum in batch:
                results[propnum] = self.validate_propnum(propnum)
        
        return results

    def validate_propnum(self, propnum: str) -> Tuple[bool, List[str]]:
        """
        Validate if a property number exists in Greater Shepparton
        Enhanced with better timeout handling and retry logic
        
        Args:
            propnum: Property number to validate
            
        Returns:
            Tuple of (exists, messages)
        """
        cache_key = f'propnum_{propnum}'
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Optimized query - put more specific field first
        where_clause = f"prop_propnum='{propnum}' AND prop_lga_code='{self.LGA_CODE}'"
        
        params = {
            'where': where_clause,
            'outFields': 'prop_propnum,prop_pfi,prop_status',
            'returnGeometry': 'false',
            'f': 'json',
            'resultRecordCount': 1
        }
        
        url = f"{self.ENDPOINTS['property']}/query"
        data = self._make_request_with_retry(
            url, params, 
            timeout=self.TIMEOUT_SETTINGS['property_query'],
            operation_name=f"Property validation for {propnum}"
        )
        
        if data is None:
            return False, [f"Failed to validate property {propnum} after retries"]
        
        messages = []
        exists = False
        
        if not data.get('features'):
            messages.append(f"Property number {propnum} not found in Greater Shepparton")
        else:
            exists = True
            property_info = data['features'][0]['attributes']
            if property_info.get('prop_status') != 'A':
                messages.append(f"Warning: Property {propnum} is not active in VicMap")
        
        # Cache the result
        self.cache[cache_key] = (exists, messages)
        return exists, messages

    def validate_spi_batch(self, spis: List[str]) -> Dict[str, Tuple[bool, List[str]]]:
        """
        Validate multiple SPIs in batch for efficiency
        
        Args:
            spis: List of SPIs to validate
            
        Returns:
            Dictionary mapping SPI to (exists, messages) tuple
        """
        self.logger.info(f"Validating {len(spis)} SPIs in batch")
        
        results = {}
        
        # Process in smaller batches
        batch_size = 50
        for i in range(0, len(spis), batch_size):
            batch = spis[i:i + batch_size]
            self.logger.info(f"Processing SPI batch {i//batch_size + 1}/{(len(spis) + batch_size - 1)//batch_size}")
            
            for spi in batch:
                results[spi] = self.validate_spi(spi)
        
        return results

    def validate_spi(self, spi: str) -> Tuple[bool, List[str]]:
        """
        Validate if an SPI exists in Greater Shepparton
        Enhanced with better timeout handling
        
        Args:
            spi: SPI to validate
            
        Returns:
            Tuple of (exists, messages)
        """
        cache_key = f'spi_{spi}'
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Escape SQL single quotes by doubling them. Done in a temp variable
        # so the f-string below stays valid on Python 3.10/3.11 (PEP 701
        # allowing same-quote nesting inside f-strings is 3.12+ only).
        escaped_spi = spi.replace("'", "''")
        where_clause = (f"parcel_lga_code='{self.LGA_CODE}' AND "
                       f"parcel_spi='{escaped_spi}'")
        
        params = {
            'where': where_clause,
            'outFields': 'parcel_spi,parcel_status,parcel_road',
            'returnGeometry': 'false',
            'f': 'json'
        }
        
        url = f"{self.ENDPOINTS['parcel']}/query"
        data = self._make_request_with_retry(
            url, params,
            timeout=self.TIMEOUT_SETTINGS['parcel_query'],
            operation_name=f"SPI validation for {spi}"
        )
        
        if data is None:
            return False, [f"Failed to validate SPI {spi} after retries"]
        
        messages = []
        exists = False
        
        if not data.get('features'):
            messages.append(f"SPI {spi} not found in Greater Shepparton")
        else:
            exists = True
            parcel = data['features'][0]['attributes']
            if parcel.get('parcel_status') != 'A':
                messages.append(f"Warning: Parcel {spi} is not active in VicMap")
            if parcel.get('parcel_road') == 'Y':
                messages.append("Road parcel identified")

        self.cache[cache_key] = (exists, messages)
        return exists, messages

    def validate_address_batch(self, addresses: List[Dict[str, str]]) -> Dict[str, Tuple[bool, List[str]]]:
        """
        Validate multiple addresses in batch for efficiency
        
        Args:
            addresses: List of address dictionaries to validate
            
        Returns:
            Dictionary mapping address key to (exists, messages) tuple
        """
        self.logger.info(f"Validating {len(addresses)} addresses in batch")
        
        results = {}
        
        # Process in smaller batches
        batch_size = 25
        for i in range(0, len(addresses), batch_size):
            batch = addresses[i:i + batch_size]
            self.logger.info(f"Processing address batch {i//batch_size + 1}/{(len(addresses) + batch_size - 1)//batch_size}")
            
            for j, address in enumerate(batch):
                address_key = f"{address.get('house_number_1', '')}_{address.get('road_name', '')}_{address.get('locality_name', '')}"
                results[address_key] = self.validate_address(address)
        
        return results

    def validate_address(self, address_data: Dict[str, str]) -> Tuple[bool, List[str]]:
        """
        Validate an address against VicMap
        Enhanced with better timeout handling
        
        Args:
            address_data: Dictionary containing address components
            
        Returns:
            Tuple of (exists, messages)
        """
        cache_key = (f"address_{address_data.get('house_number_1')}_{address_data.get('road_name')}_"
                    f"{address_data.get('road_type')}_{address_data.get('locality_name')}")
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Build where clause with proper field names
        conditions = []
        conditions.append(f"lga_code='{self.LGA_CODE}'")
        
        if address_data.get('house_number_1'):
            conditions.append(f"house_number_1='{address_data['house_number_1']}'")
        if address_data.get('road_name'):
            conditions.append(f"road_name='{address_data['road_name'].upper()}'")
        if address_data.get('road_type'):
            conditions.append(f"road_type='{address_data['road_type'].upper()}'")
        if address_data.get('locality_name'):
            conditions.append(f"locality_name='{address_data['locality_name'].upper()}'")
            
        where_clause = ' AND '.join(conditions)
        
        params = {
            'where': where_clause,
            'outFields': 'house_number_1,road_name,road_type,locality_name',
            'returnGeometry': 'false',
            'f': 'json'
        }
        
        url = f"{self.ENDPOINTS['address']}/query"
        data = self._make_request_with_retry(
            url, params,
            timeout=self.TIMEOUT_SETTINGS['address_query'],
            operation_name=f"Address validation for {address_data.get('house_number_1', '')} {address_data.get('road_name', '')}"
        )
        
        if data is None:
            return False, [f"Failed to validate address after retries"]
        
        messages = []
        exists = False
        
        if not data.get('features'):
            address_str = f"{address_data.get('house_number_1', '')} {address_data.get('road_name', '')}"
            messages.append(f"Address not found in VicMap: {address_str}")
        else:
            exists = True
                    
        self.cache[cache_key] = (exists, messages)
        return exists, messages

    def get_processing_stats(self) -> Dict[str, any]:
        """
        Get processing statistics and cache information
        
        Returns:
            Dictionary with processing statistics
        """
        return {
            'cache_size': len(self.cache),
            'timeout_settings': self.TIMEOUT_SETTINGS,
            'endpoints': list(self.ENDPOINTS.keys()),
            'lga_code': self.LGA_CODE
        }

    def clear_cache(self):
        """Clear the cache to free memory"""
        self.cache.clear()
        self.logger.info("Cache cleared")

    def set_timeout(self, timeout_seconds: int):
        """
        Set custom timeout for all requests
        
        Args:
            timeout_seconds: Timeout in seconds
        """
        self.TIMEOUT_SETTINGS['default'] = timeout_seconds
        self.TIMEOUT_SETTINGS['property_query'] = timeout_seconds
        self.TIMEOUT_SETTINGS['address_query'] = timeout_seconds
        self.TIMEOUT_SETTINGS['parcel_query'] = timeout_seconds
        self.session.timeout = timeout_seconds
        self.logger.info(f"Timeout set to {timeout_seconds} seconds")
