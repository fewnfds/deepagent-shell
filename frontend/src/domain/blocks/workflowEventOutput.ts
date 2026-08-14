import {
  cleanName,
  clone,
  identity,
  isRecord,
  type BlockDraftBase,
  type BlockPayloadBase,
} from './shared'

interface EventOutputScript {
  enabled: boolean
  output_source: string
}

interface WorkflowEventOutputValue {
  event_outputs: Record<string, EventOutputScript>
}

export interface WorkflowEventOutputDraft extends BlockDraftBase, WorkflowEventOutputValue {}
type WorkflowEventOutputApiRecord = WorkflowEventOutputDraft
interface WorkflowEventOutputPayload extends BlockPayloadBase, WorkflowEventOutputValue {}

export interface WorkflowEventOutputDefaults {
  events: Array<{ key: string; fields: string[] }>
  default_value: WorkflowEventOutputValue
}

export const workflowEventOutputAdapter = {
  blank(defaults: WorkflowEventOutputDefaults): WorkflowEventOutputDraft {
    return { id: '', name: '', ...clone(defaults.default_value) }
  },
  fromApi(
    value: WorkflowEventOutputApiRecord,
    defaults: WorkflowEventOutputDefaults,
  ): WorkflowEventOutputDraft {
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
    return { ...identity(value), event_outputs }
  },
  toPayload(value: WorkflowEventOutputDraft): WorkflowEventOutputPayload {
    return {
      name: cleanName(value.name),
      event_outputs: clone(value.event_outputs),
    }
  },
}
