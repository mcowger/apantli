// Statistics loading and rendering

import { state } from './state.js'
import { escapeHtml, getModelColor } from './core.js'
import { sortTable, applySortIfNeeded, updateSortIndicators } from './tables.js'

// Refresh stats (main stats tab data)
export async function refreshStats(alpineData, renderProviderTrends) {
  if (!alpineData) return
  const query = alpineData.buildQuery(alpineData.dateFilter)

  // Fetch stats and daily data in parallel for faster loading
  const [statsRes, _] = await Promise.all([
    fetch(`/stats${query}`),
    renderProviderTrends() // Start chart fetch in parallel
  ])
  const data = await statsRes.json()

  // Totals
  document.getElementById('totals').innerHTML = `
    <div class="metric">
      <div class="metric-value">${data.totals.requests}</div>
      <div class="metric-label">REQUESTS</div>
    </div>
    <div class="metric">
      <div class="metric-value">$${data.totals.cost.toFixed(4)}</div>
      <div class="metric-label">TOTAL COST</div>
    </div>
    <div class="metric">
      <div class="metric-value">${(data.totals.prompt_tokens + data.totals.completion_tokens).toLocaleString()}</div>
      <div class="metric-label">TOTAL TOKENS</div>
    </div>
    <div class="metric">
      <div class="metric-value">${data.totals.avg_duration_ms.toFixed(0)}ms</div>
      <div class="metric-label">AVG DURATION</div>
    </div>
  `

  // By model - convert to sortable format and merge with performance data
  const performanceMap = new Map((data.performance || []).map(p => [p.model, p]))

  state.byModelData = data.by_model.map(m => {
    const perf = performanceMap.get(m.model)
    return [
      m.model,                                    // 0: model
      m.requests,                                 // 1: requests
      m.cost,                                     // 2: cost
      m.tokens,                                   // 3: tokens
      m.cost / m.requests,                        // 4: avg cost per request
      m.tokens / m.requests,                      // 5: avg tokens per request
      perf ? perf.avg_tokens_per_sec : null,      // 6: speed (tokens/sec)
      perf ? perf.avg_duration_ms : null          // 7: avg duration
    ]
  })

  if (!state.tableSortState['by-model']) {
    state.tableSortState['by-model'] = { column: null, direction: null, originalData: [...state.byModelData] }
  } else {
    state.tableSortState['by-model'].originalData = [...state.byModelData]
  }
  renderByModelTable(applySortIfNeeded('by-model', state.byModelData), state.tableSortState['by-model'])

  // By provider - convert to sortable format
  state.byProviderData = data.by_provider.map(p => [p.provider, p.requests, p.cost, p.tokens])
  if (!state.tableSortState['by-provider']) {
    state.tableSortState['by-provider'] = { column: null, direction: null, originalData: [...state.byProviderData] }
  } else {
    state.tableSortState['by-provider'].originalData = [...state.byProviderData]
  }
  renderByProviderTable(applySortIfNeeded('by-provider', state.byProviderData), state.tableSortState['by-provider'])

  // Errors - convert to sortable format
  state.errorsData = data.recent_errors.map(e => [new Date(e.timestamp.endsWith('Z') || e.timestamp.includes('+') ? e.timestamp : e.timestamp + 'Z').getTime(), e.model, e.error, e.timestamp])
  if (!state.tableSortState['errors']) {
    state.tableSortState['errors'] = { column: null, direction: null, originalData: [...state.errorsData] }
  } else {
    state.tableSortState['errors'].originalData = [...state.errorsData]
  }
  renderErrorsTable(applySortIfNeeded('errors', state.errorsData), state.tableSortState['errors'])
}

// Navigate to requests tab with filters
export function filterRequests(filters, alpineData) {
  if (!alpineData) return

  // Set the filters
  Object.assign(alpineData.requestFilters, filters)

  // Switch to requests tab
  alpineData.currentTab = 'requests'
}

// Sort by model table
export function sortByModelTable(columnIndex) {
  sortTable('by-model', columnIndex, state.byModelData, renderByModelTable)
}

// Render by model table
function renderByModelTable(data, sortState) {
  // Find best performers
  const validCostPerRequest = data.filter(r => r[4] != null)
  const validTokensPerRequest = data.filter(r => r[5] != null)
  const validSpeed = data.filter(r => r[6] != null)

  const mostEconomical = validCostPerRequest.length > 0
    ? validCostPerRequest.reduce((min, curr) => curr[4] < min[4] ? curr : min)[0]
    : null
  const mostTokenRich = validTokensPerRequest.length > 0
    ? validTokensPerRequest.reduce((max, curr) => curr[5] > max[5] ? curr : max)[0]
    : null
  const fastest = validSpeed.length > 0
    ? validSpeed.reduce((max, curr) => curr[6] > max[6] ? curr : max)[0]
    : null

  const table = document.getElementById('by-model')
  table.innerHTML = `
    <thead>
      <tr>
        <th class="sortable" onclick="window.sortByModelTable(0)">Model</th>
        <th class="sortable" onclick="window.sortByModelTable(1)">Requests</th>
        <th class="sortable" onclick="window.sortByModelTable(2)">Total Cost</th>
        <th class="sortable" onclick="window.sortByModelTable(3)">Tokens</th>
        <th class="sortable" onclick="window.sortByModelTable(4)">$/Request</th>
        <th class="sortable" onclick="window.sortByModelTable(5)">Tokens/Req</th>
        <th class="sortable" onclick="window.sortByModelTable(6)">Speed</th>
        <th class="sortable" onclick="window.sortByModelTable(7)">Duration</th>
      </tr>
    </thead>
    <tbody>
      ${data.map(row => {
        const badges = []
        if (row[0] === mostEconomical) badges.push('<span class="badge badge-economical" onmouseover="window.showChartTooltip(event, \'Most Economical\', \'Lowest cost per request\', null)" onmouseout="window.hideChartTooltip()">$</span>')
        if (row[0] === mostTokenRich) badges.push('<span class="badge badge-tokens" onmouseover="window.showChartTooltip(event, \'Most Token-Rich\', \'Highest tokens per request\', null)" onmouseout="window.hideChartTooltip()">▰</span>')
        if (row[0] === fastest) badges.push('<span class="badge badge-speed" onmouseover="window.showChartTooltip(event, \'Fastest\', \'Highest tokens per second\', null)" onmouseout="window.hideChartTooltip()">⚡︎</span>')

        return `
        <tr class="clickable-row" onclick="window.filterRequests({ model: '${escapeHtml(row[0])}', provider: '', search: '', minCost: '', maxCost: '' })">
          <td>${escapeHtml(row[0])} ${badges.join(' ')}</td>
          <td>${row[1]}</td>
          <td>$${row[2].toFixed(4)}</td>
          <td>${row[3].toLocaleString()}</td>
          <td>$${row[4].toFixed(4)}</td>
          <td>${Math.round(row[5]).toLocaleString()}</td>
          <td>${row[6] != null ? row[6].toFixed(1) + ' tok/s' : '—'}</td>
          <td>${row[7] != null ? Math.round(row[7]) + 'ms' : '—'}</td>
        </tr>
      `}).join('')}
    </tbody>
  `
  updateSortIndicators(table, sortState)
}

// Sort by provider table
export function sortByProviderTable(columnIndex) {
  sortTable('by-provider', columnIndex, state.byProviderData, renderByProviderTable)
}

// Render by provider table
function renderByProviderTable(data, sortState) {
  const table = document.getElementById('by-provider')
  table.innerHTML = `
    <thead>
      <tr>
        <th class="sortable" onclick="window.sortByProviderTable(0)">Provider</th>
        <th class="sortable" onclick="window.sortByProviderTable(1)">Requests</th>
        <th class="sortable" onclick="window.sortByProviderTable(2)">Cost</th>
        <th class="sortable" onclick="window.sortByProviderTable(3)">Tokens</th>
      </tr>
    </thead>
    <tbody>
      ${data.map(row => `
        <tr class="clickable-row" onclick="window.filterRequests({ provider: '${escapeHtml(row[0])}', model: '', search: '', minCost: '', maxCost: '' })">
          <td>${row[0]}</td>
          <td>${row[1]}</td>
          <td>$${row[2].toFixed(4)}</td>
          <td>${row[3].toLocaleString()}</td>
        </tr>
      `).join('')}
    </tbody>
  `
  updateSortIndicators(table, sortState)
}

// Sort errors table
export function sortErrorsTable(columnIndex) {
  sortTable('errors', columnIndex, state.errorsData, renderErrorsTable)
}

// Render errors table
function renderErrorsTable(data, sortState) {
  const table = document.getElementById('errors')
  if (data.length === 0) {
    table.innerHTML = '<tr><td>No errors</td></tr>'
    return
  }

  table.innerHTML = `
    <thead>
      <tr>
        <th class="sortable" onclick="window.sortErrorsTable(0)">Time</th>
        <th class="sortable" onclick="window.sortErrorsTable(1)">Model</th>
        <th class="sortable" onclick="window.sortErrorsTable(2)">Error</th>
      </tr>
    </thead>
    <tbody>
      ${data.map(row => `
        <tr class="clickable-row" onclick="window.filterRequests({ model: '${escapeHtml(row[1])}', provider: '', search: '', minCost: '', maxCost: '' })">
          <td>${new Date(row[3].endsWith('Z') || row[3].includes('+') ? row[3] : row[3] + 'Z').toLocaleString()}</td>
          <td>${row[1]}</td>
          <td class="error">${row[2]}</td>
        </tr>
      `).join('')}
    </tbody>
  `
  updateSortIndicators(table, sortState)
}

// Clear all errors
export async function clearErrors(refreshStatsFn) {
  if (!confirm('Clear all errors from the database?')) return
  await fetch('/errors', { method: 'DELETE' })
  refreshStatsFn()
}
