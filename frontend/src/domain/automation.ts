import type {
  AutomationPluginBinding,
  PrimaryAutomation,
  SubagentAutomation,
} from '@/api'

export interface AutomationPluginBindingDraft {
  key: string
  plugin_id: string
  enabled: boolean
  config_text: string
}

export interface AutomationConfigurationDraft {
  plugins: AutomationPluginBindingDraft[]
  lifecycle_interval_seconds: number | null
}

export interface SubagentAutomationDraft extends AutomationConfigurationDraft {
  mode: 'inherit' | 'replace' | 'disabled'
}

let bindingSequence = 0

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function bindingDraft(value: unknown = {}): AutomationPluginBindingDraft {
  const source = record(value)
  bindingSequence += 1
  return {
    key: `automation-plugin-${bindingSequence}`,
    plugin_id: text(source.plugin_id),
    enabled: source.enabled !== false,
    config_text: JSON.stringify(record(source.config), null, 2),
  }
}

export function blankAutomationPluginBinding(): AutomationPluginBindingDraft {
  return bindingDraft()
}

export function normalizeAutomation(value: unknown): AutomationConfigurationDraft {
  const source = record(value)
  const plugins = Array.isArray(source.plugins) ? source.plugins : []
  const interval = source.lifecycle_interval_seconds
  return {
    plugins: plugins.map(bindingDraft),
    lifecycle_interval_seconds: typeof interval === 'number' ? interval : null,
  }
}

export function normalizeSubagentAutomation(value: unknown): SubagentAutomationDraft {
  const source = record(value)
  const mode = source.mode
  return {
    mode: mode === 'replace' || mode === 'disabled' ? mode : 'inherit',
    ...normalizeAutomation(source),
  }
}

function parseConfig(value: string): Record<string, unknown> {
  const parsed: unknown = JSON.parse(value)
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Plugin config must be a JSON object.')
  }
  return parsed as Record<string, unknown>
}

function pluginPayload(value: AutomationPluginBindingDraft): AutomationPluginBinding {
  return {
    plugin_id: value.plugin_id,
    enabled: value.enabled,
    config: parseConfig(value.config_text),
  }
}

export function automationPayload(value: AutomationConfigurationDraft): PrimaryAutomation {
  return {
    plugins: value.plugins.map(pluginPayload),
    lifecycle_interval_seconds: value.lifecycle_interval_seconds,
  }
}

export function subagentAutomationPayload(value: SubagentAutomationDraft): SubagentAutomation {
  if (value.mode !== 'replace') {
    return { mode: value.mode, plugins: [], lifecycle_interval_seconds: null }
  }
  return { mode: 'replace', ...automationPayload(value) }
}
