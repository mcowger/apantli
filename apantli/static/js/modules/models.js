// Models table loading and rendering

import { state } from './state.js'
import { sortTable, applySortIfNeeded, updateSortIndicators } from './tables.js'

// Load models from API
export async function loadModels() {
  const res = await fetch('/v1/models')
  const data = await res.json()

  // Convert to array format for sorting: [id, provider, context_length]
  state.modelsData = data.data.map(m => [
    m.id,
    m.provider,
    m.context_length || 0
  ])

  if (!state.tableSortState['models-list']) {
    state.tableSortState['models-list'] = { column: null, direction: null, originalData: [...state.modelsData] }
  } else {
    state.tableSortState['models-list'].originalData = [...state.modelsData]
  }
  renderModelsTable(applySortIfNeeded('models-list', state.modelsData), state.tableSortState['models-list'])
}

// Sort models table
export function sortModelsTable(columnIndex) {
  sortTable('models-list', columnIndex, state.modelsData, renderModelsTable)
}

// Reload models and configuration data
export async function reloadModels() {
  const reloadButton = document.getElementById('reload-models-btn')
  const reloadStatus = document.getElementById('reload-status')
  
  if (!reloadButton || !reloadStatus) {
    console.error('Reload button or status element not found')
    return
  }

  try {
    // Show loading state
    reloadButton.setAttribute('aria-busy', 'true')
    reloadButton.disabled = true
    reloadStatus.style.display = 'flex'
    
    // Call reload endpoint
    const response = await fetch('/admin/reload', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      }
    })
    
    const result = await response.json()
    
    if (response.ok) {
      // Success - reload the models table
      await loadModels()
      
      // Show success message briefly
      const statusText = reloadStatus.querySelector('.status-text')
      if (statusText) {
        statusText.textContent = `Reload successful: ${result.models_count} models, ${result.providers_count} providers`
      }
      
      // Hide status after a delay
      setTimeout(() => {
        reloadStatus.style.display = 'none'
      }, 3000)
    } else {
      throw new Error(result.message || 'Reload failed')
    }
  } catch (error) {
    console.error('Reload failed:', error)
    
    // Show error message
    const statusText = reloadStatus.querySelector('.status-text')
    if (statusText) {
      statusText.textContent = `Reload failed: ${error.message}`
      statusText.style.color = 'var(--color-error)'
    }
    
    // Hide status after a delay
    setTimeout(() => {
      reloadStatus.style.display = 'none'
      // Reset color
      if (statusText) {
        statusText.style.color = ''
      }
    }, 5000)
  } finally {
    // Reset button state
    reloadButton.removeAttribute('aria-busy')
    reloadButton.disabled = false
  }
}

// Render models table
function renderModelsTable(data, sortState) {
  const table = document.getElementById('models-list')
  table.innerHTML = `
    <thead>
      <tr>
        <th class="sortable" onclick="window.sortModelsTable(0)">Model ID</th>
        <th class="sortable" onclick="window.sortModelsTable(1)">Provider</th>
        <th class="sortable" onclick="window.sortModelsTable(2)">Context Length</th>
      </tr>
    </thead>
    <tbody>
      ${data.map(row => `
        <tr>
          <td>${row[0]}</td>
          <td>${row[1]}</td>
          <td>${row[2] ? row[2].toLocaleString() : 'N/A'}</td>
        </tr>
      `).join('')}
    </tbody>
  `
  updateSortIndicators(table, sortState)
}
