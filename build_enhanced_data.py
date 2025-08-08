#!/usr/bin/env python3
"""
Enhanced Data Processor for Crop Variety Dashboard
Combines all enhanced batch JSON files into a comprehensive CSV for the revamped dashboard
"""

import json
import csv
import os
import glob
from datetime import datetime
from typing import Dict, List, Any
import re

def extract_stress_types_from_queries(search_metadata: Dict) -> List[str]:
    """Extract stress tolerance types from search query results"""
    stress_types = set()
    
    if not search_metadata or 'query_results' not in search_metadata:
        return []
    
    for query_result in search_metadata['query_results']:
        if query_result.get('results_count', 0) > 0:
            query_text = query_result.get('query', '').lower()
            
            # Check for specific stress types
            if 'drought' in query_text or 'water stress' in query_text:
                stress_types.add('Drought')
            if 'heat' in query_text or 'temperature stress' in query_text:
                stress_types.add('Heat')
            if 'salt' in query_text or 'salinity' in query_text:
                stress_types.add('Salt')
            if 'flood' in query_text or 'water logging' in query_text:
                stress_types.add('Flood')
            if 'cold' in query_text or 'frost' in query_text:
                stress_types.add('Cold')
            if 'disease' in query_text or 'pathogen' in query_text:
                stress_types.add('Disease')
            if 'pest' in query_text or 'insect' in query_text:
                stress_types.add('Pest')
    
    return sorted(list(stress_types))

def determine_stress_tolerance(search_metadata: Dict, stress_types: List[str]) -> str:
    """Determine if variety is stress tolerant based on search results"""
    if not search_metadata or not stress_types:
        return 'No'
    
    # Check if any stress-related queries returned results
    total_stress_results = 0
    for query_result in search_metadata.get('query_results', []):
        query_text = query_result.get('query', '').lower()
        if any(stress in query_text for stress in ['drought', 'heat', 'salt', 'flood', 'cold']):
            total_stress_results += query_result.get('results_count', 0)
    
    return 'Yes' if total_stress_results > 0 else 'No'

def determine_evidence_quality(search_metadata: Dict) -> str:
    """Determine evidence quality based on search results"""
    if not search_metadata or 'query_results' not in search_metadata:
        return 'Low'
    
    total_results = sum(q.get('results_count', 0) for q in search_metadata['query_results'])
    successful_queries = len([q for q in search_metadata['query_results'] if q.get('results_count', 0) > 0])
    
    if total_results >= 50 and successful_queries >= 10:
        return 'High'
    elif total_results >= 20 and successful_queries >= 5:
        return 'Medium'
    else:
        return 'Low'

def process_single_variety(variety: Dict, debug_index: int = -1) -> Dict[str, Any]:
    """Process a single variety into dashboard format"""
    original_data = variety.get('original_data', {})
    search_metadata = variety.get('search_metadata', {})
    
    # Extract basic information
    variety_name = original_data.get('variety_name', original_data.get('crop_variety', 'Unknown Variety'))
    crop_type = original_data.get('crop_type', original_data.get('crop', 'Unknown'))
    year_of_release = original_data.get('extracted_year', original_data.get('year', ''))
    
    # Extract state information - handle comma-separated states
    states_raw = original_data.get('state_zone', original_data.get('state_zone_standardized', ''))
    if isinstance(states_raw, str):
        # Clean up state names and create abbreviated format
        states = [s.strip() for s in states_raw.split(',') if s.strip() and s.strip() != 'Not Specified']
        states_cleaned = []
        for state in states:
            # Convert full state names to abbreviations where possible
            state_mapping = {
                'Andhra Pradesh': 'AP', 'Arunachal Pradesh': 'AR', 'Assam': 'AS',
                'Bihar': 'BR', 'Chhattisgarh': 'CG', 'Goa': 'GA', 'Gujarat': 'GJ',
                'Haryana': 'HR', 'Himachal Pradesh': 'HP', 'Jharkhand': 'JH',
                'Karnataka': 'KA', 'Kerala': 'KL', 'Madhya Pradesh': 'MP',
                'Maharashtra': 'MH', 'Manipur': 'MN', 'Meghalaya': 'ML',
                'Mizoram': 'MZ', 'Nagaland': 'NL', 'Odisha': 'OR', 'Punjab': 'PB',
                'Rajasthan': 'RJ', 'Sikkim': 'SK', 'Tamil Nadu': 'TN',
                'Telangana': 'TG', 'Tripura': 'TR', 'Uttar Pradesh': 'UP',
                'Uttarakhand': 'UK', 'West Bengal': 'WB', 'Delhi': 'DL',
                'Puducherry': 'PY', 'Jammu and Kashmir': 'JK', 'Ladakh': 'LA'
            }
            states_cleaned.append(state_mapping.get(state, state[:3].upper()))
        states_acronyms = ', '.join(states_cleaned[:5])  # Limit to first 5 states
    else:
        states_acronyms = 'Unknown'
    
    # Extract stress information
    stress_types = extract_stress_types_from_queries(search_metadata)
    stress_tolerance = determine_stress_tolerance(search_metadata, stress_types)
    evidence_quality = determine_evidence_quality(search_metadata)
    
    # Extract seednet information from the seednet_fields object
    seednet_fields_data = variety.get('seednet_fields', {})
    seednet_available = bool(seednet_fields_data and seednet_fields_data.get('seednet_raw_variety_id'))
    seednet_match = 'YES' if seednet_available else 'NO'
    seednet_url = seednet_fields_data.get('seednet_raw_source_url', '')
    seednet_variety_id = seednet_fields_data.get('seednet_raw_variety_id', '')
    
    # Debug: Remove in production
    # if seednet_available:
    #     print(f"  DEBUG: Found Seednet match for {variety_name}: {seednet_variety_id} -> {seednet_url}")
    
    # Build seednet fields dictionary for the output
    seednet_fields = {}
    if seednet_available:
        # Extract all seednet fields, removing the 'seednet_raw_' prefix
        for key, value in seednet_fields_data.items():
            if key.startswith('seednet_raw_'):
                clean_key = key[len('seednet_raw_'):]
                seednet_fields[clean_key] = value
    
    # Extract search result summary
    total_search_results = 0
    if search_metadata and 'query_results' in search_metadata:
        total_search_results = sum(q.get('results_count', 0) for q in search_metadata['query_results'])
    
    # Build research data structure
    research_data = {
        'basic_info': {
            'crop': crop_type,
            'variety_name': variety_name,
            'data_source': original_data.get('data_source', 'enhanced_batch'),
            'year': year_of_release,
            'institution': original_data.get('institution', 'Not specified')
        },
        'search_results_summary': total_search_results,
        'stress_tolerance_evidence': {stress: 1 for stress in stress_types},
        'disease_pest_resistance': {
            'disease': {'count': len([q for q in search_metadata.get('query_results', []) if 'disease' in q.get('query', '').lower() and q.get('results_count', 0) > 0])},
            'pest': {'count': len([q for q in search_metadata.get('query_results', []) if 'pest' in q.get('query', '').lower() and q.get('results_count', 0) > 0])}
        },
        'field_trials': len([q for q in search_metadata.get('query_results', []) if 'trial' in q.get('query', '').lower() and q.get('results_count', 0) > 0]),
        'commercial_availability': len([q for q in search_metadata.get('query_results', []) if 'seed' in q.get('query', '').lower() and 'availability' in q.get('query', '').lower() and q.get('results_count', 0) > 0]),
        'enhancement_features': ['AI-Enhanced Search', 'Multi-query Analysis', 'Stress Tolerance Detection']
    }
    
    return {
        'variety_id': variety.get('variety_id', f"{crop_type}_{variety_name}_{year_of_release}"),
        'crop': crop_type,
        'variety_name': variety_name,
        'year_of_release': str(year_of_release) if year_of_release else '',
        'stress_tolerance': stress_tolerance,
        'key_attributes': ', '.join(stress_types) if stress_types else 'Standard variety',
        'states_acronyms': states_acronyms,
        'seasons': original_data.get('season', original_data.get('crop_season', 'Unknown')),
        'days_to_maturity': original_data.get('maturity_days', original_data.get('maturity_group', 'Unknown')),
        'evidence_quality': evidence_quality,
        'stress_types': stress_types,
        'seednet_match': seednet_match,
        'seednet_available': seednet_available,
        'seednet_url': seednet_url,
        'seednet_variety_id': seednet_variety_id,
        'seednet_fields': seednet_fields,
        'research_data': research_data,
        'search_metadata': search_metadata
    }

def load_enhanced_batches(data_dir: str) -> List[Dict]:
    """Load all enhanced batch JSON files"""
    all_varieties = []
    
    # Find all enhanced batch files
    pattern = os.path.join(data_dir, 'enhanced_batch_*.json')
    batch_files = sorted(glob.glob(pattern))
    
    print(f"Found {len(batch_files)} enhanced batch files")
    
    for batch_file in batch_files:
        print(f"Loading {os.path.basename(batch_file)}...")
        try:
            with open(batch_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # Replace NaN with null for proper JSON parsing
                content = content.replace('NaN', 'null')
                batch_data = json.loads(content)
                if isinstance(batch_data, list):
                    all_varieties.extend(batch_data)
                    print(f"  Loaded {len(batch_data)} varieties")
                else:
                    print(f"  Warning: Expected list, got {type(batch_data)}")
        except Exception as e:
            print(f"  Error loading {batch_file}: {e}")
    
    print(f"Total varieties loaded: {len(all_varieties)}")
    return all_varieties

def write_csv(varieties: List[Dict], output_file: str):
    """Write processed varieties to CSV"""
    if not varieties:
        print("No varieties to write!")
        return
    
    # Define CSV columns
    csv_columns = [
        'variety_id', 'crop', 'variety_name', 'year_of_release', 
        'stress_tolerance', 'key_attributes', 'states_acronyms', 
        'seasons', 'days_to_maturity', 'evidence_quality',
        'stress_types_list', 'seednet_match', 'seednet_url',
        'seednet_variety_id', 'search_results_total',
        'institution', 'data_source'
    ]
    
    print(f"Writing {len(varieties)} varieties to {output_file}")
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
        writer.writeheader()
        
        for variety in varieties:
            # Flatten some fields for CSV
            row = {
                'variety_id': variety['variety_id'],
                'crop': variety['crop'],
                'variety_name': variety['variety_name'],
                'year_of_release': variety['year_of_release'],
                'stress_tolerance': variety['stress_tolerance'],
                'key_attributes': variety['key_attributes'],
                'states_acronyms': variety['states_acronyms'],
                'seasons': variety['seasons'],
                'days_to_maturity': variety['days_to_maturity'],
                'evidence_quality': variety['evidence_quality'],
                'stress_types_list': '|'.join(variety['stress_types']),
                'seednet_match': variety['seednet_match'],
                'seednet_url': variety['seednet_url'],
                'seednet_variety_id': variety['seednet_variety_id'],
                'search_results_total': variety['research_data']['search_results_summary'],
                'institution': variety['research_data']['basic_info'].get('institution', ''),
                'data_source': variety['research_data']['basic_info'].get('data_source', '')
            }
            writer.writerow(row)

def write_json(varieties: List[Dict], output_file: str):
    """Write complete processed varieties to JSON for the JavaScript to use"""
    print(f"Writing complete data to {output_file}")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(varieties, f, indent=2, ensure_ascii=False, default=str)

def main():
    """Main processing function"""
    # Paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, '..', 'enhanced_data')
    output_csv = os.path.join(script_dir, 'varieties_compiled_enhanced.csv')
    output_json = os.path.join(script_dir, 'varieties_complete.json')
    
    print("Enhanced Data Processor for Crop Variety Dashboard")
    print("=" * 60)
    
    # Load all enhanced batch files
    all_varieties = load_enhanced_batches(data_dir)
    
    if not all_varieties:
        print("No varieties found! Exiting.")
        return
    
    # Process varieties
    print("\nProcessing varieties...")
    processed_varieties = []
    
    for i, variety in enumerate(all_varieties):
        try:
            processed = process_single_variety(variety, i)
            processed_varieties.append(processed)
            
            if (i + 1) % 100 == 0:
                print(f"  Processed {i + 1}/{len(all_varieties)} varieties")
                
        except Exception as e:
            print(f"  Error processing variety {i}: {e}")
    
    print(f"Successfully processed {len(processed_varieties)} varieties")
    
    # Write outputs
    print("\nWriting output files...")
    write_csv(processed_varieties, output_csv)
    write_json(processed_varieties, output_json)
    
    # Generate statistics
    print("\nStatistics:")
    print(f"  Total varieties: {len(processed_varieties)}")
    print(f"  Stress tolerant: {len([v for v in processed_varieties if v['stress_tolerance'] == 'Yes'])}")
    print(f"  With Seednet data: {len([v for v in processed_varieties if v['seednet_available']])}")
    print(f"  High evidence: {len([v for v in processed_varieties if v['evidence_quality'] == 'High'])}")
    print(f"  Unique crops: {len(set(v['crop'] for v in processed_varieties))}")
    
    # Timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\nProcessing completed at: {timestamp}")
    
    print(f"\nOutput files created:")
    print(f"  CSV: {output_csv}")
    print(f"  JSON: {output_json}")

if __name__ == "__main__":
    main()
