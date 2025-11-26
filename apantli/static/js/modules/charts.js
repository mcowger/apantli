// Chart rendering for provider trends and usage visualization

import { escapeHtml, getProviderColor, getModelColor } from './core.js'

// Show chart tooltip
export function showChartTooltip(event, date, provider, cost) {
  const tooltip = document.getElementById('chart-tooltip')
  if (cost === null) {
    // Badge tooltip (date is title, provider is description)
    tooltip.innerHTML = `
      <div class="chart-tooltip-date">${date}</div>
      <div class="chart-tooltip-item">
        <span>${provider}</span>
      </div>
    `
  } else {
    // Chart tooltip (standard format)
    tooltip.innerHTML = `
      <div class="chart-tooltip-date">${date}</div>
      <div class="chart-tooltip-item">
        <span>${provider}:</span>
        <span>$${cost.toFixed(4)}</span>
      </div>
    `
  }
  tooltip.style.display = 'block'
  tooltip.style.left = (event.pageX + 10) + 'px'
  tooltip.style.top = (event.pageY - 30) + 'px'
}

// Hide chart tooltip
export function hideChartTooltip() {
  const tooltip = document.getElementById('chart-tooltip')
  tooltip.style.display = 'none'
}

// Render provider trends chart
export async function renderProviderTrends(alpineData) {
  if (!alpineData) return

  const container = document.getElementById('provider-trends-chart')
  const filter = alpineData.dateFilter

  // Detect single-day view (Today, Yesterday, or custom single-day range)
  const isSingleDay = filter.startDate && filter.endDate && filter.startDate === filter.endDate

  try {
    if (isSingleDay) {
      // Fetch hourly data for single-day view
      const timezoneOffset = -new Date().getTimezoneOffset()
      const res = await fetch(`/stats/hourly?date=${filter.startDate}&timezone_offset=${timezoneOffset}`)
      const data = await res.json()

      if (!data.hourly || data.hourly.length === 0) {
        container.innerHTML = '<div class="chart-empty">No data available for selected date</div>'
        return
      }

      renderHourlyChart(container, data.hourly, data.date)
    } else {
      // Fetch daily data for multi-day view
      const query = alpineData.buildQuery(filter)
      const res = await fetch(`/stats/daily${query}`)
      const data = await res.json()

      if (!data.daily || data.daily.length === 0) {
        container.innerHTML = '<div class="chart-empty">No data available for selected date range</div>'
        return
      }

      // Sort daily data by date ascending for proper line rendering
      const dailyData = data.daily.sort((a, b) => a.date.localeCompare(b.date))

      // Group data by model (includes provider for coloring)
      const modelData = {}
      dailyData.forEach(day => {
        day.by_model.forEach(m => {
          const modelKey = `${m.provider}:${m.model}`
          if (!modelData[modelKey]) {
            modelData[modelKey] = {
              provider: m.provider,
              model: m.model,
              data: []
            }
          }
          modelData[modelKey].data.push({
            date: day.date,
            cost: m.cost
          })
        })
      })

      // Fill in missing dates with 0 cost for each model
      const allDates = dailyData.map(d => d.date)
      Object.values(modelData).forEach(modelInfo => {
        const existingDates = new Set(modelInfo.data.map(d => d.date))
        allDates.forEach(date => {
          if (!existingDates.has(date)) {
            modelInfo.data.push({ date, cost: 0 })
          }
        })
        // Re-sort after filling gaps
        modelInfo.data.sort((a, b) => a.date.localeCompare(b.date))
      })

      // Sort models by total cost and assign colors
      const sortedModels = Object.values(modelData).sort((a, b) => {
        const aCost = a.data.reduce((sum, d) => sum + d.cost, 0)
        const bCost = b.data.reduce((sum, d) => sum + d.cost, 0)
        return bCost - aCost
      })

      // Group by provider and assign colors
      const modelsByProvider = {}
      sortedModels.forEach(m => {
        if (!modelsByProvider[m.provider]) {
          modelsByProvider[m.provider] = []
        }
        modelsByProvider[m.provider].push(m)
      })

      // Assign colors to models
      Object.entries(modelsByProvider).forEach(([provider, models]) => {
        models.forEach((m, index) => {
          m.color = getModelColor(provider, index, models.length)
        })
      })

      renderDailyChart(container, sortedModels, allDates)
    }
  } catch (e) {
    console.error('Failed to load provider trends:', e)
    container.innerHTML = '<div class="chart-empty">Failed to load chart data</div>'
  }
}

// Render hourly chart for single-day view
function renderHourlyChart(container, hourlyData, date) {
  const width = container.offsetWidth - 140 // Subtract container padding (60 + 80)
  const height = 260
  const margin = { top: 20, right: 0, bottom: 25, left: 0 }
  const chartWidth = width - margin.left - margin.right
  const chartHeight = height - margin.top - margin.bottom

  // Calculate max cost for scaling
  const maxCost = Math.max(...hourlyData.map(h => h.cost), 0.0001)
  const minCost = 0

  // Group data by model for stacked bars
  const modelTotals = {}
  hourlyData.forEach(hour => {
    hour.by_model.forEach(m => {
      const modelKey = `${m.provider}:${m.model}`
      if (!modelTotals[modelKey]) {
        modelTotals[modelKey] = {
          provider: m.provider,
          model: m.model,
          costs: new Array(24).fill(0)
        }
      }
      modelTotals[modelKey].costs[hour.hour] = m.cost
    })
  })

  // Sort models by total cost and assign colors
  const sortedModels = Object.values(modelTotals).sort((a, b) => {
    const aCost = a.costs.reduce((sum, c) => sum + c, 0)
    const bCost = b.costs.reduce((sum, c) => sum + c, 0)
    return bCost - aCost
  })

  // Group by provider and assign colors
  const modelsByProvider = {}
  sortedModels.forEach(m => {
    if (!modelsByProvider[m.provider]) {
      modelsByProvider[m.provider] = []
    }
    modelsByProvider[m.provider].push(m)
  })

  Object.entries(modelsByProvider).forEach(([provider, models]) => {
    models.forEach((m, index) => {
      m.color = getModelColor(provider, index, models.length)
    })
  })
  const barWidth = chartWidth / 24

  // Y scale: cost to pixel (inverted because SVG Y increases downward)
  const yScale = (cost) => chartHeight - ((cost - minCost) / (maxCost - minCost)) * chartHeight

  // Format hour for display (0-23 to "12am", "1am", ... "11pm")
  const formatHour = (hour) => {
    if (hour === 0) return '12am'
    if (hour < 12) return hour + 'am'
    if (hour === 12) return '12pm'
    return (hour - 12) + 'pm'
  }

  // Create SVG
  let svg = `
    <svg class="chart-svg" viewBox="0 0 ${width} ${height + 40}" xmlns="http://www.w3.org/2000/svg">
      <g transform="translate(${margin.left}, ${margin.top})">
  `

  // Add grid lines
  const gridSteps = 5
  for (let i = 0; i <= gridSteps; i++) {
    const y = (i / gridSteps) * chartHeight
    svg += `<line class="chart-grid" x1="0" y1="${y}" x2="${chartWidth}" y2="${y}" />`
  }

  // Add Y axis
  svg += `<line class="chart-axis" x1="0" y1="0" x2="0" y2="${chartHeight}" />`
  for (let i = 0; i <= gridSteps; i++) {
    const y = (i / gridSteps) * chartHeight
    const cost = maxCost - (i / gridSteps) * (maxCost - minCost)
    svg += `<text class="chart-axis-text" x="-10" y="${y + 4}" text-anchor="end">$${cost.toFixed(3)}</text>`
  }

  // Add X axis
  svg += `<line class="chart-axis" x1="0" y1="${chartHeight}" x2="${chartWidth}" y2="${chartHeight}" />`

  // Add X axis labels (show every 3 hours to avoid crowding: 0, 3, 6, 9, 12, 15, 18, 21)
  for (let hour = 0; hour < 24; hour += 3) {
    const x = hour * barWidth + barWidth / 2
    svg += `<text class="chart-axis-text" x="${x}" y="${chartHeight + 20}" text-anchor="middle">${formatHour(hour)}</text>`
  }

  // Draw stacked bars for each hour
  for (let hour = 0; hour < 24; hour++) {
    const x = hour * barWidth
    let yOffset = chartHeight
    const hourLabel = formatHour(hour)

    sortedModels.forEach(modelInfo => {
      const cost = modelInfo.costs[hour]
      if (cost > 0) {
        const barHeight = chartHeight - yScale(cost)
        yOffset -= barHeight
        const modelLabel = escapeHtml(modelInfo.model)
        svg += `<rect class="chart-bar" x="${x + 2}" y="${yOffset}" width="${barWidth - 4}" height="${barHeight}" fill="${modelInfo.color}"
                     onmouseover="window.showChartTooltip(event, '${hourLabel}', '${modelLabel}', ${cost})"
                     onmouseout="window.hideChartTooltip()" />`
      }
    })
  }

  // Add legend grouped by provider
  let legendY = 0
  const legendX = chartWidth + 10

  Object.entries(modelsByProvider).forEach(([provider, models]) => {
    // Add provider name
    svg += `<text class="chart-legend-text" x="${legendX}" y="${legendY + 8}" style="font-weight: bold;">${provider}</text>`
    legendY += 18

    // Add models for this provider
    models.forEach(m => {
      svg += `
        <circle cx="${legendX}" cy="${legendY + 4}" r="4" fill="${m.color}" />
        <text class="chart-legend-text" x="${legendX + 10}" y="${legendY + 8}">${escapeHtml(m.model)}</text>
      `
      legendY += 16
    })

    legendY += 4 // Extra space between providers
  })

  svg += `
      </g>
    </svg>
  `

  // Display date as title
  const dateObj = new Date(date + 'T00:00:00')
  const dateStr = dateObj.toLocaleDateString('en-US', { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' })

  container.innerHTML = `
    <div class="chart-title">Hourly Usage - ${dateStr}</div>
    ${svg}
  `
}

// Render daily chart for multi-day view
function renderDailyChart(container, modelData, dates) {
  const width = container.offsetWidth - 140 // Subtract container padding (60 + 80)
  const height = 260
  const margin = { top: 20, right: 0, bottom: 25, left: 0 }
  const chartWidth = width - margin.left - margin.right
  const chartHeight = height - margin.top - margin.bottom

  // Calculate scales
  const maxCost = Math.max(...modelData.flatMap(m => m.data.map(d => d.cost)), 0.0001)
  const minCost = 0

  // Calculate bar width based on number of dates
  const barWidth = chartWidth / dates.length

  // Y scale: cost to pixel (inverted because SVG Y increases downward)
  const yScale = (cost) => chartHeight - ((cost - minCost) / (maxCost - minCost)) * chartHeight

  // Format date for display
  const formatDate = (dateStr) => {
    const date = new Date(dateStr + 'T00:00:00')
    return `${date.getMonth() + 1}/${date.getDate()}`
  }

  // Create SVG
  let svg = `
    <svg class="chart-svg" viewBox="0 0 ${width} ${height + 40}" xmlns="http://www.w3.org/2000/svg">
      <g transform="translate(${margin.left}, ${margin.top})">
  `

  // Add grid lines
  const gridSteps = 5
  for (let i = 0; i <= gridSteps; i++) {
    const y = (i / gridSteps) * chartHeight
    svg += `<line class="chart-grid" x1="0" y1="${y}" x2="${chartWidth}" y2="${y}" />`
  }

  // Add Y axis
  svg += `<line class="chart-axis" x1="0" y1="0" x2="0" y2="${chartHeight}" />`
  for (let i = 0; i <= gridSteps; i++) {
    const y = (i / gridSteps) * chartHeight
    const cost = maxCost - (i / gridSteps) * (maxCost - minCost)
    svg += `<text class="chart-axis-text" x="-10" y="${y + 4}" text-anchor="end">$${cost.toFixed(3)}</text>`
  }

  // Add X axis
  svg += `<line class="chart-axis" x1="0" y1="${chartHeight}" x2="${chartWidth}" y2="${chartHeight}" />`

  // Add X axis labels (show fewer labels to avoid crowding)
  const labelStep = Math.ceil(dates.length / 8)
  dates.forEach((date, i) => {
    if (i % labelStep === 0 || i === dates.length - 1) {
      const x = i * barWidth + barWidth / 2
      svg += `<text class="chart-axis-text" x="${x}" y="${chartHeight + 20}" text-anchor="middle">${formatDate(date)}</text>`
    }
  })

  // Draw stacked bars for each date
  dates.forEach((date, dateIndex) => {
    const x = dateIndex * barWidth
    let yOffset = chartHeight
    const dateLabel = formatDate(date)

    // Stack bars from each model for this date
    modelData.forEach(modelInfo => {
      const dataPoint = modelInfo.data[dateIndex]
      if (dataPoint && dataPoint.cost > 0) {
        const barHeight = chartHeight - yScale(dataPoint.cost)
        yOffset -= barHeight
        const modelLabel = escapeHtml(modelInfo.model)
        svg += `<rect class="chart-bar" x="${x + 2}" y="${yOffset}" width="${barWidth - 4}" height="${barHeight}" fill="${modelInfo.color}"
                     onmouseover="window.showChartTooltip(event, '${dateLabel}', '${modelLabel}', ${dataPoint.cost})"
                     onmouseout="window.hideChartTooltip()" />`
      }
    })
  })

  svg += `
      </g>
    </svg>
  `

  // Add legend grouped by provider
  const modelsByProvider = {}
  modelData.forEach(m => {
    if (!modelsByProvider[m.provider]) {
      modelsByProvider[m.provider] = []
    }
    modelsByProvider[m.provider].push(m)
  })

  let legend = ''
  Object.entries(modelsByProvider).forEach(([provider, models]) => {
    // Create provider section as a grid item
    legend += `<div class="chart-legend-provider">`
    legend += `<div class="chart-legend-provider-name">${provider}</div>`

    // Add models for this provider
    models.forEach(m => {
      const totalCost = m.data.reduce((sum, d) => sum + d.cost, 0)
      legend += `
        <div class="chart-legend-item">
          <div class="chart-legend-color" style="background: ${m.color}"></div>
          <div class="chart-legend-label">${escapeHtml(m.model)} ($${totalCost.toFixed(4)})</div>
        </div>
      `
    })
    legend += `</div>`
  })

  container.innerHTML = svg + `<div class="chart-legend">${legend}</div>`
}
