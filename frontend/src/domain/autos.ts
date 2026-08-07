import type { AutoRoot, AutoRootDefinition } from '@/api'

export function defaultAutoPublicId(name: string): string {
  const slug = name.normalize('NFKD').replace(/[^\u0000-\u007F]/g, '').toLowerCase()
    .replace(/[^a-z]+/g, '-').replace(/^-+|-+$/g, '')
  return `auto-${slug || 'config'}`
}

export function blankAutoRoot(): AutoRootDefinition {
  return {
    public_id: '',
    name: '',
    source: "def route(messages):\n    return {'kind': 'workflow', 'public_id': 'workflow-example'}\n",
    enabled: true,
  }
}

export function normalizeAutoRoot(value: unknown): AutoRoot {
  const source = value && typeof value === 'object' ? value as Record<string, any> : {}
  return {
    ...blankAutoRoot(),
    ...source,
    id: typeof source.id === 'string' ? source.id : '',
    revision: typeof source.revision === 'number' ? source.revision : 0,
  }
}

