import {
  cleanName,
  isRecord,
  stringList,
  stringValue,
  uniqueStrings,
  type BlockDraftBase,
  type BlockPayloadBase,
} from './shared'

export interface SessionRecorderDraft extends BlockDraftBase {
  enabled: boolean
  custom_transform_enabled: boolean
  custom_transform_source: string
  python_requirements: string[]
  dependency_status: 'ready' | 'restart_required' | 'failed'
}

export type SessionRecorderDefaults = Omit<SessionRecorderDraft, 'id' | 'name' | 'dependency_status'>

interface SessionRecorderPayload extends BlockPayloadBase {
  enabled: boolean
  custom_transform_enabled: boolean
  custom_transform_source: string
  python_requirements: string[]
}

export const sessionRecorderAdapter = {
  blank(defaults: SessionRecorderDefaults): SessionRecorderDraft {
    return { id: '', name: '', ...defaults, python_requirements: [...defaults.python_requirements], dependency_status: 'ready' }
  },
  fromApi(value: unknown, defaults: SessionRecorderDefaults): SessionRecorderDraft {
    const source = isRecord(value) ? value : {}
    return {
      id: stringValue(source.id),
      name: stringValue(source.name),
      enabled: typeof source.enabled === 'boolean' ? source.enabled : defaults.enabled,
      custom_transform_enabled: source.custom_transform_enabled === true,
      custom_transform_source: stringValue(source.custom_transform_source, defaults.custom_transform_source),
      python_requirements: stringList(source.python_requirements),
      dependency_status: source.dependency_status === 'failed' || source.dependency_status === 'restart_required'
        ? source.dependency_status
        : 'ready',
    }
  },
  toPayload(value: SessionRecorderDraft): SessionRecorderPayload {
    return {
      name: cleanName(value.name),
      enabled: value.enabled,
      custom_transform_enabled: value.custom_transform_enabled,
      custom_transform_source: value.custom_transform_source,
      python_requirements: uniqueStrings(value.python_requirements),
    }
  },
}
