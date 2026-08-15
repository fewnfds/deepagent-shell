import { describe, expect, it } from 'vitest'

import type { PythonPackageConfigSchema } from '@/api'
import { pythonPackageConfigDefaults } from './pythonPackageConfigSchema'

describe('Python package config schema defaults', () => {
  it('materializes only declared defaults without losing false or zero', () => {
    const schema: PythonPackageConfigSchema = {
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

    expect(pythonPackageConfigDefaults(schema)).toEqual({
      source: '',
      enabled: false,
      attempts: 0,
    })
  })
})
