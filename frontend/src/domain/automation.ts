import type {
  AutomationPluginBinding,
  PeriodicAutomationPluginBinding,
  MainAgentAutomation,
} from '@/api'

export interface AutomationPluginBindingDraft {
  key: string
  plugin_id: string
  enabled: boolean
  config: Record<string, unknown>
}

export interface PeriodicAutomationPluginBindingDraft extends AutomationPluginBindingDraft {
  interval_seconds: number
}

export interface AutomationConfigurationDraft {
  hooks: AutomationPluginBindingDraft[]
  periodic: PeriodicAutomationPluginBindingDraft[]
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
    config: { ...record(source.config) },
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

function pluginPayload(value: AutomationPluginBindingDraft): AutomationPluginBinding {
  return {
    plugin_id: value.plugin_id,
    enabled: value.enabled,
    config: { ...value.config },
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

export function automationPayload(value: AutomationConfigurationDraft): MainAgentAutomation {
  return {
    hooks: value.hooks.map(pluginPayload),
    periodic: value.periodic.map(periodicPluginPayload),
  }
}
