// Core utilities and error handling

export function showError(message) {
  const errorBanner = document.getElementById('error-banner')
  errorBanner.textContent = message
  errorBanner.style.display = 'block'
  setTimeout(() => {
    errorBanner.style.display = 'none'
  }, 5000)
}

export function hideError() {
  const errorBanner = document.getElementById('error-banner')
  errorBanner.style.display = 'none'
}

export async function fetchWithErrorHandling(url) {
  try {
    const res = await fetch(url)
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`)
    return await res.json()
  } catch (err) {
    showError(`Failed to load data: ${err.message}`)
    return null
  }
}

export function escapeHtml(text) {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}

export function formatDate(date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function getCostColor(cost, maxCost) {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark'

  if (cost === 0) {
    return isDark ? '#2a2a2a' : '#f0f0f0'
  }

  const ratio = Math.min(cost / (maxCost || 1), 1)

  if (isDark) {
    // Dark mode: darker blues with less saturation
    const lightness = 25 + (ratio * 25) // 25% to 50%
    const saturation = 60 + (ratio * 20) // 60% to 80%
    return `hsl(210, ${saturation}%, ${lightness}%)`
  } else {
    // Light mode: lighter blues
    const lightness = 100 - (ratio * 50) // 100% to 50%
    return `hsl(210, 100%, ${lightness}%)`
  }
}

export function copyToClipboard(text, button) {
  navigator.clipboard.writeText(text).then(() => {
    const originalText = button.textContent
    button.textContent = 'Copied!'
    setTimeout(() => {
      button.textContent = originalText
    }, 1500)
  }).catch(err => {
    console.error('Failed to copy:', err)
  })
}

// Provider colors (shared with bar chart)
const PROVIDER_COLORS = {
  'openai': '#10a37f',
  'anthropic': '#d97757',
  'google': '#4285f4',
  'default': '#999999'
}

export function getProviderColor(provider) {
  return PROVIDER_COLORS[provider] || PROVIDER_COLORS.default
}

// Generate color tints for models within a provider
export function getModelColor(provider, modelIndex, totalModels) {
  const baseColor = getProviderColor(provider)

  // Parse hex color to RGB
  const r = parseInt(baseColor.slice(1, 3), 16)
  const g = parseInt(baseColor.slice(3, 5), 16)
  const b = parseInt(baseColor.slice(5, 7), 16)

  // Generate tint: darker for first model, lighter for subsequent
  // Lightness range: 0% (darkest) to 75% (lightest)
  const lightness = totalModels === 1 ? 0 : (modelIndex / (totalModels - 1)) * 0.75

  // Mix with white to create tint
  const nr = Math.round(r + (255 - r) * lightness)
  const ng = Math.round(g + (255 - g) * lightness)
  const nb = Math.round(b + (255 - b) * lightness)

  return `#${nr.toString(16).padStart(2, '0')}${ng.toString(16).padStart(2, '0')}${nb.toString(16).padStart(2, '0')}`
}
