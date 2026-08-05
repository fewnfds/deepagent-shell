import { describe, expect, it } from 'vitest'

import type { AutomationConfigSchema } from '@/api'
import { automationConfigDefaults } from './automationConfigSchema'

describe('automation config schema defaults', () => {
  it('materializes only explicitly declared defaults without losing false or zero', () => {
    const schema: AutomationConfigSchema = {
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

    expect(automationConfigDefaults(schema)).toEqual({
      source: '',
      enabled: false,
      attempts: 0,
    })
  })
})
