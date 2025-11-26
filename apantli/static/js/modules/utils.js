// Shared utilities for request processing and content rendering

import { escapeHtml, copyToClipboard } from './core.js'

// Extract text from content (handles both string and multimodal array formats)
export function extractContentText(content) {
  if (!content) return ''

  // If content is a string, return as-is
  if (typeof content === 'string') {
    return content
  }

  // If content is an array (multimodal format), extract text parts
  if (Array.isArray(content)) {
    return content.map(part => {
      if (typeof part === 'string') return part
      if (part.type === 'text' && part.text) return part.text
      if (part.type === 'image_url') return '[Image]'
      return ''
    }).filter(Boolean).join('\n\n')
  }

  // Fallback for unexpected formats
  return String(content)
}

// Extract conversation messages from request/response
export function extractConversation(requestObj) {
  try {
    const request = JSON.parse(requestObj.request_data)
    const response = JSON.parse(requestObj.response_data)

    const messages = []

    // Extract request messages
    if (request.messages && Array.isArray(request.messages)) {
      request.messages.forEach(msg => {
        messages.push({
          role: msg.role,
          content: extractContentText(msg.content),
          isRequest: true
        })
      })
    }

    // Extract response message
    if (response.choices && response.choices[0] && response.choices[0].message) {
      const assistantMsg = response.choices[0].message
      messages.push({
        role: assistantMsg.role || 'assistant',
        content: extractContentText(assistantMsg.content),
        isRequest: false
      })
    }

    return messages
  } catch (e) {
    return null
  }
}

// Estimate token count for a message (rough approximation)
export function estimateTokens(text) {
  if (!text) return 0
  // Rough estimate: ~4 characters per token
  return Math.ceil(text.length / 4)
}

// Format message content with markdown-like code block detection
export function formatMessageContent(content) {
  if (!content) return ''

  // Escape HTML
  const escaped = escapeHtml(content)

  // Convert markdown code blocks to HTML
  let formatted = escaped.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
    return `<pre><code>${code.trim()}</code></pre>`
  })

  // Convert inline code
  formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>')

  return formatted
}

// Render conversation view
export function renderConversationView(requestObj) {
  const messages = extractConversation(requestObj)
  if (!messages) {
    return '<p class="error">Could not extract conversation from request/response data</p>'
  }

  let html = '<div class="conversation-view">'

  messages.forEach((msg, index) => {
    const icon = msg.role === 'user' ? '⊙' : msg.role === 'assistant' ? '◈' : '⚙'
    const roleLabel = msg.role.charAt(0).toUpperCase() + msg.role.slice(1)
    const tokens = estimateTokens(msg.content)
    const formattedContent = formatMessageContent(msg.content)

    html += `
      <div class="message">
        <div class="message-icon">${icon}</div>
        <div class="message-content">
          <div class="message-header">
            <div>
              <span class="message-role">${roleLabel}</span>
              <span class="message-meta">~${tokens.toLocaleString()} tokens</span>
            </div>
            <button class="copy-btn" onclick="window.copyToClipboard(\`${escapeHtml(msg.content).replace(/`/g, '\\`')}\`, this)">Copy</button>
          </div>
          <div class="message-text">${formattedContent}</div>
        </div>
      </div>
    `
  })

  html += '</div>'
  return html
}

// Render JSON tree with collapsible nodes
export function renderJsonTree(obj, isRoot = true) {
  if (obj === null) return '<span class="json-null">null</span>'
  if (obj === undefined) return '<span class="json-null">undefined</span>'

  const type = typeof obj
  if (type === 'string') return `<span class="json-string">"${escapeHtml(obj)}"</span>`
  if (type === 'number') return `<span class="json-number">${obj}</span>`
  if (type === 'boolean') return `<span class="json-boolean">${obj}</span>`

  if (Array.isArray(obj)) {
    if (obj.length === 0) return '<span>[]</span>'

    const id = 'json-' + Math.random().toString(36).substr(2, 9)
    let html = `<span class="json-toggle" onclick="window.toggleJson('${id}')">▼</span>[`
    html += `<div id="${id}" class="json-line">`
    obj.forEach((item, i) => {
      html += renderJsonTree(item, false)
      if (i < obj.length - 1) html += ','
      html += '<br>'
    })
    html += '</div>]'
    return html
  }

  if (type === 'object') {
    const keys = Object.keys(obj)
    if (keys.length === 0) return '<span>{}</span>'

    const id = 'json-' + Math.random().toString(36).substr(2, 9)
    let html = `<span class="json-toggle" onclick="window.toggleJson('${id}')">▼</span>{`
    html += `<div id="${id}" class="json-line">`
    keys.forEach((key, i) => {
      html += `<span class="json-key">"${escapeHtml(key)}"</span>: `
      html += renderJsonTree(obj[key], false)
      if (i < keys.length - 1) html += ','
      html += '<br>'
    })
    html += '</div>}'
    return html
  }

  return String(obj)
}

// Toggle JSON tree node
export function toggleJson(id) {
  const el = document.getElementById(id)
  const toggle = el.previousElementSibling
  if (el.classList.contains('json-collapsed')) {
    el.classList.remove('json-collapsed')
    toggle.textContent = '▼'
  } else {
    el.classList.add('json-collapsed')
    toggle.textContent = '▶'
  }
}