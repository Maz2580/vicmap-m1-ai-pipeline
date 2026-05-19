"""
VicMap Feature Layer API handler
"""
import requests
import logging
from typing import Dict, List, Tuple, Optional
from urllib.parse import urlencode

class FeatureLayer:
    def __init__(self, url: str, layer_type: str):
        """Initialize feature layer connection
        
        Args:
            url: Feature layer endpoint URL
            layer_type: Type of layer ('address', 'property', or 'parcel')
        """
        self.url = url
        self.layer_type = layer_type
        self.logger = logging.getLogger(f'FeatureLayer.{layer_type}')
        
    def query(self, where_clause: str, out_fields: str = '*', 
             return_geometry: bool = False, result_record_count: Optional[int] = None) -> Tuple[bool, Dict]:
        """Query the feature layer
        
        Args:
            where_clause: SQL where clause for filtering
            out_fields: Comma-separated list of fields to return
            return_geometry: Whether to return feature geometries
            result_record_count: Maximum number of records to return
            
        Returns:
            Tuple of (success, data)
        """
        params = {
            'where': where_clause,
            'outFields': out_fields,
            'returnGeometry': str(return_geometry).lower(),
            'f': 'json'
        }
        
        if result_record_count:
            params['resultRecordCount'] = result_record_count
            
        try:
            response = requests.get(f"{self.url}/query", params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if 'error' in data:
                self.logger.error(f"API error: {data['error']}")
                return False, data['error']
                
            if 'features' not in data:
                self.logger.warning("No features found in response")
                return False, {'message': 'No features found'}
                
            return True, data
            
        except requests.exceptions.Timeout:
            self.logger.error(f"Request timed out for query: {where_clause}")
            return False, {'message': 'Request timed out'}
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed: {str(e)}")
            return False, {'message': str(e)}
            
    def get_by_id(self, field_name: str, field_value: str) -> Tuple[bool, Dict]:
        """Get a single feature by ID field
        
        Args:
            field_name: Name of the ID field
            field_value: Value to match
            
        Returns:
            Tuple of (success, feature data)
        """
        # Escape single quotes in the value
        escaped_value = field_value.replace("'", "''")
        where_clause = f"{field_name}='{escaped_value}'"
        success, data = self.query(where_clause, result_record_count=1)
        
        if not success:
            return False, data
            
        features = data.get('features', [])
        if not features:
            return False, {'message': f'No feature found with {field_name}={field_value}'}
            
        return True, features[0]['attributes']
        
    def search(self, criteria: Dict[str, str], exact_match: bool = True) -> Tuple[bool, List[Dict]]:
        """Search features using multiple criteria
        
        Args:
            criteria: Dictionary of field names and values to match
            exact_match: Whether to require exact matches
            
        Returns:
            Tuple of (success, list of matching features)
        """
        conditions = []
        for field, value in criteria.items():
            if not value:  # Skip empty values
                continue
            # Escape special characters in values
            escaped_value = value.replace("'", "''").replace("%", "[%]").replace("\\", "\\\\")
            if exact_match:
                conditions.append(f"{field}='{escaped_value}'")
            else:
                conditions.append(f"UPPER({field}) LIKE '%{escaped_value.upper()}%'")
                
        where_clause = ' AND '.join(conditions) if conditions else '1=1'
        success, data = self.query(where_clause)
        
        if not success:
            return False, []
            
        return True, [feature['attributes'] for feature in data.get('features', [])]