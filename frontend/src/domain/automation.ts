import type {
  AutomationPluginBinding,
  PeriodicAutomationPluginBinding,
  PrimaryAutomation,
  SubagentAutomation,
} from '@/api'

export interface AutomationPluginBindingDraft {
  key: string
  plugin_id: string
  enabled: boolean
  config_text: string
}

export interface PeriodicAutomationPluginBindingDraft extends AutomationPluginBindingDraft {
  interval_seconds: number
}

export interface AutomationConfigurationDraft {
  hooks: AutomationPluginBindingDraft[]
  periodic: PeriodicAutomationPluginBindingDraft[]
}

interface AutomationOverrideDraft<TBinding> {
  mode: 'inherit' | 'replace' | 'disabled'
  plugins: TBinding[]
}

export interface SubagentAutomationDraft {
  hooks: AutomationOverrideDraft<AutomationPluginBindingDraft>
  periodic: AutomationOverrideDraft<PeriodicAutomationPluginBindingDraft>
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

function periodicBindingDraft(value: unknown = {}): PeriodicAutomationPluginBindingDraft {
  const source = record(value)
  return {
    ...bindingDraft(source),
    interval_seconds: typeof source.interval_seconds === 'number'
      ? source.interval_seconds
      : 2,
  }
}

export function blankAutomationPluginBinding(): AutomationPluginBindingDraft {
  return bindingDraft()
}

export function blankPeriodicAutomationPluginBinding(): PeriodicAutomationPluginBindingDraft {
  return periodicBindingDraft()
}

export function normalizeAutomation(value: unknown): AutomationConfigurationDraft {
  const source = record(value)
  const hooks = Array.isArray(source.hooks) ? source.hooks : []
  const periodic = Array.isArray(source.periodic) ? source.periodic : []
  return {
    hooks: hooks.map(bindingDraft),
    periodic: periodic.map(periodicBindingDraft),
  }
}

function overrideMode(value: unknown): 'inherit' | 'replace' | 'disabled' {
  return value === 'replace' || value === 'disabled' ? value : 'inherit'
}

export function normalizeSubagentAutomation(value: unknown): SubagentAutomationDraft {
  const source = record(value)
  const hooks = record(source.hooks)
  const periodic = record(source.periodic)
  return {
    hooks: {
      mode: overrideMode(hooks.mode),
      plugins: (Array.isArray(hooks.plugins) ? hooks.plugins : []).map(bindingDraft),
    },
    periodic: {
      mode: overrideMode(periodic.mode),
      plugins: (Array.isArray(periodic.plugins) ? periodic.plugins : [])
        .map(periodicBindingDraft),
    },
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

function periodicPluginPayload(
  value: PeriodicAutomationPluginBindingDraft,
): PeriodicAutomationPluginBinding {
  return {
    ...pluginPayload(value),
    interval_seconds: value.interval_seconds,
  }
}

export function automationPayload(value: AutomationConfigurationDraft): PrimaryAutomation {
  return {
    hooks: value.hooks.map(pluginPayload),
    periodic: value.periodic.map(periodicPluginPayload),
  }
}

export function subagentAutomationPayload(value: SubagentAutomationDraft): SubagentAutomation {
  return {
    hooks: {
      mode: value.hooks.mode,
      plugins: value.hooks.mode === 'replace' ? value.hooks.plugins.map(pluginPayload) : [],
    },
    periodic: {
      mode: value.periodic.mode,
      plugins: value.periodic.mode === 'replace'
        ? value.periodic.plugins.map(periodicPluginPayload)
        : [],
    },
  }
}
