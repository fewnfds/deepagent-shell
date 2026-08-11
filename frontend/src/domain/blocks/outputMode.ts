import {
  cleanName,
  clone,
  identity,
  isRecord,
  type BlockDraftBase,
  type BlockPayloadBase,
} from './shared'

type OutputFilterMode = 'allowlist' | 'blocklist'
type OutputVariableEncoding = 'html' | 'plain'

interface OutputFilterMapping {
  field: string
  value: string
}

interface OutputEventTemplate {
  enabled: boolean
  template: string
}

interface OutputModeValue {
  filter_mode: OutputFilterMode
  filter_mappings: OutputFilterMapping[]
  variable_encoding: OutputVariableEncoding
  event_templates: Record<string, OutputEventTemplate>
}

export interface OutputModeDraft extends BlockDraftBase, OutputModeValue {}
type OutputModeApiRecord = OutputModeDraft
interface OutputModePayload extends BlockPayloadBase, OutputModeValue {}

interface OutputEventDefault {
  key: string
  label?: string
  description?: string
  variables: string[]
}

export interface OutputModeDefaults {
  events: OutputEventDefault[]
  filter_fields: string[]
  default_value: OutputModeValue
}

export const outputModeAdapter = {
  blank(defaults: OutputModeDefaults): OutputModeDraft {
    return { id: '', name: '', ...clone(defaults.default_value) }
  },
  fromApi(value: OutputModeApiRecord, defaults: OutputModeDefaults): OutputModeDraft {
    const templates = isRecord(value.event_templates) ? value.event_templates : {}
    const event_templates = Object.fromEntries(defaults.events.map((event) => {
      const fallback = defaults.default_value.event_templates[event.key]
      const source = isRecord(templates[event.key]) ? templates[event.key] : {}
      return [event.key, {
        enabled: typeof source.enabled === 'boolean'
          ? source.enabled
          : fallback?.enabled ?? false,
        template: typeof source.template === 'string'
          ? source.template
          : fallback?.template ?? '',
      }]
    }))
    return {
      ...identity(value),
      filter_mode: value.filter_mode === 'allowlist' || value.filter_mode === 'blocklist'
        ? value.filter_mode
        : defaults.default_value.filter_mode,
      filter_mappings: Array.isArray(value.filter_mappings)
        ? value.filter_mappings.flatMap((mapping) => isRecord(mapping)
          && typeof mapping.field === 'string'
          && typeof mapping.value === 'string'
          ? [{ field: mapping.field, value: mapping.value }]
          : [])
        : clone(defaults.default_value.filter_mappings),
      variable_encoding: value.variable_encoding === 'html' || value.variable_encoding === 'plain'
        ? value.variable_encoding
        : defaults.default_value.variable_encoding,
      event_templates,
    }
  },
  toPayload(value: OutputModeDraft): OutputModePayload {
    return {
      name: cleanName(value.name),
      filter_mode: value.filter_mode,
      filter_mappings: clone(value.filter_mappings),
      variable_encoding: value.variable_encoding,
      event_templates: clone(value.event_templates),
    }
  },
}
