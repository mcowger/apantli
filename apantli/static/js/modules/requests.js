// Request loading, rendering, and detail views

import { state } from './state.js'
import { escapeHtml, copyToClipboard } from './core.js'
import { sortTable, updateSortIndicators } from './tables.js'
import {
  extractContentText,
  extractConversation,
  estimateTokens,
  formatMessageContent,
  renderConversationView,
  renderJsonTree,
  toggleJson
} from './utils.js'

// Toggle between conversation and JSON view
export function toggleDetailView(requestId, mode) {
  state.detailViewMode[requestId] = mode
  const requestObj = state.requestsObjects.find(r => r.timestamp === requestId)
  if (!requestObj) return

  const detailRow = document.getElementById('detail-' + requestId)
  const contentDiv = detailRow.querySelector('.detail-content')

  if (mode === 'conversation') {
    contentDiv.innerHTML = renderConversationView(requestObj)
  } else {
    // JSON view
    let incomingRequestHtml = '<span class="json-null">null</span>'
    let requestHtml = '<span class="error">Error parsing request</span>'
    let responseHtml = '<span class="error">Error parsing response</span>'

    try {
      if (requestObj.incoming_request_data) {
        const incomingReq = JSON.parse(requestObj.incoming_request_data)
        incomingRequestHtml = renderJsonTree(incomingReq)
      }
    } catch(e) {}

    try {
      const req = JSON.parse(requestObj.request_data)
      requestHtml = renderJsonTree(req)
    } catch(e) {}

    try {
      const resp = JSON.parse(requestObj.response_data)
      responseHtml = renderJsonTree(resp)
    } catch(e) {}

    contentDiv.innerHTML = `
      <b>Incoming Request (from client):</b>
      <div class="json-view json-tree">${incomingRequestHtml}</div>
      <b>Outbound Request (to LLM):</b>
      <div class="json-view json-tree">${requestHtml}</div>
      <b>Response:</b>
      <div class="json-view json-tree">${responseHtml}</div>
    `
  }

  // Update toggle buttons
  detailRow.querySelectorAll('.toggle-btn').forEach(btn => {
    btn.classList.remove('active')
    if (btn.dataset.mode === mode) {
      btn.classList.add('active')
    }
  })
}

// Load requests from API
export async function loadRequests(alpineData) {
  if (!alpineData) return
  try {
    const query = alpineData.buildQuery(alpineData.dateFilter)
    const offset = (alpineData.currentPage - 1) * alpineData.itemsPerPage
    let url = `/requests${query}${query ? '&' : '?'}offset=${offset}&limit=${alpineData.itemsPerPage}`

    // Add filter parameters
    const filters = alpineData.requestFilters
    if (filters.provider) {
      url += `&provider=${encodeURIComponent(filters.provider)}`
    }
    if (filters.model) {
      url += `&model=${encodeURIComponent(filters.model)}`
    }
    if (filters.minCost !== '' && filters.minCost !== null) {
      url += `&min_cost=${filters.minCost}`
    }
    if (filters.maxCost !== '' && filters.maxCost !== null) {
      url += `&max_cost=${filters.maxCost}`
    }
    if (filters.search) {
      url += `&search=${encodeURIComponent(filters.search)}`
    }

    const res = await fetch(url)
    const data = await res.json()

    // Store server-side aggregates for ALL matching requests
    state.serverAggregates = {
      total: data.total,
      total_tokens: data.total_tokens,
      total_cost: data.total_cost,
      avg_cost: data.avg_cost
    }

    // Store total for pagination
    alpineData.totalItems = data.total

    // Store original objects and convert to array format for sorting
    state.requestsObjects = data.requests
    state.requestsData = data.requests.map(r => [
      new Date(r.timestamp.endsWith('Z') || r.timestamp.includes('+') ? r.timestamp : r.timestamp + 'Z').getTime(), // For sorting by time
      r.model,
      r.total_tokens,
      r.cost,
      r.duration_ms,
      r.timestamp // Store timestamp for detail row lookup
    ])

    // Populate filter dropdowns from current page data
    populateFilterDropdowns(alpineData)

    // Initialize or update sort state
    if (!state.tableSortState['requests-list']) {
      state.tableSortState['requests-list'] = { column: null, direction: null, originalData: [...state.requestsData] }
    } else {
      // Update originalData to match current filtered results
      state.tableSortState['requests-list'].originalData = [...state.requestsData]
    }

    // Update summary and render table
    updateRequestSummary()
    renderRequestsTable(state.requestsData, state.tableSortState['requests-list'])
  } catch(e) {
    document.getElementById('requests-list').innerHTML = '<tr><td colspan="5">Error loading requests</td></tr>'
  }
}

// Populate filter dropdowns
function populateFilterDropdowns(alpineData) {
  // Get unique providers from current page data
  const providers = [...new Set(state.requestsObjects.map(r => r.provider).filter(Boolean))].sort()
  const providerSelect = document.getElementById('filter-provider')
  const currentProvider = alpineData.requestFilters.provider
  providerSelect.innerHTML = '<option value="">All</option>'
  providers.forEach(p => {
    const option = document.createElement('option')
    option.value = p
    option.textContent = p
    if (p === currentProvider) option.selected = true
    providerSelect.appendChild(option)
  })

  // Get unique models from current page data
  const models = [...new Set(state.requestsObjects.map(r => r.model).filter(Boolean))].sort()
  const modelSelect = document.getElementById('filter-model')
  const currentModel = alpineData.requestFilters.model
  modelSelect.innerHTML = '<option value="">All</option>'
  models.forEach(m => {
    const option = document.createElement('option')
    option.value = m
    option.textContent = m
    if (m === currentModel) option.selected = true
    modelSelect.appendChild(option)
  })
}

// Update request summary display
function updateRequestSummary() {
  const summary = document.getElementById('request-summary')

  // Use server-side aggregates for ALL matching requests, not just paginated results
  if (state.serverAggregates.total === 0) {
    summary.style.display = 'none'
    return
  }

  document.getElementById('summary-count').textContent = state.serverAggregates.total.toLocaleString()
  document.getElementById('summary-cost').textContent = '$' + state.serverAggregates.total_cost.toFixed(4)
  document.getElementById('summary-tokens').textContent = state.serverAggregates.total_tokens.toLocaleString()
  document.getElementById('summary-avg-cost').textContent = '$' + state.serverAggregates.avg_cost.toFixed(4)

  summary.style.display = 'flex'
}

// Sort requests table
export function sortRequestsTable(columnIndex) {
  sortTable('requests-list', columnIndex, state.requestsData, renderRequestsTable)
}

// Render requests table
function renderRequestsTable(data, sortState) {
  const tbody = document.createElement('tbody')

  data.forEach(row => {
    const timestamp = row[5]
    const requestObj = state.requestsObjects.find(r => r.timestamp === timestamp)
    if (!requestObj) return

    const requestId = timestamp
    const currentMode = state.detailViewMode[requestId] || 'conversation'

    // Calculate cost breakdown
    const promptTokens = requestObj.prompt_tokens || 0
    const completionTokens = requestObj.completion_tokens || 0
    const totalTokens = requestObj.total_tokens || 0
    const cost = requestObj.cost || 0

    // Rough cost split based on token counts (not exact but reasonable)
    const promptCost = totalTokens > 0 ? (promptTokens / totalTokens) * cost : 0
    const completionCost = cost - promptCost

    // Create main row
    const mainRow = document.createElement('tr')
    mainRow.className = 'request-row'
    mainRow.onclick = () => window.toggleDetail(requestId)
    mainRow.innerHTML = `
      <td>${escapeHtml(new Date(timestamp.endsWith('Z') || timestamp.includes('+') ? timestamp : timestamp + 'Z').toLocaleString())}</td>
      <td>${escapeHtml(row[1])}</td>
      <td>${row[2].toLocaleString()}</td>
      <td>$${row[3].toFixed(4)}</td>
      <td>${row[4]}ms</td>
    `

    // Create detail row, restore expanded state
    const detailRow = document.createElement('tr')
    detailRow.id = 'detail-' + requestId
    detailRow.style.display = state.expandedRequests.has(requestId) ? 'table-row' : 'none'

    // Extract parameters from request data
    let paramsHtml = ''
    try {
      const req = JSON.parse(requestObj.request_data)
      const params = []

      if (req.temperature !== null && req.temperature !== undefined) {
        params.push(`temp: ${req.temperature}`)
      }
      if (req.max_tokens !== null && req.max_tokens !== undefined) {
        params.push(`max: ${req.max_tokens}`)
      }
      if (req.timeout !== null && req.timeout !== undefined) {
        params.push(`timeout: ${req.timeout}s`)
      }
      if (req.num_retries !== null && req.num_retries !== undefined) {
        params.push(`retries: ${req.num_retries}`)
      }
      if (req.top_p !== null && req.top_p !== undefined) {
        params.push(`top_p: ${req.top_p}`)
      }

      if (params.length > 0) {
        paramsHtml = `
          <div class="detail-stat">
            <span class="detail-stat-label">Params: </span>
            <span class="detail-stat-value">${params.join(', ')}</span>
          </div>
        `
      }
    } catch(e) {
      // Ignore parsing errors
    }

    // Build detail content
    const detailHeader = `
      <div class="detail-header">
        <div class="detail-stats">
          <div class="detail-stat">
            <span class="detail-stat-label">Model: </span>
            <span class="detail-stat-value">${escapeHtml(requestObj.model)}</span>
          </div>
          <div class="detail-stat">
            <span class="detail-stat-label">Provider: </span>
            <span class="detail-stat-value">${escapeHtml(requestObj.provider || 'unknown')}</span>
          </div>
          <div class="detail-stat">
            <span class="detail-stat-label">Tokens: </span>
            <span class="detail-stat-value">${promptTokens.toLocaleString()} in / ${completionTokens.toLocaleString()} out = ${totalTokens.toLocaleString()} total</span>
          </div>
          <div class="detail-stat">
            <span class="detail-stat-label">Cost: </span>
            <span class="detail-stat-value">$${cost.toFixed(4)} ($${promptCost.toFixed(4)} in + $${completionCost.toFixed(4)} out)</span>
          </div>
          <div class="detail-stat">
            <span class="detail-stat-label">Duration: </span>
            <span class="detail-stat-value">${requestObj.duration_ms}ms</span>
          </div>
          ${paramsHtml}
        </div>
      </div>
    `

    const toggleButtons = `
      <div class="detail-toggle">
        <button class="toggle-btn ${currentMode === 'conversation' ? 'active' : ''}" data-mode="conversation" onclick="event.stopPropagation(); window.toggleDetailView('${requestId}', 'conversation')">Conversation</button>
        <button class="toggle-btn ${currentMode === 'json' ? 'active' : ''}" data-mode="json" onclick="event.stopPropagation(); window.toggleDetailView('${requestId}', 'json')">Raw JSON</button>
      </div>
    `

    // Generate initial content
    let contentHtml = ''
    if (currentMode === 'conversation') {
      contentHtml = renderConversationView(requestObj)
    } else {
      let incomingRequestHtml = '<span class="json-null">null</span>'
      let requestHtml = '<span class="error">Error parsing request</span>'
      let responseHtml = '<span class="error">Error parsing response</span>'

      try {
        if (requestObj.incoming_request_data) {
          const incomingReq = JSON.parse(requestObj.incoming_request_data)
          incomingRequestHtml = renderJsonTree(incomingReq)
        }
      } catch(e) {}

      try {
        const req = JSON.parse(requestObj.request_data)
        requestHtml = renderJsonTree(req)
      } catch(e) {}

      try {
        const resp = JSON.parse(requestObj.response_data)
        responseHtml = renderJsonTree(resp)
      } catch(e) {}

      contentHtml = `
        <b>Incoming Request (from client):</b>
        <div class="json-view json-tree">${incomingRequestHtml}</div>
        <b>Outbound Request (to LLM):</b>
        <div class="json-view json-tree">${requestHtml}</div>
        <b>Response:</b>
        <div class="json-view json-tree">${responseHtml}</div>
      `
    }

    detailRow.innerHTML = `
      <td colspan="5" class="request-detail">
        ${detailHeader}
        ${toggleButtons}
        <div class="detail-content">
          ${contentHtml}
        </div>
      </td>
    `

    tbody.appendChild(mainRow)
    tbody.appendChild(detailRow)
  })

  const table = document.getElementById('requests-list')
  table.innerHTML = `
    <thead>
      <tr>
        <th class="sortable" onclick="window.sortRequestsTable(0)">Time</th>
        <th class="sortable" onclick="window.sortRequestsTable(1)">Model</th>
        <th class="sortable" onclick="window.sortRequestsTable(2)">Tokens</th>
        <th class="sortable" onclick="window.sortRequestsTable(3)">Cost</th>
        <th class="sortable" onclick="window.sortRequestsTable(4)">Duration</th>
      </tr>
    </thead>
  `
  table.appendChild(tbody)
  updateSortIndicators(table, sortState)
}

// Toggle detail row
export function toggleDetail(id) {
  const row = document.getElementById('detail-' + id)
  if (row) {
    const isHidden = row.style.display === 'none' || !row.style.display
    row.style.display = isHidden ? 'table-row' : 'none'

    // Track expanded state
    if (isHidden) {
      state.expandedRequests.add(id)
    } else {
      state.expandedRequests.delete(id)
    }
  }
}

// Filter requests (not currently used but kept for compatibility)
export function filterRequests(filters) {
  // This function is defined but filtering is now done server-side
  // Kept for potential client-side filtering in the future
  return state.requestsData
}
