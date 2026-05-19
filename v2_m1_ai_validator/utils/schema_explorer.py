"""
VicMap Schema Explorer - Understand the data structure
"""
import os
import requests
import json
from typing import Dict, List, Optional
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class VicMapSchemaExplorer:
    """Explore and document VicMap layer schemas"""
    
    ENDPOINTS = {
        'address': 'https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/arcgis/rest/services/Vicmap_Address/FeatureServer/0',
        'property': 'https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/arcgis/rest/services/Vicmap_Property/FeatureServer/0',
        'parcel': 'https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/arcgis/rest/services/Vicmap_Parcel/FeatureServer/0'
    }
    
    # Override via the LGA_CODE env var. See https://www.land.vic.gov.au/maps-and-spatial/
    # for the list of Victorian LGA codes. Default left blank so adopters set it explicitly.
    LGA_CODE = os.getenv('LGA_CODE', '')
    
    def get_layer_metadata(self, layer_name: str) -> Optional[Dict]:
        """Get metadata about a layer"""
        url = self.ENDPOINTS.get(layer_name)
        if not url:
            logger.error(f"Unknown layer: {layer_name}")
            return None
        
        try:
            response = requests.get(url, params={'f': 'json'}, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error getting metadata: {e}")
            return None
    
    def print_schema(self, layer_name: str):
        """Print the schema for a layer"""
        logger.info(f"\n{'='*80}")
        logger.info(f"Schema for {layer_name.upper()} layer")
        logger.info(f"{'='*80}\n")
        
        metadata = self.get_layer_metadata(layer_name)
        if not metadata:
            return
        
        logger.info(f"Layer Name: {metadata.get('name')}")
        logger.info(f"Description: {metadata.get('description', 'N/A')}\n")
        
        fields = metadata.get('fields', [])
        logger.info(f"Total Fields: {len(fields)}\n")
        
        # Group fields by type
        by_type = {}
        for field in fields:
            field_type = field.get('type', 'unknown')
            if field_type not in by_type:
                by_type[field_type] = []
            by_type[field_type].append(field)
        
        logger.info("Fields by Type:")
        for field_type, type_fields in sorted(by_type.items()):
            logger.info(f"\n  {field_type.upper()} ({len(type_fields)} fields):")
            for field in type_fields[:5]:  # Show first 5 of each type
                logger.info(f"    - {field['name']:<40} | {field.get('alias', 'N/A')}")
            if len(type_fields) > 5:
                logger.info(f"    ... and {len(type_fields) - 5} more")
        
        # Show key fields for M1 validation
        logger.info(f"\n{'-'*80}")
        logger.info("Key Fields for M1 Validation:")
        logger.info(f"{'-'*80}\n")
        
        key_field_patterns = {
            'property': ['prop_pfi', 'prop_propnum', 'prop_lga_code', 'prop_status'],
            'parcel': ['parcel_pfi', 'parcel_spi', 'parcel_lga_code', 'parcel_status', 'parcel_road'],
            'address': ['address_pfi', 'house_nbr_1', 'road_name', 'road_type', 'locality_name', 'lga_code']
        }
        
        patterns = key_field_patterns.get(layer_name, [])
        for field in fields:
            field_name = field['name']
            if any(pattern in field_name.lower() for pattern in patterns):
                logger.info(f"  {field_name:<40} | {field.get('type', 'N/A'):<15} | {field.get('alias', 'N/A')}")
    
    def get_sample_data(self, layer_name: str, limit: int = 3) -> List[Dict]:
        """Get sample data from a layer"""
        url = self.ENDPOINTS.get(layer_name)
        if not url:
            return []
        
        # Determine LGA field name based on layer
        lga_field = {
            'property': 'prop_lga_code',
            'parcel': 'parcel_lga_code',
            'address': 'lga_code'
        }.get(layer_name, 'lga_code')
        
        params = {
            'where': f"{lga_field}='{self.LGA_CODE}'",
            'outFields': '*',
            'returnGeometry': 'false',
            'f': 'json',
            'resultRecordCount': limit
        }
        
        try:
            response = requests.get(f"{url}/query", params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            features = data.get('features', [])
            return [f['attributes'] for f in features]
        except Exception as e:
            logger.error(f"Error getting sample data: {e}")
            return []
    
    def print_sample_data(self, layer_name: str):
        """Print sample data from a layer"""
        logger.info(f"\n{'='*80}")
        logger.info(f"Sample Data from {layer_name.upper()} layer (Greater Shepparton)")
        logger.info(f"{'='*80}\n")
        
        samples = self.get_sample_data(layer_name)
        
        if not samples:
            logger.warning("No sample data available")
            return
        
        for idx, sample in enumerate(samples, 1):
            logger.info(f"Record {idx}:")
            # Show only non-null values
            for key, value in sorted(sample.items()):
                if value is not None and value != '':
                    logger.info(f"  {key:<40} = {value}")
            logger.info("")
    
    def analyze_layer(self, layer_name: str):
        """Complete analysis of a layer"""
        self.print_schema(layer_name)
        self.print_sample_data(layer_name)
        
        # Get statistics
        logger.info(f"\n{'='*80}")
        logger.info(f"Statistics for {layer_name.upper()} (Greater Shepparton)")
        logger.info(f"{'='*80}\n")
        
        self.get_layer_statistics(layer_name)
    
    def get_layer_statistics(self, layer_name: str):
        """Get statistics about the layer"""
        url = self.ENDPOINTS.get(layer_name)
        if not url:
            return
        
        lga_field = {
            'property': 'prop_lga_code',
            'parcel': 'parcel_lga_code',
            'address': 'lga_code'
        }.get(layer_name, 'lga_code')
        
        params = {
            'where': f"{lga_field}='{self.LGA_CODE}'",
            'returnCountOnly': 'true',
            'f': 'json'
        }
        
        try:
            response = requests.get(f"{url}/query", params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            count = data.get('count', 0)
            logger.info(f"Total records in Greater Shepparton: {count:,}")
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
    
    def find_field(self, search_term: str):
        """Search for fields across all layers"""
        logger.info(f"\n{'='*80}")
        logger.info(f"Searching for fields matching: '{search_term}'")
        logger.info(f"{'='*80}\n")
        
        for layer_name in self.ENDPOINTS.keys():
            metadata = self.get_layer_metadata(layer_name)
            if not metadata:
                continue
            
            matching_fields = [
                f for f in metadata.get('fields', [])
                if search_term.lower() in f['name'].lower() or 
                   search_term.lower() in f.get('alias', '').lower()
            ]
            
            if matching_fields:
                logger.info(f"\n{layer_name.upper()} layer:")
                for field in matching_fields:
                    logger.info(f"  {field['name']:<40} | {field.get('alias', 'N/A')}")


def main():
    """Run schema exploration"""
    explorer = VicMapSchemaExplorer()
    
    print("\n" + "="*80)
    print("VicMap Schema Explorer for Greater Shepparton")
    print("="*80)
    
    # Analyze each layer
    for layer in ['property', 'parcel', 'address']:
        explorer.analyze_layer(layer)
        print("\n" + "="*80 + "\n")
    
    # Search for specific fields
    print("\nSearching for key M1 fields:")
    for term in ['pfi', 'propnum', 'spi', 'status']:
        explorer.find_field(term)


if __name__ == '__main__':
    main()