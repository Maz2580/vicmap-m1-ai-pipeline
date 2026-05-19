"""
Test script to verify VicMap Feature Layer access and data retrieval.
Set LGA_CODE in your .env to your council's Victorian LGA code before running.
"""
import os
import requests
import json
import logging
from urllib.parse import urlencode

# LGA filter for queries below. Set LGA_CODE in .env (e.g. '346' for Greater
# Shepparton, '300' for Alpine). Default empty so adopters configure explicitly.
LGA_CODE = os.getenv('LGA_CODE', '')

# Setup logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Feature Layer endpoints
ENDPOINTS = {
    'address': 'https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/arcgis/rest/services/Vicmap_Address/FeatureServer/0',
    'property': 'https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/arcgis/rest/services/Vicmap_Property/FeatureServer/0',
    'parcel': 'https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/arcgis/rest/services/Vicmap_Parcel/FeatureServer/0'
}

def test_endpoint(name: str, url: str):
    """Test a single endpoint's accessibility and data retrieval"""
    logger.info(f"\nTesting {name} endpoint...")
    
    # First, test basic endpoint access
    try:
        # Get endpoint metadata
        params = {'f': 'json'}
        response = requests.get(url, params=params)
        response.raise_for_status()
        metadata = response.json()
        
        logger.info(f"✓ Successfully accessed {name} endpoint")
        logger.info(f"Layer name: {metadata.get('name', 'N/A')}")
        logger.info(f"Number of fields: {len(metadata.get('fields', []))}")
        
        # Display field information
        logger.info("\nField schema:")
        for field in metadata.get('fields', []):
            field_name = field.get('name', 'N/A')
            field_type = field.get('type', 'N/A')
            field_alias = field.get('alias', 'N/A')
            logger.info(f"  {field_name:<30} | {field_type:<15} | {field_alias}")
        
        # Try to get some actual data scoped to the configured LGA.
        # Adjust query based on layer.
        where_clause = None
        if 'PARCEL_MP' in metadata.get('name', ''):
            where_clause = f"parcel_lga_code='{LGA_CODE}'"
        elif 'PROPERTY_MP' in metadata.get('name', ''):
            where_clause = f"prop_lga_code='{LGA_CODE}'"
        else:  # Address
            where_clause = f"lga_code='{LGA_CODE}'"
            
        query_params = {
            'where': where_clause,
            'outFields': '*',
            'returnGeometry': 'false',
            'f': 'json'
        }
        
        # Print the query URL and parameters
        query_url = f"{url}/query"
        logger.info(f"Query URL: {query_url}")
        logger.info(f"Query parameters: {query_params}")
        logger.info(f"Full URL with parameters: {query_url}?{urlencode(query_params)}")
        
        response = requests.get(query_url, params=query_params)
        response.raise_for_status()
        data = response.json()
        
        # Print raw response for debugging
        logger.info("Raw Response:")
        logger.info(json.dumps(data, indent=2))
        
        if 'features' in data:
            record_count = len(data['features'])
            logger.info(f"✓ Successfully retrieved {record_count} records")
            
            # Show sample of first record
            if record_count > 0:
                sample_record = data['features'][0]['attributes']
                logger.info("\nSample record fields:")
                for key, value in sample_record.items():
                    if value is not None:  # Only show non-null values
                        logger.info(f"  {key}: {value}")
        else:
            logger.warning("No features found in the response")
            if 'error' in data:
                logger.error(f"Error details: {data['error']}")
            
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Error accessing {name} endpoint: {str(e)}")
    except Exception as e:
        logger.error(f"✗ Unexpected error testing {name} endpoint: {str(e)}")

def main():
    """Main test function"""
    logger.info("Starting VicMap Feature Layer Tests")
    logger.info("=" * 50)
    
    # Test just the parcel endpoint for debugging
    test_endpoint('parcel', ENDPOINTS['parcel'])
    logger.info("-" * 50)
    
    logger.info("\nTests completed!")

if __name__ == "__main__":
    main()