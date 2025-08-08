#!/usr/bin/env python3
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT.parent / 'enhanced_data'
OUT_CSV = ROOT / 'varieties_compiled.csv'

BATCH_FILES = [
    'enhanced_batch_0001.json',
    'enhanced_batch_0002.json',
    'enhanced_batch_0003.json',
    'enhanced_batch_0004.json',
    'enhanced_batch_0005.json',
    'enhanced_batch_0006.json',
    'enhanced_batch_0007.json',
]

FIELDS = [
    'Seed_Name', 'Crop_Type', 'All_States', 'Primary_State', 'Year_of_Release',
    'Stressors_Broadly_Defined', 'In_Depth_Stress_Tolerance_Notes',
    'Breeder_Origin_Institution', 'Crop_Value_Chain', 'Crop_Season',
    'Is_Stresstolerant', 'Variety', 'notificationDate', 'averageYield',
    'maturityDays', 'seednet_url'
]

def extract_seasons(text: str) -> str:
    if not text:
        return ''
    t = text.lower()
    seasons = []
    for s in ('kharif','rabi','summer','winter','monsoon'):
        if s in t:
            seasons.append(s.capitalize())
    return ', '.join(seasons)

def process_item(v: dict) -> dict:
    seednet_url = v.get('seednet_raw_source_url') or (
        f"https://seednet.gov.in/SeedVarieties/ssrsVarietydetail.aspx?varietycd={v.get('seednet_raw_variety_id')}"
        if v.get('seednet_raw_variety_id') else ''
    )
    crop = v.get('seednet_raw_Crop Name') or (v.get('original_data') or {}).get('crop') or (v.get('original_data') or {}).get('crop_type') or ''
    variety_name = v.get('seednet_raw_Variety Name') or (v.get('original_data') or {}).get('variety_name') or (v.get('original_data') or {}).get('crop_variety') or ''
    year = v.get('seednet_raw_Year of Release') or (v.get('original_data') or {}).get('year') or (v.get('original_data') or {}).get('extracted_year') or ''
    rec_states = v.get('seednet_raw_Recommended States') or ''
    # build stress evidence
    results = ((v.get('search_metadata') or {}).get('query_results')) or []
    stress_map = {'Drought':0,'Heat':0,'Salt':0,'Flood':0,'Cold':0}
    disease = 0; pest = 0
    for r in results:
        q = (r.get('query') or '').lower(); c = int(r.get('results_count') or 0)
        if 'drought' in q: stress_map['Drought'] += c
        if 'heat' in q or 'temperature' in q: stress_map['Heat'] += c
        if 'salt' in q or 'salin' in q: stress_map['Salt'] += c
        if 'flood' in q or 'waterlogging' in q or 'submergence' in q: stress_map['Flood'] += c
        if 'cold' in q or 'frost' in q: stress_map['Cold'] += c
        if 'disease' in q: disease += c
        if 'pest' in q or 'insect' in q or 'borer' in q: pest += c
    stress_types = [k for k,vv in stress_map.items() if vv>0]
    notes = ''
    if v.get('analysis_result') and v['analysis_result'].get('variety_analysis'):
        notes = v['analysis_result']['variety_analysis'].get('overall_assessment') or ''
    seasons = extract_seasons(v.get('seednet_raw_Adaptation and recommended ecology') or '')
    return {
        'Seed_Name': variety_name or 'Unknown Variety',
        'Crop_Type': crop or 'Unknown',
        'All_States': rec_states,
        'Primary_State': (rec_states.split(',')[0].strip() if rec_states else ''),
        'Year_of_Release': str(year) if year is not None else '',
        'Stressors_Broadly_Defined': ', '.join(stress_types) if stress_types else 'Not specified',
        'In_Depth_Stress_Tolerance_Notes': notes or 'No detailed analysis available',
        'Breeder_Origin_Institution': v.get('seednet_raw_Institution Responsible for developing Breeder Seed') or 'Not specified',
        'Crop_Value_Chain': v.get('seednet_raw_Group Name') or 'Not specified',
        'Crop_Season': seasons or 'Not specified',
        'Is_Stresstolerant': 'Yes' if stress_types else 'Unknown',
        'Variety': variety_name or 'Unknown',
        'notificationDate': v.get('seednet_raw_Notification Date') or 'Not specified',
        'averageYield': v.get('seednet_raw_Average Yield (Kg/Ha)') or 'Not specified',
        'maturityDays': v.get('seednet_raw_Maturity (in days)') or 'Not specified',
        'seednet_url': seednet_url,
    }

def main():
    rows = []
    for fname in BATCH_FILES:
        path = DATA_DIR / fname
        if not path.exists():
            continue
        with path.open('r', encoding='utf-8') as f:
            data = json.load(f)
        for item in data:
            rows.append(process_item(item))

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f'Wrote {len(rows)} rows to {OUT_CSV}')

if __name__ == '__main__':
    main()


