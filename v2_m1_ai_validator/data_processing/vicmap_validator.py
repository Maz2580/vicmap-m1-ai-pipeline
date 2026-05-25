"""
VicMap Data Validator using ArcGIS REST Services.
Filters results by the LGA_CODE env var (set to your council's Victorian LGA code).
"""
import os
import logging
import requests
import json
from typing import Dict, List, Optional, Tuple
from .feature_layer import FeatureLayer

logger = logging.getLogger(__name__)

class VicmapValidator:
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

    def __init__(self):
        """Initialize the validator"""
        self.logger = logging.getLogger('VicmapValidator')
        self.cache = {}  # Simple cache to store recent queries
        self.session = requests.Session()
        
        # Initialize feature layers
        self.address_layer = FeatureLayer(self.ENDPOINTS['address'], 'address')
        self.property_layer = FeatureLayer(self.ENDPOINTS['property'], 'property')
        self.parcel_layer = FeatureLayer(self.ENDPOINTS['parcel'], 'parcel')

    def get_property_info(self, pfi: str) -> Optional[Dict]:
        """Get property information from VicMap
        
        Args:
            pfi: Property PFI number
            
        Returns:
            Dictionary of property data if found, None otherwise
        """
        cache_key = f"property_{pfi}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # Query directly with correct field names
        where_clause = f"prop_lga_code='{self.LGA_CODE}' AND prop_pfi='{pfi}'"
        params = {
            'where': where_clause,
            'outFields': '*',
            'returnGeometry': 'false',
            'f': 'json'
        }
        
        try:
            response = requests.get(f"{self.ENDPOINTS['property']}/query", params=params, timeout=300)  # 5 minutes
            if not response.ok:
                logger.warning(f"Failed to get property info for PFI {pfi}")
                return None
                
            data = response.json()
            if not data.get('features'):
                logger.info(f"Property PFI {pfi} not found")
                return None
                
            property_info = data['features'][0]['attributes']
            self.cache[cache_key] = property_info
            return property_info
        except Exception as e:
            logger.error(f"Error getting property info: {e}")
            return None

    def validate_propnum(self, propnum: str) -> Tuple[bool, List[str]]:
        """
        Validate if a property number exists in Greater Shepparton
        Returns tuple of (exists, messages)
        """
        cache_key = f'propnum_{propnum}'
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Optimized query - put more specific field first
        where_clause = f"prop_propnum='{propnum}' AND prop_lga_code='{self.LGA_CODE}'"
        
        params = {
            'where': where_clause,
            'outFields': 'prop_propnum,prop_pfi',  # Only get needed fields
            'returnGeometry': 'false',
            'f': 'json',
            'resultRecordCount': 1  # Only need 1 result
        }
        
        try:
            response = requests.get(f"{self.ENDPOINTS['property']}/query", params=params, timeout=300)  # 5 minutes
            
            if not response.ok:
                return False, ["Unable to validate property number - API error"]
                
            data = response.json()
            messages = []
            exists = False
            
            if 'error' in data:
                messages.append(f"API Error: {data['error'].get('message', 'Unknown error')}")
            elif not data.get('features'):
                messages.append(f"Property number {propnum} not found in Greater Shepparton")
            else:
                exists = True
            
            # Cache the result
            self.cache[cache_key] = (exists, messages)
            return exists, messages
        except requests.exceptions.Timeout:
            self.logger.warning(f"Timeout validating propnum {propnum}")
            return False, [f"Timeout validating property {propnum} - API may be slow. Try again later."]
        except requests.exceptions.ConnectionError:
            self.logger.error(f"Connection error validating propnum {propnum}")
            return False, [f"Connection error validating property {propnum} - check internet connection"]
        except Exception as e:
            self.logger.error(f"Error validating propnum: {e}")
            return False, [f"Error validating property: {str(e)}"]

    def validate_spi(self, spi: str) -> Tuple[bool, List[str]]:
        """
        Validate if an SPI exists in Greater Shepparton
        Returns tuple of (exists, messages)
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
        
        try:
            response = requests.get(f"{self.ENDPOINTS['parcel']}/query", params=params, timeout=300)  # 5 minutes
            
            if not response.ok:
                return False, ["API error occurred"]
                
            data = response.json()
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
        except Exception as e:
            logger.error(f"Error validating SPI: {e}")
            return False, [f"Error validating SPI: {str(e)}"]

    def validate_address(self, address_data: Dict[str, str]) -> Tuple[bool, List[str]]:
        """Validate an address against VicMap
        
        Args:
            address_data: Dictionary containing address components:
                - house_number_1: House number
                - street_name: Road name
                - street_type: Road type (e.g., ROAD, STREET)
                - locality_name: Locality name
            
        Returns:
            Tuple of (exists, messages)
        """
        cache_key = (f"address_{address_data.get('house_number_1')}_{address_data.get('street_name')}_"
                    f"{address_data.get('street_type')}_{address_data.get('locality_name')}")
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Build where clause with proper field names
        conditions = []
        conditions.append(f"lga_code='{self.LGA_CODE}'")
        
        if address_data.get('house_number_1'):
            conditions.append(f"house_number_1='{address_data['house_number_1']}'")
        if address_data.get('street_name'):
            conditions.append(f"road_name='{address_data['street_name'].upper()}'")
        if address_data.get('street_type'):
            conditions.append(f"road_type='{address_data['street_type'].upper()}'")
        if address_data.get('locality_name'):
            conditions.append(f"locality_name='{address_data['locality_name'].upper()}'")
            
        where_clause = ' AND '.join(conditions)
        
        params = {
            'where': where_clause,
            'outFields': 'house_number_1,road_name,road_type,locality_name',
            'returnGeometry': 'false',
            'f': 'json'
        }
        
        try:
            response = requests.get(f"{self.ENDPOINTS['address']}/query", params=params, timeout=300)  # 5 minutes
            messages = []
            exists = False
            
            if not response.ok:
                messages.append("Failed to validate address")
                return False, messages
                
            data = response.json()
            
            if not data.get('features'):
                address_str = f"{address_data.get('house_number_1', '')} {address_data.get('street_name', '')}"
                messages.append(f"Address not found in VicMap: {address_str}")
                
                # Try fuzzy match on road name
                fuzzy_where = (f"lga_code='{self.LGA_CODE}' AND "
                             f"road_name LIKE '%{address_data.get('street_name', '').upper()}%'")
                
                fuzzy_params = {
                    'where': fuzzy_where,
                    'outFields': 'road_name,road_type',
                    'returnGeometry': 'false',
                    'f': 'json',
                    'resultRecordCount': 3
                }
                
                fuzzy_response = requests.get(f"{self.ENDPOINTS['address']}/query", params=fuzzy_params, timeout=300)  # 5 minutes
                if fuzzy_response.ok:
                    fuzzy_data = fuzzy_response.json()
                    if fuzzy_data.get('features'):
                        messages.append("Similar road names found:")
                        seen = set()
                        for addr in fuzzy_data['features']:
                            road_name = addr['attributes'].get('road_name', '')
                            road_type = addr['attributes'].get('road_type', '')
                            if (road_name, road_type) not in seen:
                                messages.append(f"- {road_name} {road_type}")
                                seen.add((road_name, road_type))
            else:
                exists = True
                    
            self.cache[cache_key] = (exists, messages)
            return exists, messages
        except Exception as e:
            logger.error(f"Error validating address: {e}")
            return False, [f"Error validating address: {str(e)}"]

    def clear_cache(self):
        """Clear the cache to free memory"""
        self.cache.clear()