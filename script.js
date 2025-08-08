// Enhanced Dashboard JavaScript with Dual-View Modal System
(function(){
  const JSON_PATH = 'varieties_complete.json';
  let ALL_ITEMS = [];
  let FILTERED = [];
  let SORT = { key: null, dir: 'asc' };
  let VISIBLE = { crop:true,variety:true,year:true,stress:true,attributes:true,states:true,seasons:true,maturity:true,evidence:true };
  let PAGE = { size: 25, index: 1 };

  document.addEventListener('DOMContentLoaded', async () => {
    // Title/Header adjustments
    document.title = "India's Seed Varieties Dashboard";
    const headerH1 = document.querySelector('.header h1');
    if (headerH1) headerH1.textContent = "India's Seed Varieties Dashboard";

    await loadEnhancedData();
    populateFilters();
    updateStats();
    filterData();
    setupEvents();

    // Unify button sizes if present
    const reloadBtn = document.getElementById('btn-reload');
    const aboutBtn = document.getElementById('btn-about');
    if (reloadBtn){ reloadBtn.classList.add('btn','btn-primary'); }
    if (aboutBtn){ aboutBtn.classList.add('btn','btn-outline'); }

    // Adjust table hint copy if present
    const hints = Array.from(document.querySelectorAll('div,span,p')).filter(el=>/Click any row to view/i.test(el.textContent||''));
    if (hints[0]) hints[0].textContent = 'Click any row to view sources and research/evidence';
  });

  async function loadEnhancedData(){
    try {
      const res = await fetch(JSON_PATH);
      if (!res.ok) throw new Error('Enhanced data not found');
      ALL_ITEMS = await res.json();
      FILTERED = [...ALL_ITEMS];
      updateCountsLabel();
      setLastUpdated();
      const totalEl = document.getElementById('total-varieties');
      if (totalEl) totalEl.textContent = String(ALL_ITEMS.length);
    } catch(e){
      console.error('Failed to load enhanced data', e);
      ALL_ITEMS = [];
      FILTERED = [];
      updateCountsLabel();
    }
  }

  function setupEvents(){
    byId('search-box') && byId('search-box').addEventListener('input', filterData);
    byId('crop-filter') && byId('crop-filter').addEventListener('change', filterData);
    byId('state-filter') && byId('state-filter').addEventListener('change', filterData);
    byId('stress-filter') && byId('stress-filter').addEventListener('change', filterData);
    byId('evidence-filter') && byId('evidence-filter').addEventListener('change', filterData);
    byId('stress-type-filter') && byId('stress-type-filter').addEventListener('change', filterData);
    byId('btn-reset') && byId('btn-reset').addEventListener('click', () => { resetFilters(); filterData(); });
    byId('btn-reload') && byId('btn-reload').addEventListener('click', async () => { await loadEnhancedData(); populateFilters(); filterData(); updateStats(); });
    byId('btn-about') && byId('btn-about').addEventListener('click', showAboutModal);

    document.querySelectorAll('#varieties-table thead th.sortable').forEach(th => {
      th.addEventListener('click', ()=> onSort(th.dataset.key));
      th.addEventListener('keydown', (e)=>{ if (e.key==='Enter'||e.key===' '){ e.preventDefault(); onSort(th.dataset.key);} });
    });
    const btnCols = byId('btn-columns'); const menuCols = byId('columns-menu');
    if (btnCols && menuCols){
      btnCols.addEventListener('click', ()=> menuCols.classList.toggle('hidden'));
      menuCols.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.addEventListener('change', ()=>{ VISIBLE[cb.dataset.col]=cb.checked; renderTable(); }));
      document.addEventListener('click', (e)=>{ if (!menuCols.contains(e.target) && e.target!==btnCols) menuCols.classList.add('hidden'); });
    }

    byId('page-size') && byId('page-size').addEventListener('change', (e)=>{ PAGE.size=parseInt(e.target.value,10); PAGE.index=1; renderTable(); });
    byId('page-prev') && byId('page-prev').addEventListener('click', ()=>{ if (PAGE.index>1){ PAGE.index--; renderTable(); } });
    byId('page-next') && byId('page-next').addEventListener('click', ()=>{ const totalPages=Math.max(1,Math.ceil(FILTERED.length/PAGE.size)); if (PAGE.index<totalPages){ PAGE.index++; renderTable(); } });
    byId('btn-export-csv') && byId('btn-export-csv').addEventListener('click', exportCSV);

    const closeBtn = document.getElementsByClassName('close')[0];
    if (closeBtn){ closeBtn.onclick = () => byId('variety-modal').style.display='none'; }
    window.addEventListener('click',(e)=>{ if (e.target===byId('variety-modal')) byId('variety-modal').style.display='none'; });
  }

  function showAboutModal(){
    const modalBody = byId('modal-body');
    if (!modalBody) return;
    modalBody.innerHTML = `
      <div class="space-y-4">
        <h2 class="text-2xl font-bold text-dark-green">India's Seed Varieties Dashboard</h2>
        <p class="text-gray-700">Stress-Tolerant Seed Variety Identification by Precision Development.</p>

        <div class="p-4 rounded-lg border bg-light-accent border-primary-green/30">
          <h3 class="font-semibold text-dark-green mb-2">Official Seednet Data</h3>
          <p class="text-gray-700 text-sm">We directly reference the Government of India's Seednet portal for official variety notifications and specifications.</p>
          <a href="https://seednet.gov.in/" target="_blank" rel="noopener" class="inline-block mt-2 text-primary-green underline">Visit Seednet Portal</a>
        </div>

        <div class="p-4 rounded-lg border bg-white border-primary-green/20">
          <h3 class="font-semibold text-dark-green mb-2">Research Data & Methods</h3>
          <p class="text-gray-700 text-sm">Since 2008, we aggregate publicly available information on seed varieties, link to available Seednet information, and perform targeted web searches. We then summarize evidence for stress tolerance, disease/pest resistance, field trials, and availability using an LLM enhancement layer.</p>
          <div class="text-xs text-gray-600 mt-2">AI summarization powered by Google Gemini 2.5 Flash</div>
        </div>

        <div class="mt-2">
          <h3 class="font-semibold text-dark-green mb-2">Features</h3>
          <ul class="list-disc list-inside text-sm text-gray-700 space-y-1">
            <li>Dual-view system for official vs research data</li>
            <li>Advanced stress tolerance filtering</li>
            <li>Direct Seednet portal integration</li>
            <li>Evidence quality assessment</li>
            <li>Comprehensive search across ${ALL_ITEMS.length} varieties</li>
          </ul>
        </div>
      </div>`;
    byId('variety-modal').style.display='block';
  }

  function populateFilters(){
    // Crop single-select values
    const cropSelect = byId('crop-filter');
    if (cropSelect){
      cropSelect.multiple = false;
      fillOptions(cropSelect, [''].concat(unique(ALL_ITEMS.map(i=>i.crop))));
    }

    // State single-select with full names
    const stateSelect = byId('state-filter');
    if (stateSelect){
      stateSelect.multiple = false;
      const statesFull = unique(ALL_ITEMS.flatMap(i => Array.isArray(i.states_full)? i.states_full : []));
      fillOptions(stateSelect, [''].concat(statesFull));
    }

    // Stress tolerance yes/no (keep as-is if present)
    const stressSel = byId('stress-filter'); if (stressSel){ stressSel.multiple = false; }

    // Stress types multi-select (keep)
    const allStressTypes = unique(ALL_ITEMS.flatMap(i => i.stress_types || []));
    const stressTypeSelect = byId('stress-type-filter');
    if (stressTypeSelect) {
      stressTypeSelect.multiple = true;
      stressTypeSelect.size = Math.min(6, Math.max(3, allStressTypes.length));
      stressTypeSelect.innerHTML = allStressTypes.map(type => `<option value="${type}">${type}</option>`).join('');
    }
  }

  function resetFilters(){
    ['crop-filter','state-filter','stress-filter','evidence-filter','stress-type-filter'].forEach(id => {
      const el = byId(id);
      if (!el) return;
      if (el.multiple){ Array.from(el.options).forEach(opt => opt.selected = false); }
      else { el.value = ''; }
    });
    const sb = byId('search-box'); if (sb) sb.value = '';
  }

  function filterData(){
    const q = (byId('search-box')?.value||'').toLowerCase();
    const cropSel = valueOrEmpty('crop-filter');
    const stateSel = valueOrEmpty('state-filter');
    const stressSel = getMulti('stress-filter');
    const evSel = getMulti('evidence-filter');
    const stressTypesSel = getMulti('stress-type-filter');

    FILTERED = ALL_ITEMS.filter(i => {
      const matchesQ = !q || i.variety_name.toLowerCase().includes(q) || i.crop.toLowerCase().includes(q) || (i.key_attributes||'').toLowerCase().includes(q);
      const matchesCrop = !cropSel || i.crop === cropSel;
      const itemStatesFull = Array.isArray(i.states_full) ? i.states_full : [];
      const matchesState = !stateSel || itemStatesFull.includes(stateSel);
      const matchesStress = stressSel.length===0 || stressSel.includes(i.stress_tolerance);
      const matchesEv = evSel.length===0 || evSel.includes(i.evidence_quality);
      const matchesStressTypes = stressTypesSel.length===0 || (i.stress_types && i.stress_types.some(t => stressTypesSel.includes(t)));
      return matchesQ && matchesCrop && matchesState && matchesStress && matchesEv && matchesStressTypes;
    });
    PAGE.index = 1;
    updateCountsLabel();
    renderTable();
    updateStats();
  }

  function renderTable(){
    const tbody = byId('varieties-tbody');
    if (!tbody) return;
    let data = [...FILTERED];
    if (SORT.key){ const dir=SORT.dir==='asc'?1:-1; data.sort((a,b)=> compareByKey(a,b,SORT.key)*dir); }
    const totalPages = Math.max(1, Math.ceil(data.length / PAGE.size));
    if (PAGE.index>totalPages) PAGE.index=totalPages;
    const start=(PAGE.index-1)*PAGE.size; const pageItems=data.slice(start, start+PAGE.size);
    const pageInfo = byId('page-info'); if (pageInfo) pageInfo.textContent = `Page ${PAGE.index} / ${totalPages}`;

    if (!pageItems.length){
      tbody.innerHTML = `<tr><td colspan="9" class="px-6 py-12 text-center text-gray-500"><div class="text-4xl mb-4">🌱</div><p class="text-xl font-medium">No varieties found</p><p class="text-sm">Try adjusting your filters or search terms</p></td></tr>`;
      return;
    }

    tbody.innerHTML = pageItems.map((item, idx) => {
      const realIdx = start + idx;
      const statesFullText = (Array.isArray(item.states_full) ? item.states_full.join(', ') : (item.states_acronyms||''));
      const stressTypes = (item.stress_types || []).slice(0, 3).map(type => `<span class="inline-block bg-amber-100 text-amber-800 text-xs px-1 py-0.5 rounded mr-1">${type}</span>`).join('');
      return `
      <tr class="hover:bg-gray-50 transition-colors cursor-pointer variety-row" data-idx="${realIdx}">
        ${VISIBLE.crop?`<td class="px-4 py-3">${item.crop}</td>`:''}
        ${VISIBLE.variety?`<td class="px-4 py-3"><div class="font-medium">${item.variety_name}</div></td>`:''}
        ${VISIBLE.year?`<td class="px-4 py-3">${item.year_of_release}</td>`:''}
        ${VISIBLE.stress?`<td class="px-4 py-3"><span class="stress-${item.stress_tolerance.toLowerCase()}">${item.stress_tolerance}</span></td>`:''}
        ${VISIBLE.attributes?`<td class="px-4 py-3 text-sm"><div>${item.key_attributes}</div><div class="mt-1">${stressTypes}</div></td>`:''}
        ${VISIBLE.states?`<td class="px-4 py-3 text-sm">${statesFullText}</td>`:''}
        ${VISIBLE.seasons?`<td class="px-4 py-3 text-sm">${item.seasons}</td>`:''}
        ${VISIBLE.maturity?`<td class="px-4 py-3 text-sm">${item.days_to_maturity}</td>`:''}
        ${VISIBLE.evidence?`<td class="px-4 py-3"><span class="evidence-${item.evidence_quality.toLowerCase()}">${item.evidence_quality}</span></td>`:''}
      </tr>`;
    }).join('');

    Array.from(tbody.querySelectorAll('.variety-row')).forEach(tr=>{
      tr.addEventListener('click', ()=>{
        const idx = Number(tr.getAttribute('data-idx'));
        showDualViewModal(idx);
      });
    });
  }

  function onSort(key){
    SORT.key===key ? (SORT.dir = SORT.dir==='asc'?'desc':'asc') : (SORT.key=key,SORT.dir='asc');
    renderTable();
  }
  function compareByKey(a,b,key){
    const map={crop:'crop',variety:'variety_name',year:'year_of_release',stress:'stress_tolerance',attributes:'key_attributes',states:'states_acronyms',seasons:'seasons',maturity:'days_to_maturity',evidence:'evidence_quality'};
    const ka=map[key]; const va=(a[ka]||'').toString().toLowerCase(); const vb=(b[ka]||'').toString().toLowerCase();
    if(!isNaN(parseFloat(va))&&!isNaN(parseFloat(vb))) return parseFloat(va)-parseFloat(vb);
    return va.localeCompare(vb);
  }

  function showDualViewModal(index){
    const item = FILTERED[index];
    const modalBody = byId('modal-body'); 
    if(!item||!modalBody) return;
    const seednetEnabled = item.seednet_available && item.seednet_url;
    const seednetBtnClass = seednetEnabled ? 'tab-seednet enabled' : 'tab-seednet disabled';

    modalBody.innerHTML = `
      <div class="mb-4">
        <h2 class="text-2xl font-bold text-dark-green">${item.variety_name}</h2>
        <div class="text-sm text-gray-600">${item.crop} • ${item.year_of_release}</div>
      </div>
      <div class="tabs mb-4">
        <button id="tab-seednet" class="tab-btn ${seednetBtnClass}" ${!seednetEnabled ? 'disabled' : ''}>
          <span class="flex items-center gap-2">Seednet Details</span>
          <span class="tab-badge">OFFICIAL SOURCE</span>
        </button>
        <button id="tab-research" class="tab-btn tab-research">
          <span class="flex items-center gap-2">Research Details</span>
          <span class="tab-badge">EVIDENCE SUMMARY</span>
        </button>
      </div>
      <div id="panel-seednet" class="tab-panel ${seednetEnabled ? 'active' : ''}">
        ${seednetEnabled ? renderSeednetPanel(item) : '<div class="text-center py-8 text-gray-500"><div class="text-4xl mb-2">🏛️</div><p class="font-medium">No Official Seednet Data Available</p><p class="text-sm">This variety has not been found in the official Seednet portal database.</p></div>'}
      </div>
      <div id="panel-research" class="tab-panel ${seednetEnabled ? '' : 'active'}">
        ${renderResearchPanel(item)}
      </div>
      <div class="mt-6 pt-4 border-t border-gray-200 text-xs text-gray-600">
        <div class="flex flex-wrap gap-2">
          ${seednetEnabled ? '<span class="inline-block bg-light-accent text-dark-green px-2 py-1 rounded">Seednet available</span>' : ''}
          <span class="inline-block bg-white border border-primary-green/30 text-dark-green px-2 py-1 rounded">AI summarization: Gemini 2.5 Flash</span>
        </div>
      </div>`;

    const tabSeed = byId('tab-seednet'); const tabRes = byId('tab-research');
    const panSeed = byId('panel-seednet'); const panRes = byId('panel-research');
    if (seednetEnabled && tabSeed) tabSeed.addEventListener('click',()=>{ panSeed.classList.add('active'); panRes.classList.remove('active'); });
    if (tabRes) tabRes.addEventListener('click',()=>{ panRes.classList.add('active'); panSeed.classList.remove('active'); });
    byId('variety-modal').style.display='block';
  }

  function renderSeednetPanel(item) {
    const seednet = item.seednet_fields || {};
    const constructSeednetUrl = (varietyId) => `https://seednet.gov.in/SeedVarieties/ssrsVarietydetail.aspx?varietycd=${varietyId}`;
    return `
      <div class="bg-green-50 rounded-lg p-4 mb-4 border border-green-200">
        <h3 class="font-semibold text-dark-green mb-3">Official Government Data</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <h4 class="font-medium text-dark-green mb-2">Basic Information</h4>
            <div class="text-sm space-y-1">
              <div><span class="text-gray-600">Variety Name:</span> ${seednet['Variety Name'] || item.variety_name}</div>
              <div><span class="text-gray-600">Notification Number:</span> ${seednet['Notification Number'] || 'Not specified'}</div>
              <div><span class="text-gray-600">Notification Date:</span> ${seednet['Notification Date'] || 'Not specified'}</div>
              <div><span class="text-gray-600">Year of Release:</span> ${seednet['Year of Release'] || item.year_of_release}</div>
            </div>
          </div>
          <div>
            <h4 class="font-medium text-dark-green mb-2">Development Details</h4>
            <div class="text-sm space-y-1">
              <div><span class="text-gray-600">Institution:</span> ${seednet['Institution Responsible for developing Breeder Seed'] || 'Not specified'}</div>
              <div><span class="text-gray-600">Parentage:</span> ${seednet['Parentage'] || 'Not specified'}</div>
              <div><span class="text-gray-600">Maturity:</span> ${seednet['Maturity (in days)'] || 'Not specified'}</div>
              <div><span class="text-gray-600">Average Yield:</span> ${seednet['Average Yield (Kg/Ha)'] || 'Not specified'}</div>
            </div>
          </div>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          <div>
            <div class="mb-2"><span class="text-gray-600">Morphological Characteristics:</span><br>${seednet['General Morphological Characteristics'] || 'Not specified'}</div>
            <div><span class="text-gray-600">Disease Reaction:</span><br>${seednet['Reaction to Major Diseases'] || 'Not specified'}</div>
          </div>
          <div>
            <div class="mb-2"><span class="text-gray-600">Pest Reaction:</span><br>${seednet['Reaction to Major Pests'] || 'Not specified'}</div>
            <div><span class="text-gray-600">Stress Reaction:</span><br>${seednet['Reaction to Stress'] || 'Not specified'}</div>
          </div>
        </div>
        <div class="flex gap-2 mt-4">
          <a href="${item.seednet_url || constructSeednetUrl(item.seednet_variety_id)}" target="_blank" rel="noopener" 
             class="inline-flex items-center gap-2 btn btn-primary">
            VIEW ON SEEDNET PORTAL
          </a>
        </div>
      </div>`;
  }

  function renderResearchPanel(item) {
    const research = item.research_data || {};
    const ar = research.analysis_result || {};
    const stressEvidence = research.stress_tolerance_evidence || {};
    const stressTypes = Object.keys(stressEvidence).map(type => `<span class="inline-block bg-amber-100 text-amber-800 text-xs px-2 py-1 rounded mr-1 mb-1">${type}</span>`).join('');

    // Derive a simple quantitative score if not provided
    const baseScore = (research.search_results_summary || 0) + (research.field_trials||0)*5 + (research.commercial_availability||0)*2;
    const quantitativeScore = ar.quantitative_score ?? baseScore;
    const qualityLabel = ar.quality_label || (research.evidence_quality || 'Medium');

    const evidenceBullets = Array.isArray(ar.evidence_bullets)? ar.evidence_bullets : [];
    const topSources = Array.isArray(ar.top_sources)? ar.top_sources : [];
    const summaryText = ar.overall_summary || ar.summary || '';

    return `
      <div class="rounded-lg p-4 mb-4 border bg-white border-primary-green/20">
        <h3 class="font-semibold text-dark-green mb-2">Research Evidence</h3>
        ${summaryText ? `<p class="text-sm text-gray-700 mb-3">${summaryText}</p>` : ''}

        <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3 text-sm">
          <div class="bg-white p-3 rounded border">
            <div class="text-gray-600">Evidence Quality</div>
            <div class="mt-1 font-bold"><span class="evidence-${String(qualityLabel).toLowerCase()}">${qualityLabel}</span></div>
          </div>
          <div class="bg-white p-3 rounded border">
            <div class="text-gray-600">Quantitative Score</div>
            <div class="mt-1 text-lg font-bold text-primary-green">${quantitativeScore}</div>
          </div>
          <div class="bg-white p-3 rounded border">
            <div class="text-gray-600">Total Research Results</div>
            <div class="mt-1 text-lg font-bold text-primary-green">${research.search_results_summary || 0}</div>
          </div>
        </div>

        <div class="mb-3">
          <h4 class="font-medium text-dark-green mb-1">Stress Tolerance Evidence</h4>
          <div>${stressTypes || '<span class="text-gray-500 text-sm">No stress tolerance evidence detected</span>'}</div>
        </div>

        ${evidenceBullets.length ? `<div class="mb-3"><h4 class="font-medium text-dark-green mb-1">Key Evidence</h4><ul class="list-disc list-inside text-sm text-gray-700 space-y-1">${evidenceBullets.map(b=>`<li>${b}</li>`).join('')}</ul></div>` : ''}

        ${topSources.length ? `<div class="mb-3"><h4 class="font-medium text-dark-green mb-1">Top Sources</h4><ul class="list-disc list-inside text-sm text-gray-700 space-y-1">${topSources.map(s=>`<li>${typeof s==='string'?s:(s.title||'Source')} ${s.url?`- <a class='text-primary-green underline' href='${s.url}' target='_blank' rel='noopener'>link</a>`:''}</li>`).join('')}</ul></div>` : ''}

        <div class="mt-2">
          <h4 class="font-medium text-dark-green mb-1">Quick Research Links</h4>
          <div class="flex flex-wrap gap-2">
            ${createResearchLink(`${item.variety_name} ${item.crop} stress tolerance`)}
            ${createResearchLink(`${item.variety_name} ${item.crop} drought tolerance`)}
            ${createResearchLink(`${item.variety_name} ${item.crop} field trials`)}
            ${createResearchLink(`${item.variety_name} ${item.crop} seed availability`)}
          </div>
        </div>
      </div>`;
  }

  function createResearchLink(query){
    const u = `https://www.google.com/search?q=${encodeURIComponent(query)}`;
    return `<a href="${u}" target="_blank" rel="noopener" class="inline-flex items-center gap-1 text-primary-green underline text-sm">${query}</a>`;
  }

  function exportCSV(){
    const rows = FILTERED.map(i=>({
      crop: i.crop,
      variety_name: i.variety_name,
      year_of_release: i.year_of_release,
      stress_tolerance: i.stress_tolerance,
      key_attributes: i.key_attributes,
      states: Array.isArray(i.states_full)? i.states_full.join('; ') : (i.states_acronyms||''),
      seasons: i.seasons,
      days_to_maturity: i.days_to_maturity,
      evidence_quality: i.evidence_quality,
      seednet_available: i.seednet_available ? 'Yes' : 'No',
      seednet_url: i.seednet_url || '',
      total_research_results: i.research_data?.search_results_summary || 0
    }));
    const header = Object.keys(rows[0]||{});
    const csv=[header.join(','),...rows.map(r=>header.map(h=>`"${String(r[h]||'').replace(/"/g,'""')}"`).join(',')).join('\n')];
    const blob=new Blob([csv],{type:'text/csv;charset=utf-8;'}); const url=URL.createObjectURL(blob);
    const a=document.createElement('a'); a.href=url; a.download='enhanced_varieties_export.csv'; a.click(); URL.revokeObjectURL(url);
  }

  function updateStats(){
    const st = document.getElementById('stress-tolerant');
    const he = document.getElementById('high-evidence');
    const tc = document.getElementById('total-crops');
    if (st) st.textContent = String(ALL_ITEMS.filter(i=>i.stress_tolerance==='Yes').length);
    if (he) he.textContent = String(ALL_ITEMS.filter(i=>i.evidence_quality==='High').length);
    if (tc) tc.textContent = String(new Set(ALL_ITEMS.map(i=>i.crop)).size);
  }
  function updateCountsLabel(){ const fc = document.getElementById('filtered-count'); const tc = document.getElementById('total-count'); if (fc) fc.textContent=String(FILTERED.length||0); if (tc) tc.textContent=String(ALL_ITEMS.length||0); }
  function setLastUpdated(){ const d=new Date(); const el=document.getElementById('last-updated'); if (el) el.textContent=d.toISOString().split('T')[0]; }

  function fillOptions(selectEl, values){ selectEl.innerHTML = values.map(v=>`<option value="${v}">${v||'All'}</option>`).join(''); }
  function getMulti(id){ const el=document.getElementById(id); if (!el) return []; return el.multiple ? Array.from(el.selectedOptions||[]).map(o=>o.value) : (el.value? [el.value]: []); }
  function valueOrEmpty(id){ const el=document.getElementById(id); return el && !el.multiple ? el.value : ''; }
  function unique(a){ return Array.from(new Set(a)).filter(Boolean).sort(); }
  function byId(id){ return document.getElementById(id); }
})();
