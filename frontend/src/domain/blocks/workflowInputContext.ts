import {
  cleanName,
  isRecord,
  stringList,
  stringValue,
  uniqueStrings,
  type BlockDraftBase,
  type BlockPayloadBase,
} from './shared'

export type WorkflowInputContextRole = 'user' | 'assistant' | 'system'
export type WorkflowInputContextScope = 'main_agent' | 'subagent'

export interface WorkflowInputContextSlotDraft {
  _key: string
  enabled: boolean
  role: WorkflowInputContextRole
  file: string
  fallback_files: string[]
  literal: string
  max_chars: number | null
  truncate_if_missing: boolean
}

export interface WorkflowInputContextDraft extends BlockDraftBase {
  enabled: boolean
  apply_to: WorkflowInputContextScope[]
  custom_transform_enabled: boolean
  custom_transform_source: string
  system_promote_enabled: boolean
  system_promote_min_chars: number
  demote_non_top_system: boolean
  slots: WorkflowInputContextSlotDraft[]
}

export interface WorkflowInputContextDefaults {
  enabled: boolean
  apply_to: WorkflowInputContextScope[]
  custom_transform_enabled: boolean
  custom_transform_source: string
  system_promote_enabled: boolean
  system_promote_min_chars: number
  demote_non_top_system: boolean
  slots: WorkflowInputContextSlotDraft[]
}

interface WorkflowInputContextPayload extends BlockPayloadBase {
  enabled: boolean
  apply_to: WorkflowInputContextScope[]
  custom_transform_enabled: boolean
  custom_transform_source: string
  system_promote_enabled: boolean
  system_promote_min_chars: number
  demote_non_top_system: boolean
  slots: Array<Omit<WorkflowInputContextSlotDraft, '_key' | 'file'> & { file: string | null }>
}

let workflowSlotSequence = 0

function nextWorkflowSlotKey(): string {
  workflowSlotSequence += 1
  return `workflow-input-slot-${workflowSlotSequence}`
}

function workflowSlotDraft(value: unknown): WorkflowInputContextSlotDraft {
  const source = isRecord(value) ? value : {}
  const role = source.role === 'user' || source.role === 'assistant' || source.role === 'system'
    ? source.role
    : 'system'
  const maxChars = typeof source.max_chars === 'number' && Number.isFinite(source.max_chars)
    ? source.max_chars
    : null
  return {
    _key: nextWorkflowSlotKey(),
    enabled: source.enabled !== false,
    role,
    file: stringValue(source.file),
    fallback_files: stringList(source.fallback_files),
    literal: stringValue(source.literal),
    max_chars: maxChars,
    truncate_if_missing: source.truncate_if_missing === true,
  }
}

function workflowSlots(value: unknown): WorkflowInputContextSlotDraft[] {
  return Array.isArray(value) ? value.map(workflowSlotDraft) : []
}

export const workflowInputContextAdapter = {
  blank(defaults: WorkflowInputContextDefaults): WorkflowInputContextDraft {
    return {
      id: '',
      name: '',
      enabled: defaults.enabled,
      apply_to: [...defaults.apply_to],
      custom_transform_enabled: defaults.custom_transform_enabled,
      custom_transform_source: defaults.custom_transform_source,
      system_promote_enabled: defaults.system_promote_enabled,
      system_promote_min_chars: defaults.system_promote_min_chars,
      demote_non_top_system: defaults.demote_non_top_system,
      slots: workflowSlots(defaults.slots),
    }
  },
  fromApi(value: unknown, defaults: WorkflowInputContextDefaults): WorkflowInputContextDraft {
    const source = isRecord(value) ? value : {}
    const applyTo = Array.isArray(source.apply_to)
      ? source.apply_to.filter((item): item is WorkflowInputContextScope => item === 'main_agent' || item === 'subagent')
      : [...defaults.apply_to]
    return {
      id: stringValue(source.id),
      name: stringValue(source.name),
      enabled: typeof source.enabled === 'boolean' ? source.enabled : defaults.enabled,
      apply_to: Array.isArray(source.apply_to)
        ? [...new Set(applyTo)]
        : [...defaults.apply_to],
      custom_transform_enabled: source.custom_transform_enabled === true,
      custom_transform_source: stringValue(source.custom_transform_source, defaults.custom_transform_source),
      system_promote_enabled: source.system_promote_enabled !== false,
      system_promote_min_chars: typeof source.system_promote_min_chars === 'number'
        ? source.system_promote_min_chars
        : defaults.system_promote_min_chars,
      demote_non_top_system: source.demote_non_top_system !== false,
      slots: workflowSlots(source.slots),
    }
  },
  toPayload(value: WorkflowInputContextDraft): WorkflowInputContextPayload {
    return {
      name: cleanName(value.name),
      enabled: value.enabled,
      apply_to: [...new Set(value.apply_to)],
      custom_transform_enabled: value.custom_transform_enabled,
      custom_transform_source: value.custom_transform_source,
      system_promote_enabled: value.system_promote_enabled,
      system_promote_min_chars: value.system_promote_min_chars,
      demote_non_top_system: value.demote_non_top_system,
      slots: value.slots.map((slot) => ({
        enabled: slot.enabled,
        role: slot.role,
        file: slot.file.trim() || null,
        fallback_files: uniqueStrings(slot.fallback_files),
        literal: slot.literal,
        max_chars: slot.max_chars,
        truncate_if_missing: slot.truncate_if_missing,
      })),
    }
  },
}
