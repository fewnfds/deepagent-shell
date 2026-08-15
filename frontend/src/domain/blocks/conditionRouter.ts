import type { PythonPackageConfigSchema } from '@/api'

import { cleanName, isRecord, stringValue, type BlockDraftBase, type BlockPayloadBase } from './shared'

export interface ConditionRouterDraft extends BlockDraftBase {
  python_package_bindings: ConditionRouterPackageBindingDraft[]
}

export interface ConditionRouterPackageBindingDraft {
  package_id: string
  enabled: boolean
  config: Record<string, unknown>
}

export type ConditionRouterDefaults = Omit<ConditionRouterDraft, 'id' | 'name'>

interface ConditionRouterPayload extends BlockPayloadBase {
  python_package_bindings: ConditionRouterPackageBindingDraft[]
}

export interface ConditionRouterCatalogItem {
  id: string
  name: string
  description: string
  config_schema: PythonPackageConfigSchema
  dependency_status: 'ready' | 'restart_required' | 'failed'
}

function bindingValue(value: unknown): ConditionRouterPackageBindingDraft[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((entry) => isRecord(entry) ? [{
    package_id: stringValue(entry.package_id),
    enabled: typeof entry.enabled === 'boolean' ? entry.enabled : true,
    config: isRecord(entry.config) ? { ...entry.config } : {},
  }] : [])
}

function bindingsFrom(defaults: ConditionRouterDefaults | undefined): ConditionRouterPackageBindingDraft[] {
  return bindingValue(defaults?.python_package_bindings)
}

export const conditionRouterAdapter = {
  blank(defaults?: ConditionRouterDefaults): ConditionRouterDraft {
    return {
      id: '',
      name: '',
      python_package_bindings: bindingsFrom(defaults),
    }
  },
  fromApi(value: unknown, defaults?: ConditionRouterDefaults): ConditionRouterDraft {
    const source = isRecord(value) ? value : {}
    return {
      id: stringValue(source.id),
      name: stringValue(source.name),
      python_package_bindings: bindingValue(
        source.python_package_bindings ?? defaults?.python_package_bindings,
      ),
    }
  },
  toPayload(value: ConditionRouterDraft): ConditionRouterPayload {
    return {
      name: cleanName(value.name),
      python_package_bindings: value.python_package_bindings.map((binding) => ({
        package_id: binding.package_id.trim(),
        enabled: binding.enabled,
        config: { ...binding.config },
      })),
    }
  }
}
