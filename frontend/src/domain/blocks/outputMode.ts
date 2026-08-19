import {
  cleanName,
  clone,
  identity,
  isRecord,
  type BlockDraftBase,
  type BlockPayloadBase,
} from './shared'

interface OutputEventScript {
  enabled: boolean
  output_source: string
}

interface OutputModeValue {
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
      event_outputs,
    }
  },
  toPayload(value: OutputModeDraft): OutputModePayload {
    return {
      name: cleanName(value.name),
      event_outputs: clone(value.event_outputs),
    }
  },
}
