// Main entry point - imports all modules and exposes functions to window

import { state } from './state.js'
import { showError, hideError, fetchWithErrorHandling, escapeHtml, copyToClipboard, getProviderColor } from './core.js'
import { toggleJson } from './utils.js'
import { loadModels, sortModelsTable, reloadModels } from './models.js'
import { loadRequests, toggleDetailView, toggleDetail, sortRequestsTable } from './requests.js'
import { refreshStats, filterRequests, sortByModelTable, sortByProviderTable, sortErrorsTable, clearErrors } from './stats.js'
import { showChartTooltip, hideChartTooltip, renderProviderTrends } from './charts.js'

// Alpine data reference
let alpineData = null

// Tab change handler
function onTabChange(tab) {
  if (tab === 'stats') refreshStats(alpineData, () => renderProviderTrends(alpineData))
  if (tab === 'models') loadModels()
  if (tab === 'requests') loadRequests(alpineData)
}

// Initialize when Alpine is ready
function initializeAlpine() {
  alpineData = Alpine.$data(document.body)
  // Trigger initial data load now that Alpine is ready
  const initialTab = localStorage.getItem('_x_currentTab')?.replace(/['"]/g, '') || 'stats'
  onTabChange(initialTab)
}

// Try both event names for compatibility
document.addEventListener('alpine:initialized', initializeAlpine)
document.addEventListener('alpine:init', () => {
  // Alpine:init fires before components are initialized, so we need to wait
  Alpine.nextTick(initializeAlpine)
})

// Fallback: if Alpine is already initialized, run immediately
if (typeof Alpine !== 'undefined' && Alpine.$data) {
  try {
    const testData = Alpine.$data(document.body)
    if (testData) {
      initializeAlpine()
    }
  } catch (e) {
    // Alpine not ready yet, will be initialized by event listener
  }
}

// Auto-refresh stats every 5 seconds (uses current filter state)
setInterval(() => {
  if (alpineData && alpineData.currentTab === 'stats') {
    refreshStats(alpineData, () => renderProviderTrends(alpineData))
  }
}, 5000)

// Handle browser back/forward navigation
window.addEventListener('popstate', () => {
  if (!alpineData) return
  const hash = window.location.hash.slice(1)
  if (hash && ['stats', 'models', 'requests'].includes(hash)) {
    alpineData.currentTab = hash
  } else if (!hash) {
    // No hash means navigate to default (stats)
    alpineData.currentTab = 'stats'
  }
})

// Expose functions to window for onclick handlers
window.showError = showError
window.hideError = hideError
window.escapeHtml = escapeHtml
window.copyToClipboard = copyToClipboard
window.getProviderColor = getProviderColor
window.toggleJson = toggleJson
window.loadModels = loadModels
window.sortModelsTable = sortModelsTable
window.reloadModels = reloadModels
window.loadRequests = () => loadRequests(alpineData)
window.toggleDetailView = toggleDetailView
window.toggleDetail = toggleDetail
window.sortRequestsTable = sortRequestsTable
window.refreshStats = () => refreshStats(alpineData, () => renderProviderTrends(alpineData))
window.filterRequests = (filters) => filterRequests(filters, alpineData)
window.sortByModelTable = sortByModelTable
window.sortByProviderTable = sortByProviderTable
window.sortErrorsTable = sortErrorsTable
window.clearErrors = () => clearErrors(() => refreshStats(alpineData, () => renderProviderTrends(alpineData)))
window.showChartTooltip = showChartTooltip
window.hideChartTooltip = hideChartTooltip
window.onTabChange = onTabChange

// Export for potential module usage
export {
  state,
  alpineData,
  onTabChange,
  showError,
  hideError,
  fetchWithErrorHandling,
  escapeHtml,
  copyToClipboard,
  getProviderColor,
  toggleJson,
  loadModels,
  sortModelsTable,
  reloadModels,
  loadRequests,
  toggleDetailView,
  toggleDetail,
  sortRequestsTable,
  refreshStats,
  filterRequests,
  sortByModelTable,
  sortByProviderTable,
  sortErrorsTable,
  clearErrors,
  showChartTooltip,
  hideChartTooltip,
  renderProviderTrends
}
