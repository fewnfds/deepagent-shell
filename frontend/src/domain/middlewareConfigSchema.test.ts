import { describe, expect, it } from 'vitest'

import type { MiddlewareConfigSchema } from '@/api'
import { middlewareConfigDefaults } from './middlewareConfigSchema'

describe('Middleware config schema defaults', () => {
  it('materializes only declared defaults without losing false or zero', () => {
    const schema: MiddlewareConfigSchema = {
      type: 'object',
      properties: {
        source: { type: 'string', title: 'Source', description: '', default: '' },
        enabled: { type: 'boolean', title: 'Enabled', description: '', default: false },
        attempts: { type: 'integer', title: 'Attempts', description: '', default: 0 },
        optional: { type: 'string', title: 'Optional', description: '' },
      },
      required: [],
      additionalProperties: false,
    }

    expect(middlewareConfigDefaults(schema)).toEqual({
      source: '',
      enabled: false,
      attempts: 0,
    })
  })
})
