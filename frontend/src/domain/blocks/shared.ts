export interface BlockDraftBase {
  id: string
  name: string
}

export function cleanName(value: string): string {
  return value.trim()
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

export function stringValue(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

export function identity(value: unknown): BlockDraftBase {
  const source = isRecord(value) ? value : {}
  return { id: stringValue(source.id), name: stringValue(source.name) }
}
