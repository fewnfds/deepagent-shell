import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { describe, expect, it } from 'vitest'

import { conditionRouterAdapter } from '@/domain/blocks'
import { en } from '@/locales/en'

import ConditionRouterEditor from './ConditionRouterEditor.vue'

const i18n = () => createI18n({
  legacy: false,
  locale: 'en',
  messages: { en },
})

describe('ConditionRouterEditor', () => {
  it('orders editable package files from the relative path list', async () => {
    const templateKey = 'threshold-router'
    const wrapper = mount(ConditionRouterEditor, {
      props: {
        modelValue: conditionRouterAdapter.blank(),
        catalog: [{
          key: templateKey,
          format_version: 1,
          family: 'workflow-node',
          adapter: 'condition-router',
          name: 'threshold-router',
          revision: 'revision',
          files: [
            { path: 'main.py', content: 'def create_router():\n    return route\n', exists: true },
            { path: 'helpers/rules.py', content: 'THRESHOLD = 80\n', exists: true },
          ],
        }],
      },
      global: { plugins: [i18n()] },
    })

    await wrapper.get('select').setValue(templateKey)
    const pathList = wrapper.get('textarea[rows="2"]')
    await pathList.setValue('main.py\nhelpers/rules.py\nmissing.py')
    await pathList.trigger('change')

    const emitted = wrapper.emitted('update:modelValue')?.at(-1)?.[0]
    expect(emitted).toMatchObject({
      python_package: {
        folder: '',
        editable_files: ['main.py', 'helpers/rules.py', 'missing.py'],
      },
      python_package_files: {
        template_key: templateKey,
        revision: 'revision',
        files: [
          { path: 'main.py', exists: true },
          { path: 'helpers/rules.py', content: 'THRESHOLD = 80\n', exists: true },
          { path: 'missing.py', content: '', exists: false },
        ],
      },
    })
    expect(wrapper.text()).toContain('missing.py')
    expect(wrapper.text()).toContain('This file does not exist yet.')
  })

  it('keeps selected files visible when the saved package is invalid', () => {
    const draft = conditionRouterAdapter.fromApi({
      id: 'router-id',
      name: 'Broken router',
      python_package: {
        folder: 'owner--template--instance',
        editable_files: ['main.py'],
      },
      python_package_manifest: null,
      python_package_files: {
        files: [{
          path: 'main.py',
          content: 'def create_router():\n    return (\n',
          exists: true,
        }],
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
      global: { plugins: [i18n()] },
    })

    expect(wrapper.findAll('textarea').some((item) => item.element.value.includes('return ('))).toBe(true)
    expect(wrapper.text()).toContain('main.py contains a Python syntax error on line 2.')
  })

  it('requests newly selected files from a saved package', async () => {
    const draft = conditionRouterAdapter.fromApi({
      id: 'router-id',
      name: 'Router',
      python_package: {
        folder: 'owner--template--instance',
        editable_files: ['main.py'],
      },
      python_package_files: {
        files: [{ path: 'main.py', content: 'SOURCE\n', exists: true }],
        revision: 'revision',
      },
    })
    const wrapper = mount(ConditionRouterEditor, {
      props: { modelValue: draft },
      global: { plugins: [i18n()] },
    })

    const pathList = wrapper.get('textarea[rows="2"]')
    await pathList.setValue('main.py\nhelpers/rules.py')
    await pathList.trigger('change')

    expect(wrapper.emitted('load-files')?.at(-1)?.[0]).toEqual(['helpers/rules.py'])
    const emitted = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as ReturnType<typeof conditionRouterAdapter.blank>
    expect(emitted.python_package_files.files[1]).toEqual({
      path: 'helpers/rules.py',
      content: '',
      readable: true,
    })
  })
})
