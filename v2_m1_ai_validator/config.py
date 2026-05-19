"""
Configuration file for M1 AI Validator
Contains field definitions, validation rules, and settings
"""

# Required fields for all M1 entries
REQUIRED_FIELDS = ['lga_code', 'edit_code', 'comments']

# Field patterns
SPI_PATTERN = r'^([0-9]+\\[A-Z]{2}[0-9]+|[A-Z]{2}[0-9]+)$'
PROPERTY_PFI_PATTERN = r'^\d+$'
CREFNO_PATTERN = r'^[A-Za-z0-9\-\/]+$'

# M1 Field Definitions with enhanced validation
M1_FIELDS = {
    'lga_code': {'required': True, 'type': str, 'length': 3, 'pattern': r'^\d{3}$'},
    'new_sub': {'required': False, 'type': str, 'allowed_values': ['Y']},
    'property_pfi': {'required': False, 'type': str, 'pattern': r'^\d+$'},
    'parcel_pfi': {'required': False, 'type': str, 'pattern': r'^\d+$'},
    'address_pfi': {'required': False, 'type': str, 'pattern': r'^\d+$'},
    'spi': {'required': False, 'type': str, 'pattern': SPI_PATTERN},
    'plan_number': {'required': False, 'type': str, 'pattern': r'^[A-Z]{2}\d+$'},
    'lot_number': {'required': False, 'type': str},
    'base_propnum': {'required': False, 'type': str, 'pattern': r'^\d+$'},
    'propnum': {'required': False, 'type': str, 'pattern': r'^\d+$'},
    'crefno': {'required': False, 'type': str, 'pattern': r'^[A-Za-z0-9\-\/]+$'},
    'hsa_flag': {'required': False, 'type': str, 'allowed_values': ['Y']},
    'hsa_unit_id': {'required': False, 'type': str},
    'blg_unit_type': {'required': False, 'type': str},
    'house_number_1': {'required': False, 'type': str, 'pattern': r'^\d+[A-Za-z]?$'},
    'road_name': {'required': False, 'type': str},
    'road_type': {'required': False, 'type': str, 'pattern': r'^[A-Z]+$'},
    'locality_name': {'required': False, 'type': str},
    'distance_related_flag': {'required': False, 'type': str, 'allowed_values': ['Y', 'N']},
    'is_primary': {'required': False, 'type': str, 'allowed_values': ['Y', 'N']},
    'easting': {'required': False, 'type': str, 'pattern': r'^\d+(\.\d+)?$'},
    'northing': {'required': False, 'type': str, 'pattern': r'^\d+(\.\d+)?$'},
    'datum_proj': {'required': False, 'type': str, 'pattern': r'^EPSG:\d+$'},
    'outside_property': {'required': False, 'type': str, 'allowed_values': ['Y']},
    'edit_code': {'required': True, 'type': str, 'allowed_values': ['A', 'B', 'C', 'E', 'P', 'S', 'Z', 'R']}
}

# SPI Pattern validation
SPI_PATTERN = r'^([0-9]+\\[A-Z]{2}[0-9]+|[A-Z]{2}[0-9]+)$'

# Complete Edit Code Rules based on M1 documentation
EDIT_CODE_RULES = {
    'A': {  # Add multi-assessment
        'required_fields': ['lga_code', 'propnum'],
        'recommended_fields': ['spi', 'property_pfi'],
        'needs_spatial_ref': True,
        'description': 'Add a property to create or extend a multi-assessment',
        'common_patterns': ['multi-assessment', 'adding property', 'new multi'],
        'comment_requirements': {
            'must_include': ['propnum'],
            'should_include': ['spi'],
            'format_hints': {
                'propnum': 'numeric identifier',
                'spi': 'format like 1\\TP446069 or PC354544'
            }
        },
        'field_patterns': {
            'spi': SPI_PATTERN,
            'property_pfi': r'^\d+$',
            'propnum': r'^\d+$'
        },
        'field_dependencies': [],
        'numeric_ranges': {}
    },
    'B': {  # Remove from base property
        'required_fields': ['lga_code', 'property_pfi', 'base_propnum'],
        'needs_spatial_ref': False,
        'description': 'Remove a primary property from base or retire whole base',
        'common_patterns': ['remove from base', 'retire base', 'remove base'],
        'field_patterns': {},
        'field_dependencies': [],
        'numeric_ranges': {}
    },
    'C': {  # Update crefno
        'required_fields': ['lga_code', 'crefno'],
        'needs_spatial_ref': True,
        'description': 'Update parcel-based Council Reference number',
        'common_patterns': ['update crefno', 'council reference', 'change crefno'],
        'comment_requirements': {
            'must_include': ['crefno'],
            'format_hints': {
                'crefno': 'council reference number'
            }
        },
        'field_patterns': {
            'crefno': r'^[A-Za-z0-9\-\/]+$'  # Allow alphanumeric with hyphen and forward slash
        },
        'field_dependencies': [],
        'numeric_ranges': {}
    },
    'E': {  # Update property and address
        'required_fields': ['lga_code', 'propnum', 'road_name', 'road_type', 'locality_name'],
        'conditional_fields': ['house_number_1'],
        'needs_spatial_ref': True,
        'description': 'Update both property and address details',
        'common_patterns': ['update property and address', 'change property and address'],
        'comment_requirements': {
            'must_include': ['address', 'propnum'],
            'should_include': ['spi'],
            'format_hints': {
                'address': 'full address including house number, road name, road type and locality',
                'propnum': 'numeric identifier',
                'spi': 'format like 1\\TP446069 or PC354544'
            }
        },
        'field_patterns': {
            'spi': SPI_PATTERN,
            'property_pfi': r'^\d+$',
            'propnum': r'^\d+$',
            'house_number_1': r'^\d+[A-Za-z]?$',
            'road_type': r'^[A-Z]+$'
        },
        'field_dependencies': [
            {'if_field': 'house_number_1', 'then_field': 'road_name'},
            {'if_field': 'road_name', 'then_field': 'road_type'},
            {'if_field': 'road_name', 'then_field': 'locality_name'}
        ],
        'numeric_ranges': {}
    },
    'P': {  # Update property
        'required_fields': ['lga_code', 'propnum'],
        'needs_spatial_ref': True,
        'description': 'Update property details only',
        'common_patterns': ['update property', 'change property', 'modify property'],
        'field_patterns': {},
        'field_dependencies': [],
        'numeric_ranges': {}
    },
    'S': {  # Update address
        'required_fields': ['lga_code', 'road_name', 'road_type', 'locality_name'],
        'conditional_fields': {
            'urban_address': ['house_number_1'],
            'distance_based': ['distance_related_flag', 'easting', 'northing', 'datum_proj']
        },
        'needs_spatial_ref': True,
        'description': 'Update address details only',
        'common_patterns': ['update address', 'move address', 'change address', 'modify address'],
        'comment_requirements': {
            'must_include': ['address'],
            'should_include': ['spi', 'propnum'],
            'format_hints': {
                'address': 'full address including house number, road name, road type and locality',
                'spi': 'format like 1\\TP446069 or PC354544'
            }
        },
        'field_patterns': {
            'spi': SPI_PATTERN,
            'property_pfi': r'^\d+$',
            'propnum': r'^\d+$',
            'house_number_1': r'^\d+[A-Za-z]?$',
            'road_type': r'^[A-Z]+$'
        },
        'field_dependencies': [
            {'if_field': 'distance_related_flag', 'then_field': 'easting'},
            {'if_field': 'distance_related_flag', 'then_field': 'northing'},
            {'if_field': 'distance_related_flag', 'then_field': 'datum_proj'}
        ],
        'numeric_ranges': {
            'easting': {'min': 100000, 'max': 999999},
            'northing': {'min': 5700000, 'max': 5999999}
        }
    },
    'Z': {  # Remove secondary address
        'required_fields': ['lga_code'],
        'needs_spatial_ref': True,
        'description': 'Remove secondary address or downgrade distance-based to urban',
        'common_patterns': ['remove secondary', 'downgrade address', 'delete secondary'],
        'field_patterns': {},
        'field_dependencies': [],
        'numeric_ranges': {}
    },
    'R': {  # Remove from multi-assessment
        'required_fields': ['lga_code'],
        'needs_spatial_ref': True,
        'description': 'Remove property from multi-assessment',
        'common_patterns': ['remove from multi', 'retire multi', 'delete from multi'],
        'field_patterns': {},
        'field_dependencies': [],
        'numeric_ranges': {}
    }
}