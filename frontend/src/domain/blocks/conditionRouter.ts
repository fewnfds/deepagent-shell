import {
  cleanName,
  isRecord,
  stringList,
  stringValue,
  uniqueStrings,
  type BlockDraftBase,
  type BlockPayloadBase,
} from './shared'

export interface ConditionRouterDraft extends BlockDraftBase {
  route_source: string
  python_requirements: string[]
  dependency_status: 'ready' | 'restart_required' | 'failed'
}

export type ConditionRouterDefaults = Omit<ConditionRouterDraft, 'id' | 'name' | 'dependency_status'>

interface ConditionRouterPayload extends BlockPayloadBase {
  route_source: string
  python_requirements: string[]
}

function defaultsValue(defaults: ConditionRouterDefaults | undefined): ConditionRouterDefaults {
  return defaults ?? {
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
      route_source: value.route_source,
      python_requirements: [...value.python_requirements],
      dependency_status: 'ready',
    }
  },
  fromApi(value: unknown, defaults?: ConditionRouterDefaults): ConditionRouterDraft {
    const source = isRecord(value) ? value : {}
    const fallback = defaultsValue(defaults)
    return {
      id: stringValue(source.id),
      name: stringValue(source.name),
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
      route_source: value.route_source,
      python_requirements: uniqueStrings(value.python_requirements),
    }
  },
}
