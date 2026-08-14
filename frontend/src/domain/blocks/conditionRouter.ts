import {
  cleanName,
  isRecord,
  stringList,
  stringValue,
  uniqueStrings,
  type BlockDraftBase,
  type BlockPayloadBase,
} from './shared'

export interface ConditionRouterBranchDraft {
  _key: string
  key: string
  label: string
}

export interface ConditionRouterDraft extends BlockDraftBase {
  branches: ConditionRouterBranchDraft[]
  route_source: string
  python_requirements: string[]
  dependency_status: 'ready' | 'restart_required' | 'failed'
}

export type ConditionRouterDefaults = Omit<ConditionRouterDraft, 'id' | 'name' | 'dependency_status'>

interface ConditionRouterPayload extends BlockPayloadBase {
  branches: Array<{ key: string; label: string }>
  route_source: string
  python_requirements: string[]
}

let branchSequence = 0

function branchKey(): string {
  branchSequence += 1
  return `condition-router-branch-${branchSequence}`
}

function defaultsValue(defaults: ConditionRouterDefaults | undefined): ConditionRouterDefaults {
  return defaults ?? {
    branches: [{ _key: branchKey(), key: 'otherwise', label: 'Otherwise' }],
    route_source: 'async def route(state, context):\n    return {"activate": ["otherwise"], "update": {}}\n',
    python_requirements: [],
  }
}

export const conditionRouterAdapter = {
  blank(defaults?: ConditionRouterDefaults): ConditionRouterDraft {
    const value = defaultsValue(defaults)
    return {
      id: '',
      name: '',
      branches: value.branches.map((branch) => ({ ...branch, _key: branch._key || branchKey() })),
      route_source: value.route_source,
      python_requirements: [...value.python_requirements],
      dependency_status: 'ready',
    }
  },
  fromApi(value: unknown, defaults?: ConditionRouterDefaults): ConditionRouterDraft {
    const source = isRecord(value) ? value : {}
    const fallback = defaultsValue(defaults)
    const branches = Array.isArray(source.branches)
      ? source.branches.flatMap((item) => {
        if (!isRecord(item)) return []
        return [{
          _key: branchKey(),
          key: stringValue(item.key),
          label: stringValue(item.label),
        }]
      })
      : fallback.branches.map((branch) => ({ ...branch, _key: branch._key || branchKey() }))
    return {
      id: stringValue(source.id),
      name: stringValue(source.name),
      branches,
      route_source: stringValue(source.route_source, fallback.route_source),
      python_requirements: stringList(source.python_requirements),
      dependency_status: source.dependency_status === 'failed' || source.dependency_status === 'restart_required'
        ? source.dependency_status
        : 'ready',
    }
  },
  toPayload(value: ConditionRouterDraft): ConditionRouterPayload {
    return {
      name: cleanName(value.name),
      branches: value.branches.map(({ key, label }) => ({ key: key.trim(), label: label.trim() })),
      route_source: value.route_source,
      python_requirements: uniqueStrings(value.python_requirements),
    }
  },
}

export function newConditionRouterBranch(): ConditionRouterBranchDraft {
  return { _key: branchKey(), key: '', label: '' }
}
