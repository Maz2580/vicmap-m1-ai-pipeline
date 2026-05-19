"""
AI-Powered Comment Enhancement System for M1 Validation
Generates intelligent, consistent comments based on M1 data and edit codes
"""
import re
import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime

class AICommentEnhancer:
    """AI-powered comment generation and enhancement"""
    
    def __init__(self):
        self.logger = logging.getLogger('AICommentEnhancer')
        
        # Comment templates for different edit codes
        self.comment_templates = {
            'A': {
                'template': 'Adding property {propnum} to multi-assessment{spi_info}',
                'required_fields': ['propnum'],
                'optional_fields': ['spi', 'property_pfi'],
                'enhancements': ['multi-assessment', 'property addition']
            },
            'B': {
                'template': 'Removing property {propnum} from base property {base_propnum}',
                'required_fields': ['propnum', 'base_propnum'],
                'optional_fields': ['property_pfi'],
                'enhancements': ['base property', 'property removal']
            },
            'C': {
                'template': 'Updating crefno to {crefno} for parcel {spi}',
                'required_fields': ['crefno'],
                'optional_fields': ['spi', 'parcel_pfi'],
                'enhancements': ['council reference', 'parcel update']
            },
            'E': {
                'template': 'Updating property {propnum} and address {address_info}',
                'required_fields': ['propnum'],
                'optional_fields': ['house_number_1', 'road_name', 'road_type', 'locality_name', 'spi'],
                'enhancements': ['property and address', 'comprehensive update']
            },
            'P': {
                'template': 'Updating property details for {propnum}',
                'required_fields': ['propnum'],
                'optional_fields': ['spi', 'property_pfi'],
                'enhancements': ['property details', 'property update']
            },
            'S': {
                'template': 'Updating address {address_info}',
                'required_fields': ['road_name', 'road_type', 'locality_name'],
                'optional_fields': ['house_number_1', 'spi', 'property_pfi'],
                'enhancements': ['address update', 'location change']
            },
            'Z': {
                'template': 'Removing secondary address for property {propnum}',
                'required_fields': ['propnum'],
                'optional_fields': ['property_pfi'],
                'enhancements': ['secondary address', 'address removal']
            },
            'R': {
                'template': 'Removing property {propnum} from multi-assessment',
                'required_fields': ['propnum'],
                'optional_fields': ['property_pfi'],
                'enhancements': ['multi-assessment', 'property removal']
            }
        }
        
        # Common address patterns
        self.address_patterns = {
            'urban': '{house_number} {road_name} {road_type}, {locality_name}',
            'rural': '{house_number} {road_name} {road_type}, {locality_name} (distance-based)',
            'unit': 'Unit {unit_id} {house_number} {road_name} {road_type}, {locality_name}',
            'complex': '{complex_name} - {house_number} {road_name} {road_type}, {locality_name}'
        }
    
    def enhance_comment(self, record: Dict) -> str:
        """
        Generate or enhance comment for M1 record
        
        Args:
            record: M1 record data
            
        Returns:
            Enhanced comment string
        """
        edit_code = record.get('edit_code', '')
        if not edit_code:
            return "No edit code provided"
        
        template_info = self.comment_templates.get(edit_code)
        if not template_info:
            return f"Unknown edit code: {edit_code}"
        
        # Check if comment already exists and is good
        existing_comment = record.get('comments', '')
        if existing_comment and self._is_comment_adequate(existing_comment, edit_code, record):
            return existing_comment
        
        # Generate new comment
        comment = self._generate_comment(record, template_info)
        
        # Enhance with additional context
        comment = self._add_contextual_enhancements(comment, record)
        
        return comment
    
    def _generate_comment(self, record: Dict, template_info: Dict) -> str:
        """Generate comment using template"""
        template = template_info['template']
        comment = template
        
        # Replace placeholders
        for field in template_info['required_fields'] + template_info['optional_fields']:
            if field in record and record[field]:
                if field == 'spi_info' and record.get('spi'):
                    comment = comment.replace('{spi_info}', f' (SPI: {record["spi"]})')
                elif field == 'address_info':
                    address_info = self._format_address_info(record)
                    comment = comment.replace('{address_info}', address_info)
                else:
                    comment = comment.replace(f'{{{field}}}', str(record[field]))
        
        # Remove unused placeholders
        comment = re.sub(r'\{[^}]+\}', '', comment)
        
        # Clean up extra spaces
        comment = re.sub(r'\s+', ' ', comment).strip()
        
        return comment
    
    def _format_address_info(self, record: Dict) -> str:
        """Format address information for comment"""
        house_number = record.get('house_number_1', '')
        road_name = record.get('road_name', '')
        road_type = record.get('road_type', '')
        locality_name = record.get('locality_name', '')
        
        if not all([road_name, road_type, locality_name]):
            return "address details"
        
        # Determine address pattern
        if record.get('distance_related_flag') == 'Y':
            pattern = self.address_patterns['rural']
        elif record.get('complex_name'):
            pattern = self.address_patterns['complex']
        elif record.get('blg_unit_id_1'):
            pattern = self.address_patterns['unit']
        else:
            pattern = self.address_patterns['urban']
        
        address = pattern.format(
            house_number=house_number or '',
            road_name=road_name,
            road_type=road_type,
            locality_name=locality_name,
            unit_id=record.get('blg_unit_id_1', ''),
            complex_name=record.get('complex_name', '')
        )
        
        return address.strip()
    
    def _add_contextual_enhancements(self, comment: str, record: Dict) -> str:
        """Add contextual enhancements to comment"""
        enhancements = []
        
        # Add timestamp context
        if record.get('new_sub') == 'Y':
            enhancements.append("(new subdivision)")
        
        # Add distance-based context
        if record.get('distance_related_flag') == 'Y':
            enhancements.append("(rural address)")
        
        # Add multi-assessment context
        if record.get('prop_multi_assessment') == 'Y':
            enhancements.append("(multi-assessment property)")
        
        # Add complex site context
        if record.get('complex_name'):
            enhancements.append("(complex site)")
        
        # Add new road context
        if record.get('new_road') == 'Y':
            enhancements.append("(new road)")
        
        # Add outside property context
        if record.get('outside_property') == 'Y':
            enhancements.append("(outside property)")
        
        if enhancements:
            comment += f" - {' '.join(enhancements)}"
        
        return comment
    
    def _is_comment_adequate(self, comment: str, edit_code: str, record: Dict) -> bool:
        """Check if existing comment is adequate"""
        if not comment or len(comment.strip()) < 10:
            return False
        
        comment_lower = comment.lower()
        
        # Check for edit code specific requirements
        template_info = self.comment_templates.get(edit_code, {})
        required_enhancements = template_info.get('enhancements', [])
        
        # Check if comment contains required enhancement terms
        for enhancement in required_enhancements:
            if not any(term in comment_lower for term in enhancement.split()):
                return False
        
        # Check for key identifiers
        if edit_code in ['A', 'P', 'E', 'Z', 'R'] and record.get('propnum'):
            if str(record['propnum']) not in comment:
                return False
        
        if edit_code == 'B' and record.get('base_propnum'):
            if str(record['base_propnum']) not in comment:
                return False
        
        if edit_code == 'C' and record.get('crefno'):
            if str(record['crefno']) not in comment:
                return False
        
        return True
    
    def suggest_comment_improvements(self, comment: str, edit_code: str, record: Dict) -> List[str]:
        """
        Suggest improvements for existing comment
        
        Args:
            comment: Current comment
            edit_code: M1 edit code
            record: M1 record data
            
        Returns:
            List of improvement suggestions
        """
        suggestions = []
        
        if not comment:
            suggestions.append("Add a descriptive comment explaining the change")
            return suggestions
        
        comment_lower = comment.lower()
        
        # Check for missing key information
        if edit_code in ['A', 'P', 'E', 'Z', 'R'] and record.get('propnum'):
            if str(record['propnum']) not in comment:
                suggestions.append(f"Include property number {record['propnum']} in comment")
        
        if edit_code == 'B' and record.get('base_propnum'):
            if str(record['base_propnum']) not in comment:
                suggestions.append(f"Include base property number {record['base_propnum']} in comment")
        
        if edit_code == 'C' and record.get('crefno'):
            if str(record['crefno']) not in comment:
                suggestions.append(f"Include crefno {record['crefno']} in comment")
        
        # Check for edit code specific terms
        template_info = self.comment_templates.get(edit_code, {})
        required_enhancements = template_info.get('enhancements', [])
        
        for enhancement in required_enhancements:
            if not any(term in comment_lower for term in enhancement.split()):
                suggestions.append(f"Comment should mention '{enhancement}'")
        
        # Check for address information in address updates
        if edit_code in ['S', 'E'] and any(record.get(f) for f in ['house_number_1', 'road_name', 'locality_name']):
            if not any(term in comment_lower for term in ['address', 'road', 'street', 'location']):
                suggestions.append("Comment should describe the address change")
        
        # Check for distance-based address context
        if record.get('distance_related_flag') == 'Y' and not any(term in comment_lower for term in ['distance', 'rural', 'meters', 'metres']):
            suggestions.append("Comment should explain the distance-based nature of the address")
        
        return suggestions
    
    def generate_batch_comments(self, records: List[Dict]) -> Dict[str, str]:
        """
        Generate comments for a batch of M1 records
        
        Args:
            records: List of M1 records
            
        Returns:
            Dictionary mapping record index to enhanced comment
        """
        comments = {}
        
        for i, record in enumerate(records):
            try:
                comment = self.enhance_comment(record)
                comments[str(i)] = comment
            except Exception as e:
                self.logger.error(f"Error generating comment for record {i}: {e}")
                comments[str(i)] = f"Error generating comment: {str(e)}"
        
        return comments
    
    def analyze_comment_quality(self, comments: List[str]) -> Dict[str, any]:
        """
        Analyze comment quality across a batch
        
        Args:
            comments: List of comments to analyze
            
        Returns:
            Quality analysis results
        """
        analysis = {
            'total_comments': len(comments),
            'empty_comments': 0,
            'short_comments': 0,
            'average_length': 0,
            'quality_score': 0,
            'improvements_needed': []
        }
        
        if not comments:
            return analysis
        
        total_length = 0
        quality_issues = 0
        
        for comment in comments:
            if not comment or not comment.strip():
                analysis['empty_comments'] += 1
                quality_issues += 1
            elif len(comment.strip()) < 20:
                analysis['short_comments'] += 1
                quality_issues += 1
            else:
                total_length += len(comment.strip())
        
        analysis['average_length'] = total_length / max(1, len(comments) - analysis['empty_comments'])
        analysis['quality_score'] = max(0, 100 - (quality_issues / len(comments) * 100))
        
        if analysis['empty_comments'] > 0:
            analysis['improvements_needed'].append(f"{analysis['empty_comments']} empty comments need content")
        
        if analysis['short_comments'] > 0:
            analysis['improvements_needed'].append(f"{analysis['short_comments']} comments are too short")
        
        if analysis['quality_score'] < 70:
            analysis['improvements_needed'].append("Overall comment quality needs improvement")
        
        return analysis
