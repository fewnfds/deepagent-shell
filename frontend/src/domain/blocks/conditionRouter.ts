import type { PythonPackageTemplate } from '@/api'

import {
  blankPythonPackage,
  pythonPackageFromApi,
  pythonPackagePayload,
  type PythonPackageDraftState,
} from './pythonPackage'
import { cleanName, identity, isRecord, type BlockDraftBase, type BlockPayloadBase } from './shared'

export interface ConditionRouterDraft extends BlockDraftBase, PythonPackageDraftState {}

export type ConditionRouterDefaults = Record<string, never>
export type ConditionRouterCatalogItem = PythonPackageTemplate

interface ConditionRouterPayload extends BlockPayloadBase {
  python_package: PythonPackageDraftState['python_package']
  python_package_files: PythonPackageDraftState['python_package_files']
}

export const conditionRouterAdapter = {
  blank(_defaults?: ConditionRouterDefaults): ConditionRouterDraft {
    return { id: '', name: '', ...blankPythonPackage() }
  },
  fromApi(value: unknown, _defaults?: ConditionRouterDefaults): ConditionRouterDraft {
    const source = isRecord(value) ? value : {}
    return {
      ...identity(source),
      ...pythonPackageFromApi(source),
    }
  },
  toPayload(value: ConditionRouterDraft): ConditionRouterPayload {
    return {
      name: cleanName(value.name),
      ...pythonPackagePayload(value),
    }
  },
}
