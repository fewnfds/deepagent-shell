import type { PythonPackageTemplate } from '@/api'

import {
  blankPythonPackage,
  pythonPackageFromApi,
  pythonPackagePayload,
  type PythonPackageDraftState,
} from './pythonPackage'
import { cleanName, identity, isRecord, type BlockDraftBase, type BlockPayloadBase } from './shared'

export interface WorkflowPrepareDraft extends BlockDraftBase, PythonPackageDraftState {}

export type WorkflowPrepareDefaults = Record<string, never>
export type WorkflowPrepareCatalogItem = PythonPackageTemplate

interface WorkflowPreparePayload extends BlockPayloadBase {
  python_package: PythonPackageDraftState['python_package']
  python_package_files: PythonPackageDraftState['python_package_files']
}

export const workflowPrepareAdapter = {
  blank(_defaults?: WorkflowPrepareDefaults): WorkflowPrepareDraft {
    return { id: '', name: '', ...blankPythonPackage() }
  },
  fromApi(value: unknown, _defaults?: WorkflowPrepareDefaults): WorkflowPrepareDraft {
    const source = isRecord(value) ? value : {}
    return {
      ...identity(source),
      ...pythonPackageFromApi(source),
    }
  },
  toPayload(value: WorkflowPrepareDraft): WorkflowPreparePayload {
    return {
      name: cleanName(value.name),
      ...pythonPackagePayload(value),
    }
  },
}
