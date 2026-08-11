import type { MiddlewareConfigSchema } from '@/api'

import {
  cleanName,
  identity,
  isRecord,
  stringValue,
  type BlockDraftBase,
  type BlockPayloadBase,
} from './shared'

interface MiddlewareDraftEntry {
  _key: string
  package_id: string
  enabled: boolean
  config: Record<string, unknown>
}

interface MiddlewareApiEntry {
  package_id: string
  enabled: boolean
  config: Record<string, unknown>
}

export interface CustomMiddlewareDraft extends BlockDraftBase {
  middlewares: MiddlewareDraftEntry[]
}

interface CustomMiddlewareApiRecord extends BlockDraftBase {
  middlewares: MiddlewareApiEntry[]
}

interface CustomMiddlewarePayload extends BlockPayloadBase {
  middlewares: MiddlewareApiEntry[]
}

export interface CustomMiddlewareCatalogItem {
  id: string
  name: string
  description: string
  config_schema: MiddlewareConfigSchema
  dependency_status: 'ready' | 'restart_required' | 'failed'
}

let middlewareEntrySequence = 0

function nextMiddlewareKey(): string {
  middlewareEntrySequence += 1
  return `middleware-entry-${middlewareEntrySequence}`
}

export function createMiddlewareEntry(value: Partial<MiddlewareApiEntry> = {}): MiddlewareDraftEntry {
  return {
    _key: nextMiddlewareKey(),
    package_id: value.package_id ?? '',
    enabled: value.enabled ?? true,
    config: { ...(value.config ?? {}) },
  }
}

export const customMiddlewareAdapter = {
  blank(): CustomMiddlewareDraft {
    return { id: '', name: '', middlewares: [] }
  },
  fromApi(value: CustomMiddlewareApiRecord): CustomMiddlewareDraft {
    return {
      ...identity(value),
      middlewares: Array.isArray(value.middlewares)
        ? value.middlewares.flatMap((entry) => isRecord(entry)
          ? [createMiddlewareEntry({
              package_id: stringValue(entry.package_id),
              enabled: typeof entry.enabled === 'boolean' ? entry.enabled : true,
              config: isRecord(entry.config) ? { ...entry.config } : {},
            })]
          : [])
        : [],
    }
  },
  toPayload(value: CustomMiddlewareDraft): CustomMiddlewarePayload {
    return {
      name: cleanName(value.name),
      middlewares: value.middlewares.map((entry) => ({
        package_id: entry.package_id.trim(),
        enabled: entry.enabled,
        config: { ...entry.config },
      })),
    }
  },
}
