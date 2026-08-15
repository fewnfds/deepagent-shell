import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { PythonPackageConfigSchema } from '@/api'
import PythonPackageConfigForm from './PythonPackageConfigForm.vue'

const schema: PythonPackageConfigSchema = {
  type: 'object',
  properties: {
    label: {
      type: 'string',
      title: 'Transform',
      description: 'Edit messages.',
      default: '',
    },
    mode: {
      type: 'string',
      title: 'Mode',
      description: '',
      enum: ['all', 'latest'],
      default: 'all',
    },
    retries: {
      type: 'integer',
      title: 'Retries',
      description: '',
      minimum: 0,
      maximum: 10,
    },
    enabled: {
      type: 'boolean',
      title: 'Enabled',
      description: '',
      default: false,
    },
  },
  required: ['label'],
  additionalProperties: false,
}

describe('PythonPackageConfigForm', () => {
  it('renders controlled field types and emits structured values', async () => {
    const wrapper = mount(PythonPackageConfigForm, {
      props: {
        idPrefix: 'middleware-config',
        modelValue: { label: '', mode: 'all', enabled: false },
        schema,
      },
    })

    expect(wrapper.get('textarea').classes()).toContain('form-control')
    expect(wrapper.get('input[type="number"]').attributes('step')).toBe('1')
    expect(wrapper.get('input[type="checkbox"]').attributes('role')).toBe('switch')

    await wrapper.get('select').setValue('1')
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual({
      label: '',
      mode: 'latest',
      enabled: false,
    })
  })
})
