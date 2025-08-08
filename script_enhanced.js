// Enhanced Dashboard JavaScript with Dual-View Modal System
(function(){
  const JSON_PATH = 'varieties_complete.json';
  let ALL_ITEMS = [];
  let FILTERED = [];
  let SORT = { key: null, dir: 'asc' };
  let VISIBLE = { crop:true,variety:true,year:true,stress:true,attributes:true,states:true,seasons:true,maturity:true,evidence:true };
  let PAGE = { size: 25, index: 1 };

  document.addEventListener('DOMContentLoaded', async () => {
    await loadEnhancedData();
    populateFilters();
    updateStats();
    filterData();
    setupEvents();
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
    byId('search-box').addEventListener('input', filterData);
    byId('crop-filter').addEventListener('change', filterData);
    byId('state-filter').addEventListener('change', filterData);
    byId('stress-filter').addEventListener('change', filterData);
    byId('evidence-filter').addEventListener('change', filterData);
    byId('stress-type-filter').addEventListener('change', filterData);
    byId('btn-reset').addEventListener('click', () => { resetFilters(); filterData(); });
    byId('btn-reload').addEventListener('click', async () => { await loadEnhancedData(); populateFilters(); filterData(); updateStats(); });
    byId('btn-about').addEventListener('click', showAboutModal);

    document.querySelectorAll('#varieties-table thead th.sortable').forEach(th => {
      th.addEventListener('click', ()=> onSort(th.dataset.key));
      th.addEventListener('keydown', (e)=>{ if (e.key==='Enter'||e.key===' '){ e.preventDefault(); onSort(th.dataset.key);} });
    });
    const btnCols = byId('btn-columns'); const menuCols = byId('columns-menu');
    btnCols.addEventListener('click', ()=> menuCols.classList.toggle('hidden'));
    menuCols.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.addEventListener('change', ()=>{ VISIBLE[cb.dataset.col]=cb.checked; renderTable(); }));
    document.addEventListener('click', (e)=>{ if (!menuCols.contains(e.target) && e.target!==btnCols) menuCols.classList.add('hidden'); });

    byId('page-size').addEventListener('change', (e)=>{ PAGE.size=parseInt(e.target.value,10); PAGE.index=1; renderTable(); });
    byId('page-prev').addEventListener('click', ()=>{ if (PAGE.index>1){ PAGE.index--; renderTable(); } });
    byId('page-next').addEventListener('click', ()=>{ const totalPages=Math.max(1,Math.ceil(FILTERED.length/PAGE.size)); if (PAGE.index<totalPages){ PAGE.index++; renderTable(); } });
    byId('btn-export-csv').addEventListener('click', exportCSV);

    const closeBtn = document.getElementsByClassName('close')[0];
    closeBtn.onclick = () => byId('variety-modal').style.display='none';
    window.addEventListener('click',(e)=>{ if (e.target===byId('variety-modal')) byId('variety-modal').style.display='none'; });
  }

  function showAboutModal(){
    const modalBody = byId('modal-body');
    modalBody.innerHTML = `
      <div class="space-y-4">
        <h2 class="text-2xl font-bold text-dark-green">PxD Stress-Tolerant Seed Varieties Dashboard</h2>
        <p class="text-gray-700">This enhanced dashboard presents a comprehensive dual-source view of crop varieties with both official government data from Seednet and AI-enhanced research insights.</p>
        
        <div class="bg-green-50 p-4 rounded-lg border-l-4 border-green-400">
          <h3 class="font-semibold text-green-800 mb-2">Official Seednet Data</h3>
          <p class="text-green-700 text-sm">Direct links to government portal with verified variety information, notification details, and agricultural specifications.</p>
        </div>
        
        <div class="bg-blue-50 p-4 rounded-lg border-l-4 border-blue-400">
          <h3 class="font-semibold text-blue-800 mb-2">AI-Enhanced Research</h3>
          <p class="text-blue-700 text-sm">Advanced search analysis across multiple databases to identify stress tolerance evidence, field trials, and commercial availability.</p>
        </div>
        
        <div class="mt-4">
          <h3 class="font-semibold text-dark-green mb-2">Key Features</h3>
          <ul class="list-disc list-inside text-sm text-gray-700 space-y-1">
            <li>Dual-view system for official vs research data</li>
            <li>Advanced stress tolerance filtering</li>
            <li>Direct Seednet portal integration</li>
            <li>Evidence quality assessment</li>
            <li>Comprehensive search across ${ALL_ITEMS.length} varieties</li>
          </ul>
        </div>
        
        <div class="text-xs text-gray-500 mt-4">
          Enhanced with AI-powered research aggregation • Data sources: Seednet Portal + Research Databases
        </div>
      </div>`;
    byId('variety-modal').style.display='block';
  }

  function populateFilters(){
    fillMulti('crop-filter', unique(ALL_ITEMS.map(i=>i.crop)));
    
    // Use full state names from states_full array, with fallback to acronyms
    const stateMapping = {
      'AP': 'Andhra Pradesh', 'AR': 'Arunachal Pradesh', 'AS': 'Assam', 'BR': 'Bihar', 'CG': 'Chhattisgarh',
      'GA': 'Goa', 'GJ': 'Gujarat', 'HR': 'Haryana', 'HP': 'Himachal Pradesh', 'JH': 'Jharkhand',
      'KA': 'Karnataka', 'KL': 'Kerala', 'MP': 'Madhya Pradesh', 'MH': 'Maharashtra', 'MN': 'Manipur',
      'ML': 'Meghalaya', 'MZ': 'Mizoram', 'NL': 'Nagaland', 'OR': 'Odisha', 'PB': 'Punjab', 'RJ': 'Rajasthan',
      'SK': 'Sikkim', 'TN': 'Tamil Nadu', 'TG': 'Telangana', 'TR': 'Tripura', 'UP': 'Uttar Pradesh',
      'UK': 'Uttarakhand', 'WB': 'West Bengal', 'DL': 'Delhi', 'PY': 'Puducherry', 'JK': 'Jammu and Kashmir',
      'LA': 'Ladakh'
    };
    
    const statesSet = new Set();
    ALL_ITEMS.forEach(item => {
      // Try states_full first
      if (item.states_full && Array.isArray(item.states_full)) {
        item.states_full.forEach(state => {
          if (state && state !== 'Unknown' && state !== 'Not Specified') {
            statesSet.add(state);
          }
        });
      } else if (item.states_acronyms) {
        // Fallback to converting acronyms to full names
        const stateStr = String(item.states_acronyms);
        stateStr.split(',').map(s=>s.trim()).forEach(acronym => {
          if (acronym && acronym !== 'Unknown' && acronym.length <= 3) {
            const fullName = stateMapping[acronym] || acronym;
            statesSet.add(fullName);
          }
        });
      }
    });
    
    fillMulti('state-filter', Array.from(statesSet).sort());
    
    // Populate stress type filter from actual data
    const allStressTypes = unique(ALL_ITEMS.flatMap(i => i.stress_types || []));
    fillMulti('stress-type-filter', allStressTypes);
    
    // Setup stress type search functionality
    const stressSearch = byId('stress-search');
    if (stressSearch) {
      stressSearch.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        const options = byId('stress-type-filter').querySelectorAll('option');
        options.forEach(option => {
          const matches = option.textContent.toLowerCase().includes(query);
          option.style.display = matches ? 'block' : 'none';
        });
      });
    }
  }

  function resetFilters(){
    ['crop-filter','state-filter','stress-filter','evidence-filter','stress-type-filter'].forEach(id => {
      const el = byId(id);
      if (!el) return;
      Array.from(el.options).forEach(opt => opt.selected = false);
    });
    const sb = byId('search-box'); if (sb) sb.value = '';
  }

  function filterData(){
    const q = (byId('search-box')?.value||'').toLowerCase();
    const cropsSel = getMulti('crop-filter');
    const statesSel = getMulti('state-filter');
    const stressSel = getMulti('stress-filter');
    const evSel = getMulti('evidence-filter');
    const stressTypesSel = getMulti('stress-type-filter');

    FILTERED = ALL_ITEMS.filter(i => {
      const matchesQ = !q || i.variety_name.toLowerCase().includes(q) || i.crop.toLowerCase().includes(q) || (i.key_attributes||'').toLowerCase().includes(q);
      const matchesCrop = cropsSel.length===0 || cropsSel.includes(i.crop);
      
      // Handle both full state names and acronyms
      const stateMapping = {
        'AP': 'Andhra Pradesh', 'AR': 'Arunachal Pradesh', 'AS': 'Assam', 'BR': 'Bihar', 'CG': 'Chhattisgarh',
        'GA': 'Goa', 'GJ': 'Gujarat', 'HR': 'Haryana', 'HP': 'Himachal Pradesh', 'JH': 'Jharkhand',
        'KA': 'Karnataka', 'KL': 'Kerala', 'MP': 'Madhya Pradesh', 'MH': 'Maharashtra', 'MN': 'Manipur',
        'ML': 'Meghalaya', 'MZ': 'Mizoram', 'NL': 'Nagaland', 'OR': 'Odisha', 'PB': 'Punjab', 'RJ': 'Rajasthan',
        'SK': 'Sikkim', 'TN': 'Tamil Nadu', 'TG': 'Telangana', 'TR': 'Tripura', 'UP': 'Uttar Pradesh',
        'UK': 'Uttarakhand', 'WB': 'West Bengal', 'DL': 'Delhi', 'PY': 'Puducherry', 'JK': 'Jammu and Kashmir',
        'LA': 'Ladakh'
      };
      
      let itemStateNames = [];
      if (i.states_full && Array.isArray(i.states_full)) {
        itemStateNames = i.states_full.filter(s => s && s !== 'Unknown' && s !== 'Not Specified');
      } else if (i.states_acronyms) {
        const itemStateAcronyms = String(i.states_acronyms).split(',').map(s=>s.trim()).filter(Boolean);
        itemStateNames = itemStateAcronyms.map(acronym => stateMapping[acronym] || acronym);
      }
      
      const matchesState = statesSel.length===0 || statesSel.some(s=> itemStateNames.includes(s));
      
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
      const seednetBadge = item.seednet_available ? '<span class="inline-block bg-green-100 text-green-800 text-xs px-2 py-1 rounded mr-1">Seednet ✓</span>' : '';
      const stressTypes = (item.stress_types || []).slice(0, 3).map(type => `<span class="inline-block bg-amber-100 text-amber-800 text-xs px-1 py-0.5 rounded mr-1">${type}</span>`).join('');
      
      return `
      <tr class="hover:bg-gray-50 transition-colors cursor-pointer variety-row" data-idx="${realIdx}">
        ${VISIBLE.crop?`<td class="px-4 py-3">${item.crop}</td>`:''}
        ${VISIBLE.variety?`<td class="px-4 py-3"><div class="font-medium">${item.variety_name}</div><div class="text-xs text-gray-500">${seednetBadge}Evidence: ${item.evidence_quality}</div></td>`:''}
        ${VISIBLE.year?`<td class="px-4 py-3">${item.year_of_release}</td>`:''}
        ${VISIBLE.stress?`<td class="px-4 py-3"><span class="stress-${item.stress_tolerance.toLowerCase()}">${item.stress_tolerance}</span></td>`:''}
        ${VISIBLE.attributes?`<td class="px-4 py-3 text-sm"><div>${item.key_attributes}</div><div class="mt-1">${stressTypes}</div></td>`:''}
        ${VISIBLE.states?`<td class="px-4 py-3 text-sm">${item.states_acronyms}</td>`:''}
        ${VISIBLE.seasons?`<td class="px-4 py-3 text-sm">${item.seasons}</td>`:''}
        ${VISIBLE.maturity?`<td class="px-4 py-3 text-sm">${item.days_to_maturity}</td>`:''}
        ${VISIBLE.evidence?`<td class="px-4 py-3"><span class="evidence-${item.evidence_quality.toLowerCase()}">${item.evidence_quality}</span></td>`:''}
      </tr>`;
    }).join('');

    // Add click handlers to table rows
    Array.from(tbody.querySelectorAll('.variety-row')).forEach(tr=>{
      tr.addEventListener('click', ()=>{
        const idx = Number(tr.getAttribute('data-idx'));
        showDualViewModal(idx);
      });
    });
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
        <div class="text-sm text-gray-600 flex items-center gap-2">
          <span>${item.crop} • ${item.year_of_release}</span>
          ${seednetEnabled ? '<span class="bg-green-100 text-green-800 text-xs px-2 py-1 rounded">Seednet Available</span>' : '<span class="bg-gray-100 text-gray-600 text-xs px-2 py-1 rounded">No Seednet Data</span>'}
          <span class="bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded">AI Enhanced</span>
        </div>
      </div>
      
      <div class="tabs mb-4">
        <button id="tab-seednet" class="tab-btn ${seednetBtnClass}" ${!seednetEnabled ? 'disabled' : ''}>
          <span class="flex items-center gap-2">
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            Seednet Details
          </span>
          <span class="tab-badge">OFFICIAL SOURCE</span>
        </button>
        <button id="tab-research" class="tab-btn tab-research">
          <span class="flex items-center gap-2">
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M13 6a3 3 0 11-6 0 3 3 0 016 0zM18 8a2 2 0 11-4 0 2 2 0 014 0zM14 15a4 4 0 00-8 0v3h8v-3z"/></svg>
            Research Details
          </span>
          <span class="tab-badge">AI-ENHANCED RESEARCH</span>
        </button>
      </div>
      
      <div id="panel-seednet" class="tab-panel ${seednetEnabled ? 'active' : ''}">
        ${seednetEnabled ? renderSeednetPanel(item) : '<div class="text-center py-8 text-gray-500"><div class="text-4xl mb-2">🏛️</div><p class="font-medium">No Official Seednet Data Available</p><p class="text-sm">This variety has not been found in the official Seednet portal database.</p></div>'}
      </div>
      
      <div id="panel-research" class="tab-panel ${seednetEnabled ? '' : 'active'}">
        ${renderResearchPanel(item)}
      </div>
      
      <div class="mt-6 pt-4 border-t border-gray-200">
        <h3 class="font-semibold text-dark-green mb-2">Genetic Marker Databases</h3>
        <div class="flex flex-wrap gap-2 text-sm">
          <a href="https://www.ncbi.nlm.nih.gov/" target="_blank" class="text-primary-green hover:underline">NCBI GenBank</a>
          <a href="https://gramene.org/" target="_blank" class="text-primary-green hover:underline">Gramene</a>
          <a href="https://plantgdb.org/" target="_blank" class="text-primary-green hover:underline">PlantGDB</a>
          <a href="https://www.ipk-gatersleben.de/" target="_blank" class="text-primary-green hover:underline">IPK Gatersleben</a>
        </div>
      </div>
    `;
    
    // Setup tab switching
    const tabSeed = byId('tab-seednet'); const tabRes = byId('tab-research');
    const panSeed = byId('panel-seednet'); const panRes = byId('panel-research');
    
    if (seednetEnabled && tabSeed) {
      tabSeed.addEventListener('click', () => {
        panSeed.classList.add('active'); panRes.classList.remove('active');
        tabSeed.classList.add('active'); tabRes.classList.remove('active');
      });
    }
    
    if (tabRes) {
      tabRes.addEventListener('click', () => {
        panRes.classList.add('active'); panSeed.classList.remove('active');
        tabRes.classList.add('active'); tabSeed.classList.remove('active');
      });
    }
    
    byId('variety-modal').style.display='block';
  }

  function renderSeednetPanel(item) {
    const seednet = item.seednet_fields || {};
    const constructSeednetUrl = (varietyId) => {
      return `https://seednet.gov.in/SeedVarieties/ssrsVarietydetail.aspx?varietycd=${varietyId}`;
    };
    
    return `
      <div class="bg-green-50 rounded-lg p-4 mb-4 border border-green-200">
        <div class="flex items-center gap-2 mb-3">
          <svg class="w-5 h-5 text-green-600" fill="currentColor" viewBox="0 0 20 20"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
          <h3 class="font-semibold text-green-800">Official Government Data</h3>
        </div>
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <h4 class="font-medium text-green-700 mb-2">Basic Information</h4>
            <div class="space-y-1 text-sm">
              <div><span class="text-gray-600">Variety Name:</span> ${seednet['Variety Name'] || item.variety_name}</div>
              <div><span class="text-gray-600">Notification Number:</span> ${seednet['Notification Number'] || 'Not specified'}</div>
              <div><span class="text-gray-600">Notification Date:</span> ${seednet['Notification Date'] || 'Not specified'}</div>
              <div><span class="text-gray-600">Year of Release:</span> ${seednet['Year of Release'] || item.year_of_release}</div>
            </div>
          </div>
          
          <div>
            <h4 class="font-medium text-green-700 mb-2">Development Details</h4>
            <div class="space-y-1 text-sm">
              <div><span class="text-gray-600">Institution:</span> ${seednet['Institution Responsible for developing Breeder Seed'] || 'Not specified'}</div>
              <div><span class="text-gray-600">Parentage:</span> ${seednet['Parentage'] || 'Not specified'}</div>
              <div><span class="text-gray-600">Maturity:</span> ${seednet['Maturity (in days)'] || 'Not specified'}</div>
              <div><span class="text-gray-600">Average Yield:</span> ${seednet['Average Yield (Kg/Ha)'] || 'Not specified'}</div>
            </div>
          </div>
        </div>
        
        <div class="mb-4">
          <h4 class="font-medium text-green-700 mb-2">Agricultural Characteristics</h4>
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
        </div>
        
        <div class="flex gap-2">
          <a href="${item.seednet_url || constructSeednetUrl(item.seednet_variety_id)}" target="_blank" rel="noopener" 
             class="inline-flex items-center gap-2 bg-green-700 hover:bg-green-800 text-white px-4 py-2 rounded-lg font-medium transition-colors">
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M11 3a1 1 0 100 2h2.586l-6.293 6.293a1 1 0 101.414 1.414L15 6.414V9a1 1 0 102 0V4a1 1 0 00-1-1h-5z"/><path d="M5 5a2 2 0 00-2 2v8a2 2 0 002 2h8a2 2 0 002-2v-1a1 1 0 10-2 0v1H5V7h1a1 1 0 000-2H5z"/></svg>
            VIEW ON SEEDNET PORTAL
          </a>
        </div>
      </div>
    `;
  }

  function renderResearchPanel(item) {
    const research = item.research_data || {};
    const stressEvidence = research.stress_tolerance_evidence || {};
    const stressTypes = Object.keys(stressEvidence).map(type => 
      `<span class="inline-block bg-amber-100 text-amber-800 text-xs px-2 py-1 rounded mr-1 mb-1">${type}</span>`
    ).join('');
    
    const enhancementFeatures = (research.enhancement_features || []).map(feature => 
      `<span class="inline-block bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded mr-1 mb-1">${feature}</span>`
    ).join('');

    return `
      <div class="bg-blue-50 rounded-lg p-4 mb-4 border border-blue-200">
        <div class="flex items-center gap-2 mb-3">
          <svg class="w-5 h-5 text-blue-600" fill="currentColor" viewBox="0 0 20 20"><path d="M13 6a3 3 0 11-6 0 3 3 0 016 0zM18 8a2 2 0 11-4 0 2 2 0 014 0zM14 15a4 4 0 00-8 0v3h8v-3z"/></svg>
          <h3 class="font-semibold text-blue-800">AI-Enhanced Research Analysis</h3>
        </div>
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <h4 class="font-medium text-blue-700 mb-2">Basic Information</h4>
            <div class="space-y-1 text-sm">
              <div><span class="text-gray-600">Crop:</span> ${research.basic_info?.crop || item.crop}</div>
              <div><span class="text-gray-600">Variety:</span> ${research.basic_info?.variety_name || item.variety_name}</div>
              <div><span class="text-gray-600">Data Source:</span> ${research.basic_info?.data_source || 'enhanced_batch'}</div>
              <div><span class="text-gray-600">Institution:</span> ${research.basic_info?.institution || 'Not specified'}</div>
            </div>
          </div>
          
          <div>
            <h4 class="font-medium text-blue-700 mb-2">Research Summary</h4>
            <div class="space-y-1 text-sm">
              <div class="text-3xl font-bold text-blue-600">${research.search_results_summary || 0}</div>
              <div class="text-gray-600">Total research results found</div>
              <div class="text-sm text-gray-500">Across multiple academic databases</div>
            </div>
          </div>
        </div>
        
        <div class="mb-4">
          <h4 class="font-medium text-blue-700 mb-2">Stress Tolerance Evidence</h4>
          <div class="mb-2">
            ${stressTypes || '<span class="text-gray-500 text-sm">No stress tolerance evidence detected</span>'}
          </div>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
            <div class="bg-white p-2 rounded border">
              <div class="font-medium text-gray-700">Disease Resistance</div>
              <div class="text-lg font-bold text-primary-green">${research.disease_pest_resistance?.disease?.count || 0}</div>
            </div>
            <div class="bg-white p-2 rounded border">
              <div class="font-medium text-gray-700">Pest Resistance</div>
              <div class="text-lg font-bold text-primary-green">${research.disease_pest_resistance?.pest?.count || 0}</div>
            </div>
            <div class="bg-white p-2 rounded border">
              <div class="font-medium text-gray-700">Field Trials</div>
              <div class="text-lg font-bold text-primary-green">${research.field_trials || 0}</div>
            </div>
            <div class="bg-white p-2 rounded border">
              <div class="font-medium text-gray-700">Commercial Availability</div>
              <div class="text-lg font-bold text-primary-green">${research.commercial_availability || 0}</div>
            </div>
          </div>
        </div>
        
        <div class="mb-4">
          <h4 class="font-medium text-blue-700 mb-2">AI Enhancement Features</h4>
          <div>${enhancementFeatures || '<span class="text-gray-500 text-sm">Standard processing applied</span>'}</div>
        </div>
        
        <div>
          <h4 class="font-medium text-blue-700 mb-2">Quick Research Links</h4>
          <div class="flex flex-wrap gap-2">
            ${createResearchLink(`${item.variety_name} ${item.crop} stress tolerance research`)}
            ${createResearchLink(`${item.variety_name} ${item.crop} drought tolerance studies`)}
            ${createResearchLink(`${item.variety_name} ${item.crop} field trials`)}
            ${createResearchLink(`${item.variety_name} ${item.crop} seed availability`)}
          </div>
        </div>
      </div>
    `;
  }

  function createResearchLink(query){
    const u = `https://www.google.com/search?q=${encodeURIComponent(query)}`;
    return `<a href="${u}" target="_blank" rel="noopener" class="inline-flex items-center gap-1 text-primary-green hover:underline text-sm"><svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path d="M11 3a1 1 0 100 2h2.586l-6.293 6.293a1 1 0 101.414 1.414L15 6.414V9a1 1 0 102 0V4a1 1 0 00-1-1h-5z"/></svg>${query}</a>`;
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

  function exportCSV(){
    const rows = FILTERED.map(i=>({
      crop: i.crop,
      variety_name: i.variety_name,
      year_of_release: i.year_of_release,
      stress_tolerance: i.stress_tolerance,
      key_attributes: i.key_attributes,
      states: i.states_acronyms,
      seasons: i.seasons,
      days_to_maturity: i.days_to_maturity,
      evidence_quality: i.evidence_quality,
      seednet_available: i.seednet_available ? 'Yes' : 'No',
      seednet_url: i.seednet_url || '',
      total_research_results: i.research_data?.search_results_summary || 0
    }));
    const header = Object.keys(rows[0]||{});
    const csv=[header.join(','),...rows.map(r=>header.map(h=>`"${String(r[h]||'').replace(/"/g,'""')}"`).join(','))].join('\n');
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
  
  function updateCountsLabel(){ 
    const fc = document.getElementById('filtered-count'); 
    const tc = document.getElementById('total-count'); 
    if (fc) fc.textContent = String(FILTERED.length||0); 
    if (tc) tc.textContent = String(ALL_ITEMS.length||0); 
  }
  
  function setLastUpdated(){ 
    const d = new Date(); 
    const el = document.getElementById('last-updated'); 
    if (el) el.textContent = d.toISOString().split('T')[0]; 
  }

  function fillMulti(id, values){ 
    const el = document.getElementById(id); 
    if (!el) return; 
    el.innerHTML = values.map(v=>`<option value="${v}">${v}</option>`).join(''); 
  }
  
  function getMulti(id){ 
    const el = document.getElementById(id); 
    return Array.from(el?.selectedOptions||[]).map(o=>o.value); 
  }
  
  function unique(a){ 
    return Array.from(new Set(a)).filter(Boolean).sort(); 
  }
  
  function byId(id){ 
    return document.getElementById(id); 
  }

  function setupEvents(){
    // Event listeners
    byId('search-box')?.addEventListener('input', filterData);
    byId('crop-filter')?.addEventListener('change', filterData);
    byId('state-filter')?.addEventListener('change', filterData);
    byId('stress-filter')?.addEventListener('change', filterData);
    byId('stress-type-filter')?.addEventListener('change', filterData);
    byId('evidence-filter')?.addEventListener('change', filterData);
    byId('page-size')?.addEventListener('change', renderTable);
    byId('page-prev')?.addEventListener('click', ()=>{if (PAGE.index>1) PAGE.index--; renderTable();});
    byId('page-next')?.addEventListener('click', ()=>{PAGE.index++; renderTable();});
    byId('btn-export-csv')?.addEventListener('click', exportCSV);
    byId('btn-reload')?.addEventListener('click', ()=>window.location.reload());
    byId('btn-about')?.addEventListener('click', showAbout);

    // Modal close
    document.querySelector('.close')?.addEventListener('click', ()=>byId('variety-modal').style.display='none');
    window.addEventListener('click', (e)=>{ if (e.target.classList.contains('modal')) e.target.style.display='none'; });

    // Column visibility toggles
    document.querySelectorAll('input[data-col]').forEach(cb=>{
      cb.addEventListener('change', (e)=>{
        VISIBLE[e.target.dataset.col] = e.target.checked;
        renderTable();
      });
    });

    // Table sorting
    document.querySelectorAll('.sortable').forEach(th=>{
      th.addEventListener('click', ()=>onSort(th.dataset.key));
    });
  }

  function showAbout(){
    const aboutContent = `
      <div class="about-modal">
        <h2 class="text-2xl font-bold mb-4" style="color: var(--pxd-primary);">About India's Seed Varieties Dashboard</h2>
        
        <div class="mb-6">
          <h3 class="text-lg font-semibold mb-2" style="color: var(--pxd-primary);">Overview</h3>
          <p class="text-gray-700 mb-4">
            Since 2008, we have been collecting and analyzing seed variety data from official government sources and research institutions. 
            Our platform provides comprehensive information on stress-tolerant seed varieties to support farmers and agricultural decision-making.
          </p>
          
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div class="p-4 border rounded-lg" style="border-color: var(--pxd-secondary);">
              <h4 class="font-semibold mb-2" style="color: var(--pxd-primary);">Data Sources</h4>
              <ul class="text-sm text-gray-600 space-y-1">
                <li>• Official Government Seednet Portal</li>
                <li>• Central Seed Committee Records</li>
                <li>• Research Institution Publications</li>
                <li>• Academic Literature Database</li>
              </ul>
            </div>
            
            <div class="p-4 border rounded-lg" style="border-color: var(--pxd-secondary);">
              <h4 class="font-semibold mb-2" style="color: var(--pxd-primary);">Key Features</h4>
              <ul class="text-sm text-gray-600 space-y-1">
                <li>• Dual-view system for official vs research data</li>
                <li>• Advanced stress tolerance filtering</li>
                <li>• Direct Seednet portal integration</li>
                <li>• Evidence quality assessment</li>
                <li>• Comprehensive search across 405+ varieties</li>
              </ul>
            </div>
          </div>
        </div>

        <div class="mb-4">
          <h3 class="text-lg font-semibold mb-2" style="color: var(--pxd-primary);">AI Enhancement</h3>
          <p class="text-gray-700 mb-2">
            Our search and analysis capabilities are enhanced using Google Gemini 2.5 Flash for:
          </p>
          <ul class="text-sm text-gray-600 space-y-1 ml-4">
            <li>• Intelligent query processing and expansion</li>
            <li>• Evidence quality scoring</li>
            <li>• Stress tolerance pattern recognition</li>
            <li>• Research literature synthesis</li>
          </ul>
        </div>

        <div class="mb-6">
          <h3 class="text-lg font-semibold mb-2" style="color: var(--pxd-primary);">Official Resources</h3>
          <div class="flex flex-wrap gap-3">
            <a href="https://seednet.gov.in/" target="_blank" rel="noopener" 
               class="inline-flex items-center gap-2 px-4 py-2 rounded-md text-white text-sm hover:opacity-90 transition-opacity"
               style="background-color: var(--pxd-primary);">
              <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path d="M11 3a1 1 0 100 2h2.586l-6.293 6.293a1 1 0 101.414 1.414L15 6.414V9a1 1 0 102 0V4a1 1 0 00-1-1h-5z"/>
              </svg>
              Government Seednet Portal
            </a>
            
            <a href="https://www.icar.gov.in/" target="_blank" rel="noopener"
               class="inline-flex items-center gap-2 px-4 py-2 rounded-md text-white text-sm hover:opacity-90 transition-opacity"
               style="background-color: var(--pxd-secondary);">
              <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path d="M11 3a1 1 0 100 2h2.586l-6.293 6.293a1 1 0 101.414 1.414L15 6.414V9a1 1 0 102 0V4a1 1 0 00-1-1h-5z"/>
              </svg>
              ICAR Official Site
            </a>
          </div>
        </div>

        <div class="text-center pt-4 border-t border-gray-200">
          <p class="text-sm text-gray-500">
            Developed by Precision Development (PxD) • Data Research and AI Enhancement
          </p>
          <p class="text-xs text-gray-400 mt-1">
            Powered by Google Gemini 2.5 Flash
          </p>
        </div>
      </div>
    `;
    
    byId('modal-body').innerHTML = aboutContent;
    byId('variety-modal').style.display = 'block';
  }

  function byId(id){ 
    return document.getElementById(id); 
  }
})();
