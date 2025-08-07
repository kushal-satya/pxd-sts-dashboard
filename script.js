// Application State
let allData = [];
let filteredData = [];
let map = null;
let geoJsonLayer = null;
let selectedState = null;

// Initialize Application on DOM Load
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

// Main Application Initialization
async function initializeApp() {
    try {
        showLoadingState();
        await loadSeedData();
        await initializeMap();
        setupEventListeners();
        updateCounts();
        renderTable();
        hideLoadingState();
    } catch (error) {
        console.error('Error initializing application:', error);
        showErrorState('Failed to load application data. Please refresh the page.');
    }
}

// Load and Parse JSON Data
async function loadSeedData() {
    try {
        // Load both JSON files
        const [response1, response2] = await Promise.all([
            fetch('sample_results_20250729_185047.json'),
            fetch('sample_results_20250729_190724.json')
        ]);
        
        if (!response1.ok || !response2.ok) {
            throw new Error('Failed to load JSON files');
        }
        
        const data1 = await response1.json();
        const data2 = await response2.json();
        
        // Combine and process the data
        const combinedData = [...data1, ...data2];
        allData = processJSONData(combinedData);
        filteredData = [...allData];
        
        populateFilters();
        
    } catch (error) {
        console.error('Error loading JSON data:', error);
        throw error;
    }
}

// Process the raw JSON data into a format suitable for the dashboard
function processJSONData(rawData) {
    return rawData.map(item => {
        const seednetData = item.original_data?.seednet_data || {};
        const analysisResult = item.analysis_result || {};
        const stressProfile = analysisResult.stress_tolerance_profile || {};
        
        // Extract stress tolerance information
        const stressTolerances = [];
        if (stressProfile.drought_tolerance?.tolerance_level !== 'unknown') {
            stressTolerances.push('Drought');
        }
        if (stressProfile.heat_tolerance?.temperature_thresholds !== 'unknown') {
            stressTolerances.push('Heat');
        }
        if (stressProfile.salinity_tolerance?.salt_concentration_tolerance !== 'unknown') {
            stressTolerances.push('Salinity');
        }
        if (stressProfile.flood_tolerance?.waterlogging_duration !== 'unknown') {
            stressTolerances.push('Flood');
        }
        if (stressProfile.disease_resistance?.specific_pathogens !== 'unknown') {
            stressTolerances.push('Disease');
        }
        if (stressProfile.pest_resistance?.target_insects !== 'unknown') {
            stressTolerances.push('Pest');
        }
        
        // Process recommended states
        const recommendedStates = seednetData['Recommended States'] || 'Not specified';
        const primaryState = recommendedStates.split(',')[0]?.trim() || 'Unknown';
        
        // Extract seasons from adaptation info
        const adaptationInfo = seednetData['Adaptation and recommended ecology'] || '';
        const seasons = extractSeasons(adaptationInfo);
        
        return {
            id: item.variety_id || Math.random().toString(36).substr(2, 9),
            Seed_Name: seednetData['Variety Name'] || 'Unknown Variety',
            Crop_Type: seednetData['Crop Name'] || 'Unknown',
            Primary_State: primaryState,
            Year_of_Release: seednetData['Year of Release'] || 'Unknown',
            Stressors_Broadly_Defined: stressTolerances.join(', ') || 'Not specified',
            In_Depth_Stress_Tolerance_Notes: analysisResult.variety_analysis?.overall_assessment || 'No detailed analysis available',
            Breeder_Origin_Institution: seednetData['Institution Responsible for developing Breeder Seed'] || 'Not specified',
            Crop_Value_Chain: seednetData['Group Name'] || 'Not specified',
            Crop_Season: seasons,
            Is_Stresstolerant: stressTolerances.length > 0 ? 'Yes' : 'Unknown',
            Unique_Genetic_Marker_STS: 'Analysis pending',
            Variety: seednetData['Variety Name'] || 'Unknown',
            notificationDate: seednetData['Notification Date'] || 'Not specified',
            averageYield: seednetData['Average Yield (Kg/Ha)'] || 'Not specified',
            maturityDays: seednetData['Maturity (in days)'] || 'Not specified',
            seedRate: seednetData['Seed Rate (Kg/Ha)'] || 'Not specified',
            parentage: seednetData['Parentage'] || 'Not specified'
        };
    });
}

// Extract seasons from adaptation text
function extractSeasons(adaptationText) {
    const seasons = [];
    const text = adaptationText.toLowerCase();
    
    if (text.includes('kharif')) seasons.push('Kharif');
    if (text.includes('rabi')) seasons.push('Rabi');
    if (text.includes('summer')) seasons.push('Summer');
    if (text.includes('winter')) seasons.push('Winter');
    if (text.includes('monsoon')) seasons.push('Monsoon');
    
    return seasons.length > 0 ? seasons.join(', ') : 'Not specified';
}

// Initialize Leaflet Map with India GeoJSON
async function initializeMap() {
    try {
        // Initialize map
        map = L.map('map').setView([22.5, 78.0], 4);
        
        // Add CartoDB Positron base layer
        L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
            attribution: '© OpenStreetMap contributors © CARTO',
            maxZoom: 19
        }).addTo(map);

        // Load India states GeoJSON
        const response = await fetch('https://code.highcharts.com/mapdata/countries/in/in-all.geo.json');
        const geoData = await response.json();

        // Add GeoJSON layer with interaction
        geoJsonLayer = L.geoJSON(geoData, {
            style: function(feature) {
                return {
                    fillColor: '#f0f0f0',
                    weight: 1,
                    opacity: 1,
                    color: '#666',
                    dashArray: '',
                    fillOpacity: 0.7
                };
            },
            onEachFeature: function(feature, layer) {
                const stateName = feature.properties.name || feature.properties.NAME;
                
                layer.on({
                    mouseover: function(e) {
                        highlightStateOnHover(e.target, stateName);
                    },
                    mouseout: function(e) {
                        resetStateHighlight(e.target);
                    },
                    click: function(e) {
                        selectStateFromMap(stateName, e.target);
                    }
                });
                
                // Create popup with variety count
                const varietyCount = getVarietyCountForState(stateName);
                layer.bindPopup(`
                    <div class="p-3">
                        <h3 class="font-bold text-dark-green text-lg">${stateName}</h3>
                        <p class="text-sm text-gray-600 mt-1">
                            <strong>${varietyCount}</strong> seed varieties available
                        </p>
                        <button onclick="selectStateFromPopup('${stateName}')" 
                                class="mt-2 bg-primary-green text-white px-3 py-1 rounded text-sm hover:bg-dark-green transition-colors">
                            Filter by this state →
                        </button>
                    </div>
                `);
            }
        }).addTo(map);
        
    } catch (error) {
        console.error('Error initializing map:', error);
        // If map fails to load, continue without it
        document.getElementById('map').innerHTML = '<div class="text-center py-8 text-gray-500">Map unavailable</div>';
    }
}

// Map Interaction Functions
function highlightStateOnHover(layer, stateName) {
    if (!isStateSelected(layer)) {
        layer.setStyle({
            weight: 2,
            color: '#666',
            dashArray: '',
            fillOpacity: 0.9,
            fillColor: '#b2d8d8'
        });
    }
}

function resetStateHighlight(layer) {
    if (!isStateSelected(layer)) {
        layer.setStyle({
            weight: 1,
            color: '#666',
            dashArray: '',
            fillOpacity: 0.7,
            fillColor: '#f0f0f0'
        });
    }
}

function isStateSelected(layer) {
    return layer.options.fillColor === '#008080';
}

function selectStateFromMap(stateName, layer) {
    // Reset all states first
    resetAllStates();
    
    // Highlight selected state
    layer.setStyle({
        weight: 2,
        color: '#004d4d',
        dashArray: '',
        fillOpacity: 0.9,
        fillColor: '#008080'
    });
    
    selectedState = stateName;
    
    // Update dropdown and apply filters
    document.getElementById('stateFilter').value = stateName;
    applyFilters();
}

function selectStateFromPopup(stateName) {
    // Find the layer for this state
    if (geoJsonLayer) {
        geoJsonLayer.eachLayer(function(layer) {
            const layerStateName = layer.feature.properties.name || layer.feature.properties.NAME;
            if (layerStateName === stateName) {
                selectStateFromMap(stateName, layer);
            }
        });
    }
    
    // Close popup
    if (map) map.closePopup();
}

function resetAllStates() {
    if (geoJsonLayer) {
        geoJsonLayer.eachLayer(function(layer) {
            layer.setStyle({
                weight: 1,
                color: '#666',
                fillOpacity: 0.7,
                fillColor: '#f0f0f0'
            });
        });
    }
    selectedState = null;
}

// Setup Event Listeners
function setupEventListeners() {
    document.getElementById('searchInput').addEventListener('input', debounce(applyFilters, 300));
    document.getElementById('stateFilter').addEventListener('change', onStateFilterChange);
    document.getElementById('cropFilter').addEventListener('change', applyFilters);
    document.getElementById('yearFilter').addEventListener('change', applyFilters);
    document.getElementById('clearFilters').addEventListener('click', clearAllFilters);
}

// State filter change handler (for dropdown)
function onStateFilterChange() {
    const selectedStateFromDropdown = document.getElementById('stateFilter').value;
    
    // Update map selection
    resetAllStates();
    
    if (selectedStateFromDropdown && geoJsonLayer) {
        geoJsonLayer.eachLayer(function(layer) {
            const layerStateName = layer.feature.properties.name || layer.feature.properties.NAME;
            if (layerStateName === selectedStateFromDropdown) {
                layer.setStyle({
                    weight: 2,
                    color: '#004d4d',
                    fillOpacity: 0.9,
                    fillColor: '#008080'
                });
                selectedState = selectedStateFromDropdown;
            }
        });
    }
    
    applyFilters();
}

// Apply All Filters
function applyFilters() {
    const searchTerm = document.getElementById('searchInput').value.toLowerCase();
    const stateFilter = document.getElementById('stateFilter').value;
    const cropFilter = document.getElementById('cropFilter').value;
    const yearFilter = document.getElementById('yearFilter').value;

    filteredData = allData.filter(item => {
        const matchesSearch = !searchTerm || 
            item.Seed_Name.toLowerCase().includes(searchTerm) ||
            item.Crop_Type.toLowerCase().includes(searchTerm) ||
            item.Breeder_Origin_Institution.toLowerCase().includes(searchTerm) ||
            item.Crop_Value_Chain.toLowerCase().includes(searchTerm) ||
            item.Stressors_Broadly_Defined.toLowerCase().includes(searchTerm) ||
            item.In_Depth_Stress_Tolerance_Notes.toLowerCase().includes(searchTerm);
        
        const matchesState = !stateFilter || item.Primary_State === stateFilter;
        const matchesCrop = !cropFilter || item.Crop_Type === cropFilter;
        const matchesYear = !yearFilter || item.Year_of_Release === yearFilter;

        return matchesSearch && matchesState && matchesCrop && matchesYear;
    });

    updateCascadingFilters();
    updateCounts();
    renderTable();
}

// Update dependent filters based on current selection
function updateCascadingFilters() {
    const stateFilter = document.getElementById('stateFilter').value;
    const relevantData = stateFilter ? 
        allData.filter(item => item.Primary_State === stateFilter) : 
        allData;

    // Update crop filter
    updateSelectOptions('cropFilter', relevantData, 'Crop_Type', 'All Crops');
    
    // Update year filter
    updateSelectOptions('yearFilter', relevantData, 'Year_of_Release', 'All Years');
}

// Generic function to update select options
function updateSelectOptions(selectId, data, field, defaultText) {
    const select = document.getElementById(selectId);
    const currentValue = select.value;
    const uniqueValues = [...new Set(data.map(item => item[field]))].sort();
    
    select.innerHTML = `<option value="">${defaultText}</option>` +
        uniqueValues.map(value => 
            `<option value="${value}" ${value === currentValue ? 'selected' : ''}>${value}</option>`
        ).join('');
}

// Populate initial filter options
function populateFilters() {
    // Populate state filter
    const states = [...new Set(allData.map(item => item.Primary_State))].sort();
    const stateSelect = document.getElementById('stateFilter');
    stateSelect.innerHTML = '<option value="">All States</option>' +
        states.map(state => `<option value="${state}">${state}</option>`).join('');

    // Populate other filters
    updateSelectOptions('cropFilter', allData, 'Crop_Type', 'All Crops');
    updateSelectOptions('yearFilter', allData, 'Year_of_Release', 'All Years');
}

// Clear all filters and reset state
function clearAllFilters() {
    // Reset form inputs
    document.getElementById('searchInput').value = '';
    document.getElementById('stateFilter').value = '';
    document.getElementById('cropFilter').value = '';
    document.getElementById('yearFilter').value = '';
    
    // Reset map
    resetAllStates();
    
    // Repopulate filters and apply
    populateFilters();
    applyFilters();
}

// Render data table with expandable rows
function renderTable() {
    const tbody = document.getElementById('seedTableBody');
    const searchTerm = document.getElementById('searchInput').value.toLowerCase();
    
    if (filteredData.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="px-4 py-8 text-center text-gray-500">
                    <div class="empty-state">
                        <div class="text-4xl mb-4">🌱</div>
                        <p class="text-lg font-medium">No varieties found</p>
                        <p class="text-sm">Try adjusting your filters or search terms</p>
                    </div>
                </td>
            </tr>
        `;
        document.getElementById('emptyState').classList.remove('hidden');
        return;
    }

    document.getElementById('emptyState').classList.add('hidden');

    tbody.innerHTML = filteredData.map((item, index) => `
        <tr class="border-b hover:bg-gray-50 transition-colors" id="row-${index}">
            <td class="px-4 py-3">
                <div class="font-medium text-dark-green">
                    ${highlightSearch(item.Seed_Name, searchTerm)}
                </div>
                <div class="text-xs text-gray-500 mt-1">
                    ${highlightSearch(item.Breeder_Origin_Institution, searchTerm)}
                </div>
            </td>
            <td class="px-4 py-3">
                <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                    ${highlightSearch(item.Crop_Type, searchTerm)}
                </span>
                <div class="text-xs text-gray-600 mt-1">
                    ${highlightSearch(item.Crop_Value_Chain, searchTerm)}
                </div>
            </td>
            <td class="px-4 py-3 font-medium">
                ${highlightSearch(item.Primary_State, searchTerm)}
            </td>
            <td class="px-4 py-3">
                <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
                    ${item.Year_of_Release}
                </span>
            </td>
            <td class="px-4 py-3">
                <div class="text-sm text-gray-700">
                    ${highlightSearch(truncateText(item.Stressors_Broadly_Defined, 50), searchTerm)}
                </div>
                <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-800 mt-1">
                    ${item.Crop_Season}
                </span>
            </td>
            <td class="px-4 py-3 space-y-1">
                <button onclick="toggleNotes(${index})" 
                        class="btn-show-notes" 
                        id="notes-btn-${index}">
                    Show Notes
                </button>
                <br>
                <a href="https://www.google.com/search?q=${encodeURIComponent(item.Seed_Name + ' ' + item.Variety + ' seed variety stress tolerance')}" 
                   target="_blank" 
                   class="details-link text-sm">
                    Details →
                </a>
            </td>
        </tr>
        <tr id="notes-row-${index}" class="hidden expanded-row">
            <td colspan="6" class="px-4 py-0">
                <div class="notes-content">
                    <h4 class="font-semibold text-dark-green mb-2">Detailed Stress Tolerance Profile</h4>
                    <p class="text-sm text-gray-700 mb-3">
                        ${highlightSearch(item.In_Depth_Stress_Tolerance_Notes, searchTerm)}
                    </p>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                        <div>
                            <span class="font-medium text-dark-green">Variety:</span>
                            <span class="text-gray-600">${item.Variety}</span>
                        </div>
                        <div>
                            <span class="font-medium text-dark-green">Stress Tolerant:</span>
                            <span class="px-2 py-1 rounded-full text-xs ${item.Is_Stresstolerant === 'Yes' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}">
                                ${item.Is_Stresstolerant}
                            </span>
                        </div>
                        <div>
                            <span class="font-medium text-dark-green">Yield:</span>
                            <span class="text-gray-600">${item.averageYield}</span>
                        </div>
                        <div>
                            <span class="font-medium text-dark-green">Maturity:</span>
                            <span class="text-gray-600">${item.maturityDays}</span>
                        </div>
                    </div>
                </div>
            </td>
        </tr>
    `).join('');
}

// Toggle expandable notes for table rows
function toggleNotes(index) {
    const notesRow = document.getElementById(`notes-row-${index}`);
    const button = document.getElementById(`notes-btn-${index}`);
    
    if (notesRow.classList.contains('hidden')) {
        notesRow.classList.remove('hidden');
        button.textContent = 'Hide Notes';
        button.className = 'btn-hide-notes';
    } else {
        notesRow.classList.add('hidden');
        button.textContent = 'Show Notes';
        button.className = 'btn-show-notes';
    }
}

// Utility Functions
function highlightSearch(text, searchTerm) {
    if (!searchTerm || !text) return text;
    
    const regex = new RegExp(`(${escapeRegex(searchTerm)})`, 'gi');
    return text.replace(regex, '<span class="highlight">$1</span>');
}

function escapeRegex(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function truncateText(text, maxLength) {
    if (!text) return '';
    return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Update counts in UI
function updateCounts() {
    const totalCount = allData.length;
    const filteredCount = filteredData.length;
    
    document.getElementById('totalSeeds').textContent = totalCount;
    document.getElementById('totalCount').textContent = totalCount;
    document.getElementById('filteredCount').textContent = filteredCount;
}

// Get variety count for a specific state
function getVarietyCountForState(stateName) {
    return allData.filter(item => item.Primary_State === stateName).length;
}

// Loading and Error States
function showLoadingState() {
    document.getElementById('loadingState').classList.remove('hidden');
    document.getElementById('emptyState').classList.add('hidden');
}

function hideLoadingState() {
    document.getElementById('loadingState').classList.add('hidden');
}

function showErrorState(message) {
    const tbody = document.getElementById('seedTableBody');
    tbody.innerHTML = `
        <tr>
            <td colspan="6" class="px-4 py-8 text-center">
                <div class="error-message">
                    <div class="text-4xl mb-4">⚠️</div>
                    <p class="text-lg font-medium">Error Loading Data</p>
                    <p class="text-sm">${message}</p>
                </div>
            </td>
        </tr>
    `;
    hideLoadingState();
}

// Make functions globally available for onclick handlers
window.toggleNotes = toggleNotes;
window.selectStateFromPopup = selectStateFromPopup;