import type {
  LocalizedMessagePayload,
  PythonPackageFiles,
  PythonPackageManifest,
  PythonPackageReference,
  PythonPackageTemplate,
} from '@/api'

import { isRecord, stringValue } from './shared'

export interface PythonPackageDraftState {
  python_package: PythonPackageReference
  python_package_files: PythonPackageFiles
  python_package_manifest: PythonPackageManifest | null
  python_package_error: LocalizedMessagePayload | null
  dependency_status: 'ready' | 'restart_required' | 'failed' | ''
  editable_paths_source: string
}

export function blankPythonPackage(): PythonPackageDraftState {
  return {
    python_package: { folder: '', editable_files: ['main.py'] },
    python_package_files: {
      template_key: '',
      files: [{ path: 'main.py', content: '', exists: false }],
      revision: '',
    },
    python_package_manifest: null,
    python_package_error: null,
    dependency_status: '',
    editable_paths_source: 'main.py',
  }
}

export function pythonPackageFromApi(source: Record<string, unknown>): PythonPackageDraftState {
  const reference = isRecord(source.python_package) ? source.python_package : {}
  const files = isRecord(source.python_package_files) ? source.python_package_files : {}
  const editablePaths = Array.isArray(reference.editable_files)
    ? reference.editable_files.filter((value): value is string => typeof value === 'string')
    : ['main.py']
  const fileEntries = Array.isArray(files.files)
    ? files.files.flatMap((value) => {
      if (!isRecord(value) || typeof value.path !== 'string' || typeof value.content !== 'string') return []
      return [{
        path: value.path,
        content: value.content,
        exists: value.exists === true,
        readable: value.readable !== false,
      }]
    })
    : []
  const manifest = isRecord(source.python_package_manifest)
    ? source.python_package_manifest as unknown as PythonPackageManifest
    : null
  const status = stringValue(source.dependency_status)
  const packageError = isRecord(source.python_package_error)
    && typeof source.python_package_error.message_key === 'string'
    && isRecord(source.python_package_error.message_args)
    ? source.python_package_error as unknown as LocalizedMessagePayload
    : null
  return {
    python_package: {
      folder: stringValue(reference.folder),
      editable_files: editablePaths,
    },
    python_package_files: {
      template_key: '',
      files: editablePaths.map((path) => fileEntries.find((file) => file.path === path) ?? {
        path,
        content: '',
        exists: false,
        readable: true,
      }),
      revision: stringValue(files.revision),
    },
    python_package_manifest: manifest,
    python_package_error: packageError,
    dependency_status: status === 'ready' || status === 'restart_required' || status === 'failed'
      ? status
      : '',
    editable_paths_source: editablePaths.join('\n'),
  }
}

export function applyPythonPackageTemplate(
  target: PythonPackageDraftState,
  template: PythonPackageTemplate | undefined,
): void {
  if (!template) {
    Object.assign(target, blankPythonPackage())
    return
  }
  target.python_package = { folder: '', editable_files: ['main.py'] }
  target.python_package_files = {
    template_key: template.key,
    files: template.files.filter((file) => file.path === 'main.py'),
    revision: template.revision,
  }
  target.python_package_manifest = {
    format_version: template.format_version,
    id: '',
    family: template.family,
    adapter: template.adapter,
    folder: '',
  }
  target.python_package_error = null
  target.dependency_status = ''
  target.editable_paths_source = 'main.py'
}

export function pythonPackagePayload(value: PythonPackageDraftState): {
  python_package: PythonPackageReference
  python_package_files: PythonPackageFiles
} {
  return {
    python_package: {
      folder: value.python_package.folder,
      editable_files: [...value.python_package.editable_files],
    },
    python_package_files: {
      template_key: value.python_package_files.template_key,
      revision: value.python_package_files.revision,
      files: value.python_package_files.files.map((file) => ({
        path: file.path,
        content: file.content,
      })),
    },
  }
}
