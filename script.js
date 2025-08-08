// CSV-first loader (static-hosting friendly) + full interactivity
(function(){
  const CSV_PATH = 'varieties_compiled_enhanced.csv';
  let ALL_ITEMS = [];
  let FILTERED = [];
  let SORT = { key: null, dir: 'asc' };
  let VISIBLE = { crop:true,variety:true,year:true,stress:true,attributes:true,states:true,seasons:true,maturity:true,evidence:true };
  let PAGE = { size: 25, index: 1 };

  document.addEventListener('DOMContentLoaded', async () => {
    await loadCSV();
    populateFilters();
    updateStats();
    filterData();
    setupEvents();
  });

  async function loadCSV(){
    try {
      const res = await fetch(CSV_PATH);
      if (!res.ok) throw new Error('CSV not found');
      const text = await res.text();
      ALL_ITEMS = parseCsvToItems(text);
      FILTERED = [...ALL_ITEMS];
      updateCountsLabel();
      setLastUpdatedFromCSV();
      const totalEl = document.getElementById('total-varieties');
      if (totalEl) totalEl.textContent = String(ALL_ITEMS.length);
    } catch(e){
      console.error('Failed to load CSV', e);
      ALL_ITEMS = [];
      FILTERED = [];
      updateCountsLabel();
    }
  }

  function parseCsvToItems(csvText){
    const lines = csvText.split(/\r?\n/).filter(l => l !== '');
    if (lines.length <= 1) return [];
    const header = splitCsv(lines.shift());
    return lines.map(line => {
      const cols = splitCsv(line);
      const row = Object.fromEntries(header.map((h,i)=>[h, cols[i]||'']));
      const stressTypes = (row.Stressors_Broadly_Defined||'').split(',').map(s=>s.trim()).filter(Boolean);
      return {
        id: row.Seed_Name + '_' + row.Crop_Type,
        crop: row.Crop_Type || 'Unknown',
        variety_name: row.Seed_Name || 'Unknown Variety',
        year_of_release: row.Year_of_Release || '',
        stress_tolerance: (row.Is_Stresstolerant || 'Unknown') === 'Yes' ? 'Yes' : 'No',
        key_attributes: row.Stressors_Broadly_Defined || 'Standard variety',
        states_acronyms: row.All_States || row.Primary_State || 'Unknown',
        seasons: row.Crop_Season || 'Unknown',
        days_to_maturity: row.maturityDays || 'Unknown days',
        evidence_quality: 'Medium',
        seednet: { available: !!row.seednet_url, url: row.seednet_url || '', variety_id: '', fields: {} },
        research: {
          basic_info: { crop: row.Crop_Type, variety_name: row.Seed_Name, data_source: 'compiled_csv', year: row.Year_of_Release },
          search_results_summary: 0,
          stress_tolerance_evidence: Object.fromEntries(stressTypes.map(s=>[s, 1])),
          disease_pest_resistance: { disease: { count: 0 }, pest: { count: 0 } },
          field_trials: 0,
          commercial_availability: 0,
          enhancement_features: []
        },
        stress_types: stressTypes
      };
    });
  }

  function splitCsv(line){
    const out=[]; let cur=''; let q=false;
    for (let i=0;i<line.length;i++){
      const ch=line[i];
      if (q){ if (ch==='"' && line[i+1]==='"'){cur+='"';i++;continue;} if(ch==='"'){q=false;continue;} cur+=ch; }
      else { if (ch===','){ out.push(cur); cur=''; continue; } if (ch==='"'){ q=true; continue;} cur+=ch; }
    }
    out.push(cur); return out;
  }

  function setupEvents(){
    byId('search-box').addEventListener('input', filterData);
    byId('crop-filter').addEventListener('change', filterData);
    byId('state-filter').addEventListener('change', filterData);
    byId('stress-filter').addEventListener('change', filterData);
    byId('evidence-filter').addEventListener('change', filterData);
    byId('stress-type-filter').addEventListener('change', filterData);
    byId('btn-reset').addEventListener('click', () => { resetFilters(); filterData(); });
    byId('btn-reload').addEventListener('click', async () => { await loadCSV(); populateFilters(); filterData(); updateStats(); });
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
      <div class="space-y-3">
        <h2 class="text-2xl font-bold text-dark-green">About this Dashboard</h2>
        <p class="text-sm text-gray-700">This dashboard presents Official Seednet data (when available) and AI-Enhanced Research signals from compiled CSV.</p>
        <ul class="list-disc list-inside text-sm text-gray-700">
          <li><strong>Official Source:</strong> Link to Seednet portal when available.</li>
          <li><strong>AI-Enhanced Research:</strong> Aggregated stress-type signals derived from search metadata.</li>
          <li><strong>Updates:</strong> Click Reload Data after uploading a new compiled CSV.</li>
        </ul>
      </div>`;
    byId('variety-modal').style.display='block';
  }

  function populateFilters(){
    fillMulti('crop-filter', unique(ALL_ITEMS.map(i=>i.crop)));
    const states = unique(ALL_ITEMS.flatMap(i => String(i.states_acronyms||'').split(',').map(s=>s.trim()).filter(Boolean))).filter(s=>s!=='Unknown');
    fillMulti('state-filter', states);
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
      const itemStates = String(i.states_acronyms||'').split(',').map(s=>s.trim()).filter(Boolean);
      const matchesState = statesSel.length===0 || statesSel.some(s=> itemStates.includes(s));
      const matchesStress = stressSel.length===0 || stressSel.includes(i.stress_tolerance);
      const matchesEv = evSel.length===0 || evSel.includes(i.evidence_quality);
      const matchesStressTypes = stressTypesSel.length===0 || i.stress_types.some(t => stressTypesSel.includes(t));
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
      const links = `${createResearchLink(`${item.variety_name} ${item.crop} research publication`)} | ${createResearchLink(`${item.variety_name} ${item.crop} seed availability`)}`;
      return `
      <tr class="hover:bg-gray-50 transition-colors cursor-pointer" data-idx="${realIdx}">
        ${VISIBLE.crop?`<td>${item.crop}</td>`:''}
        ${VISIBLE.variety?`<td><div class="variety-name">${item.variety_name}</div><div class="text-xs text-gray-500">${links}</div></td>`:''}
        ${VISIBLE.year?`<td>${item.year_of_release}</td>`:''}
        ${VISIBLE.stress?`<td><span class="stress-${item.stress_tolerance.toLowerCase()}">${item.stress_tolerance}</span></td>`:''}
        ${VISIBLE.attributes?`<td class="text-sm">${item.key_attributes}</td>`:''}
        ${VISIBLE.states?`<td class="text-sm">${item.states_acronyms}</td>`:''}
        ${VISIBLE.seasons?`<td class="text-sm">${item.seasons}</td>`:''}
        ${VISIBLE.maturity?`<td class="text-sm">${item.days_to_maturity}</td>`:''}
        ${VISIBLE.evidence?`<td><span class="evidence-${item.evidence_quality.toLowerCase()}">${item.evidence_quality}</span></td>`:''}
      </tr>`;
    }).join('');

    Array.from(tbody.querySelectorAll('tr')).forEach(tr=>{
      tr.addEventListener('click', ()=>{
        const idx = Number(tr.getAttribute('data-idx'));
        showDetails(idx);
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

  function showDetails(index){
    const item = FILTERED[index];
    const modalBody = byId('modal-body'); if(!item||!modalBody) return;
    const seednetEnabled = item.seednet.available && item.seednet.url;
    const seednetBtnClass = seednetEnabled ? 'tab-seednet enabled' : 'tab-seednet disabled';
    modalBody.innerHTML = `
      <div class="mb-3">
        <h2 class="text-2xl font-bold text-dark-green">${item.variety_name}</h2>
        <div class="text-sm text-gray-600">${item.crop} • ${item.year_of_release}</div>
      </div>
      <div class="tabs">
        <button id="tab-seednet" class="tab-btn ${seednetBtnClass}">Seednet Details <span class="tab-badge">OFFICIAL SOURCE</span></button>
        <button id="tab-research" class="tab-btn tab-research">Research Details <span class="tab-badge">AI-ENHANCED RESEARCH</span></button>
      </div>
      <div id="panel-seednet" class="tab-panel ${seednetEnabled?'active':''}">
        ${seednetEnabled?(`<a href="${item.seednet.url}" target="_blank" rel="noopener" class="mt-2 inline-block bg-green-700 text-white px-4 py-2 rounded">VIEW ON SEEDNET PORTAL</a>`):'<div class="text-gray-500">No official Seednet data available.</div>'}
      </div>
      <div id="panel-research" class="tab-panel ${seednetEnabled?'':'active'}">
        ${researchPanel(item)}
      </div>`;
    const tabSeed = byId('tab-seednet'); const tabRes = byId('tab-research');
    const panSeed = byId('panel-seednet'); const panRes = byId('panel-research');
    if (seednetEnabled) tabSeed.addEventListener('click',()=>{ panSeed.classList.add('active'); panRes.classList.remove('active'); });
    tabRes.addEventListener('click',()=>{ panRes.classList.add('active'); panSeed.classList.remove('active'); });
    byId('variety-modal').style.display='block';
  }

  function researchPanel(item){
    const r = item.research; const stressList = Object.entries(r.stress_tolerance_evidence||{}).map(([k,v])=>`<span class="inline-block bg-amber-100 text-amber-800 text-xs px-2 py-1 rounded mr-1 mb-1">${k}</span>`).join('');
    const features = (r.enhancement_features||[]).map(f=>`<span class="inline-block bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded mr-1 mb-1">${f}</span>`).join('');
    const links = [createResearchLink(`${item.variety_name} ${item.crop} stress tolerance`), createResearchLink(`${item.variety_name} ${item.crop} drought tolerance`)].join(' ');
    return `
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <h3 class="font-semibold text-dark-green mb-2">Basic Info</h3>
          <div class="text-sm">Crop: ${item.crop}</div>
          <div class="text-sm">Variety: ${item.variety_name}</div>
          <div class="text-sm">Source: compiled_csv</div>
          <div class="text-sm">Year: ${item.year_of_release}</div>
        </div>
        <div>
          <h3 class="font-semibold text-dark-green mb-2">Search Results Summary</h3>
          <div class="text-3xl font-bold text-primary-green">${r.search_results_summary}</div>
        </div>
      </div>
      <div class="mt-4"><h3 class="font-semibold text-dark-green mb-2">Stress Tolerance Evidence</h3><div>${stressList||'<span class="text-gray-500">No evidence detected</span>'}</div></div>
      <div class="mt-4"><h3 class="font-semibold text-dark-green mb-2">AI Enhancement Features</h3><div>${features||'<span class="text-gray-500">None listed</span>'}</div></div>
      <div class="mt-4"><h3 class="font-semibold text-dark-green mb-2">Quick Research Links</h3><div class="space-x-2">${links}</div></div>`;
  }

  function createResearchLink(query){
    const u=`https://www.google.com/search?q=${encodeURIComponent(query)}`;
    return `<a href="${u}" target="_blank" rel="noopener" class="text-primary-green underline">${query}</a>`;
  }

  function exportCSV(){
    const rows = FILTERED.map(i=>({crop:i.crop,variety_name:i.variety_name,year_of_release:i.year_of_release,stress_tolerance:i.stress_tolerance,key_attributes:i.key_attributes,states:i.states_acronyms,seasons:i.seasons,days_to_maturity:i.days_to_maturity,evidence_quality:i.evidence_quality}));
    const header = Object.keys(rows[0]||{});
    const csv=[header.join(','),...rows.map(r=>header.map(h=>`"${String(r[h]||'').replace(/"/g,'""')}"`).join(','))].join('\n');
    const blob=new Blob([csv],{type:'text/csv;charset=utf-8;'}); const url=URL.createObjectURL(blob);
    const a=document.createElement('a'); a.href=url; a.download='varieties_export.csv'; a.click(); URL.revokeObjectURL(url);
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
  function setLastUpdatedFromCSV(){ const d=new Date(); const el=document.getElementById('last-updated'); if (el) el.textContent=d.toISOString().split('T')[0]; }

  function fillMulti(id, values){ const el=document.getElementById(id); if (!el) return; el.innerHTML=values.map(v=>`<option value="${v}">${v}</option>`).join(''); }
  function getMulti(id){ const el=document.getElementById(id); return Array.from(el?.selectedOptions||[]).map(o=>o.value); }
  function unique(a){ return Array.from(new Set(a)).sort(); }
  function byId(id){ return document.getElementById(id); }
})();


