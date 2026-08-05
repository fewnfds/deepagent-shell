import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { AutomationConfigSchema } from '@/api'
import AutomationPluginConfigForm from './AutomationPluginConfigForm.vue'

const schema: AutomationConfigSchema = {
  type: 'object',
  properties: {
    transform_source: {
      type: 'string',
      title: 'Transform',
      description: 'Edit messages.',
      default: '',
      format: 'python',
      contentMediaType: 'text/x-python',
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
  required: ['transform_source'],
  additionalProperties: false,
}

describe('AutomationPluginConfigForm', () => {
  it('renders the controlled field types and emits structured values', async () => {
    const wrapper = mount(AutomationPluginConfigForm, {
      props: {
        idPrefix: 'plugin-config',
        modelValue: { transform_source: '', mode: 'all', enabled: false },
        schema,
      },
    })

    const source = wrapper.get('textarea')
    expect(source.attributes('rows')).toBe('1')
    expect(source.classes()).toContain('font-monospace')
    expect(wrapper.get('input[type="number"]').attributes('step')).toBe('1')
    expect(wrapper.get('input[type="checkbox"]').attributes('role')).toBe('switch')

    await wrapper.get('select').setValue('1')
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual({
      transform_source: '',
      mode: 'latest',
      enabled: false,
    })
  })
})
