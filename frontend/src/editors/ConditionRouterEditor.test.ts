import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { describe, expect, it } from 'vitest'

import { conditionRouterAdapter } from '@/domain/blocks'
import { en } from '@/locales/en'

import ConditionRouterEditor from './ConditionRouterEditor.vue'

describe('ConditionRouterEditor', () => {
  it('binds one adapter package and emits manifest config defaults', async () => {
    const templateKey = 'threshold-router'
    const wrapper = mount(ConditionRouterEditor, {
      props: {
        modelValue: conditionRouterAdapter.blank(),
        catalog: [{
          key: templateKey,
          format_version: 1,
          family: 'workflow-node',
          adapter: 'condition-router',
          name: 'Threshold router',
          description: '',
          main_source: 'def create_router(config):\n    return route\n',
          requirements_source: '',
          revision: 'revision',
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

    await wrapper.get('select').setValue(templateKey)

    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({
      python_package: { folder: '', config: { threshold: 80 } },
      python_package_files: { template_key: templateKey, revision: 'revision' },
    })
    expect(wrapper.get('input[type="number"]').element.value).toBe('80')
  })

  it('keeps prescribed files visible when the saved package is invalid', () => {
    const draft = conditionRouterAdapter.fromApi({
      id: 'router-id',
      name: 'Broken router',
      python_package: { folder: 'owner--template--instance', config: {} },
      python_package_manifest: null,
      python_package_files: {
        main_source: 'def create_router(config):\n    return (\n',
        requirements_source: '',
        revision: 'broken-revision',
      },
      python_package_error: {
        message_key: 'resource.error.pythonPackage.syntax',
        message_args: { line: 2 },
      },
      dependency_status: 'failed',
    })
    const wrapper = mount(ConditionRouterEditor, {
      props: { modelValue: draft },
      global: {
        plugins: [createI18n({
          legacy: false,
          locale: 'en',
          messages: { en },
        })],
      },
    })

    expect(wrapper.get('textarea').element.value).toContain('return (')
    expect(wrapper.text()).toContain('main.py contains a Python syntax error on line 2.')
  })
})
