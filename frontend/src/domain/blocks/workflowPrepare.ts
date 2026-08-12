import {
  cleanName,
  isRecord,
  stringList,
  stringValue,
  uniqueStrings,
  type BlockDraftBase,
  type BlockPayloadBase,
} from './shared'

export interface WorkflowPrepareDraft extends BlockDraftBase {
  enabled: boolean
  prepare_source: string
  python_requirements: string[]
  dependency_status: 'ready' | 'restart_required' | 'failed'
}

export type WorkflowPrepareDefaults = Omit<WorkflowPrepareDraft, 'id' | 'name' | 'dependency_status'>

interface WorkflowPreparePayload extends BlockPayloadBase {
  enabled: boolean
  prepare_source: string
  python_requirements: string[]
}

export const workflowPrepareAdapter = {
  blank(defaults: WorkflowPrepareDefaults): WorkflowPrepareDraft {
    return { id: '', name: '', ...defaults, python_requirements: [...defaults.python_requirements], dependency_status: 'ready' }
  },
  fromApi(value: unknown, defaults: WorkflowPrepareDefaults): WorkflowPrepareDraft {
    const source = isRecord(value) ? value : {}
    return {
      id: stringValue(source.id),
      name: stringValue(source.name),
      enabled: typeof source.enabled === 'boolean' ? source.enabled : defaults.enabled,
      prepare_source: stringValue(source.prepare_source, defaults.prepare_source),
      python_requirements: stringList(source.python_requirements),
      dependency_status: source.dependency_status === 'failed' || source.dependency_status === 'restart_required'
        ? source.dependency_status
        : 'ready',
    }
  },
  toPayload(value: WorkflowPrepareDraft): WorkflowPreparePayload {
    return {
      name: cleanName(value.name),
      enabled: value.enabled,
      prepare_source: value.prepare_source,
      python_requirements: uniqueStrings(value.python_requirements),
    }
  },
}
