import {
  cleanName,
  clone,
  identity,
  isRecord,
  type BlockDraftBase,
  type BlockPayloadBase,
} from './shared'

type OutputFilterMode = 'allowlist' | 'blocklist'
interface OutputFilterMapping {
  field: string
  value: string
}

interface OutputEventScript {
  enabled: boolean
  output_source: string
}

interface OutputModeValue {
  filter_mode: OutputFilterMode
  filter_mappings: OutputFilterMapping[]
  event_outputs: Record<string, OutputEventScript>
}

export interface OutputModeDraft extends BlockDraftBase, OutputModeValue {}
type OutputModeApiRecord = OutputModeDraft
interface OutputModePayload extends BlockPayloadBase, OutputModeValue {}

interface OutputEventDefault {
  key: string
  label?: string
  description?: string
  fields: string[]
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
    const outputs = isRecord(value.event_outputs) ? value.event_outputs : {}
    const event_outputs = Object.fromEntries(defaults.events.map((event) => {
      const fallback = defaults.default_value.event_outputs[event.key]
      const source = isRecord(outputs[event.key]) ? outputs[event.key] : {}
      return [event.key, {
        enabled: typeof source.enabled === 'boolean'
          ? source.enabled
          : fallback?.enabled ?? false,
        output_source: typeof source.output_source === 'string'
          ? source.output_source
          : fallback?.output_source ?? '',
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
      event_outputs,
    }
  },
  toPayload(value: OutputModeDraft): OutputModePayload {
    return {
      name: cleanName(value.name),
      filter_mode: value.filter_mode,
      filter_mappings: clone(value.filter_mappings),
      event_outputs: clone(value.event_outputs),
    }
  },
}
