import { describe, expect, it } from 'vitest'

import { blankAutoRoot, defaultAutoPublicId, normalizeAutoRoot } from './autos'

describe('auto domain adapters', () => {
  it('uses the auto public id namespace and a runnable script draft', () => {
    expect(defaultAutoPublicId('Default Route')).toBe('auto-default-route')
    expect(blankAutoRoot().source).toContain('def route(messages)')
  })

  it('normalizes incomplete server data with current defaults', () => {
    const normalized = normalizeAutoRoot({ id: 'auto-id', revision: 2, name: 'Route' })
    expect(normalized.id).toBe('auto-id')
    expect(normalized.revision).toBe(2)
    expect(normalized.source).toContain('workflow-example')
  })
})
