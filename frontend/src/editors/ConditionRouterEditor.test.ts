import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { describe, expect, it } from 'vitest'

import { conditionRouterAdapter } from '@/domain/blocks'
import { en } from '@/locales/en'

import ConditionRouterEditor from './ConditionRouterEditor.vue'

describe('ConditionRouterEditor', () => {
  it('binds one adapter package and emits manifest config defaults', async () => {
    const packageId = '11111111-1111-4111-8111-111111111111'
    const wrapper = mount(ConditionRouterEditor, {
      props: {
        modelValue: conditionRouterAdapter.blank({ python_package_bindings: [] }),
        catalog: [{
          id: packageId,
          name: 'Threshold router',
          description: '',
          dependency_status: 'ready',
          config_schema: {
            type: 'object',
            properties: {
              threshold: {
                type: 'integer',
                title: 'Threshold',
                description: '',
                default: 80,
              },
            },
            required: ['threshold'],
            additionalProperties: false,
          },
        }],
      },
      global: {
        plugins: [createI18n({
          legacy: false,
          locale: 'en',
          messages: { en },
        })],
      },
    })

    await wrapper.get('select').setValue(packageId)

    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({
      python_package_bindings: [{
        package_id: packageId,
        enabled: true,
        config: { threshold: 80 },
      }],
    })
    expect(wrapper.get('input[type="number"]').element.value).toBe('80')
  })
})
