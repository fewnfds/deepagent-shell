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
}

export function blankPythonPackage(): PythonPackageDraftState {
  return {
    python_package: { folder: '', config: {} },
    python_package_files: {
      template_key: '',
      main_source: '',
      requirements_source: '',
      revision: '',
    },
    python_package_manifest: null,
    python_package_error: null,
    dependency_status: '',
  }
}

export function pythonPackageFromApi(source: Record<string, unknown>): PythonPackageDraftState {
  const reference = isRecord(source.python_package) ? source.python_package : {}
  const files = isRecord(source.python_package_files) ? source.python_package_files : {}
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
      config: isRecord(reference.config) ? { ...reference.config } : {},
    },
    python_package_files: {
      template_key: '',
      main_source: stringValue(files.main_source),
      requirements_source: stringValue(files.requirements_source),
      revision: stringValue(files.revision),
    },
    python_package_manifest: manifest,
    python_package_error: packageError,
    dependency_status: status === 'ready' || status === 'restart_required' || status === 'failed'
      ? status
      : '',
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
  target.python_package = { folder: '', config: {} }
  target.python_package_files = {
    template_key: template.key,
    main_source: template.main_source,
    requirements_source: template.requirements_source,
    revision: template.revision,
  }
  target.python_package_manifest = {
    format_version: template.format_version,
    id: '',
    family: template.family,
    adapter: template.adapter,
    name: template.name,
    description: template.description,
    config_schema: template.config_schema,
    folder: '',
  }
  target.python_package_error = null
  target.dependency_status = ''
}

export function pythonPackagePayload(value: PythonPackageDraftState): {
  python_package: PythonPackageReference
  python_package_files: PythonPackageFiles
} {
  return {
    python_package: {
      folder: value.python_package.folder,
      config: { ...value.python_package.config },
    },
    python_package_files: { ...value.python_package_files },
  }
}
