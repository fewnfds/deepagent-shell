import type { PythonPackageTemplate } from '@/api'

import {
  blankPythonPackage,
  pythonPackageFromApi,
  pythonPackagePayload,
  type PythonPackageDraftState,
} from './pythonPackage'
import { cleanName, identity, isRecord, type BlockDraftBase, type BlockPayloadBase } from './shared'

export interface TaskDispatcherDraft extends BlockDraftBase, PythonPackageDraftState {}

export type TaskDispatcherDefaults = Record<string, never>
export type TaskDispatcherCatalogItem = PythonPackageTemplate

interface TaskDispatcherPayload extends BlockPayloadBase {
  python_package: PythonPackageDraftState['python_package']
  python_package_files: PythonPackageDraftState['python_package_files']
}

export const taskDispatcherAdapter = {
  blank(_defaults?: TaskDispatcherDefaults): TaskDispatcherDraft {
    return { id: '', name: '', ...blankPythonPackage() }
  },
  fromApi(value: unknown, _defaults?: TaskDispatcherDefaults): TaskDispatcherDraft {
    const source = isRecord(value) ? value : {}
    return {
      ...identity(source),
      ...pythonPackageFromApi(source),
    }
  },
  toPayload(value: TaskDispatcherDraft): TaskDispatcherPayload {
    return {
      name: cleanName(value.name),
      ...pythonPackagePayload(value),
    }
  },
}
