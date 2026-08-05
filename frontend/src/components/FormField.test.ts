import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import FormField from './FormField.vue'
import { i18n } from '@/locales'

describe('FormField', () => {
  it('resolves a top-level payload path through the shared field catalog', () => {
    i18n.global.locale.value = 'zh-CN'
    const wrapper = mount(FormField, {
      props: { fieldPath: 'name' },
      slots: { default: '<input name="name">' },
      global: { plugins: [i18n] },
    })

    expect(wrapper.get('.form-label').text()).toBe('配置名称')
    expect(wrapper.get('.form-label').classes()).not.toContain('font-monospace')
  })

  it('uses the nested Subagent field label without another hardcoded map', () => {
    i18n.global.locale.value = 'en'
    const wrapper = mount(FormField, {
      props: { fieldPath: 'subagents.0.name' },
      slots: { default: '<input name="subagent-name">' },
      global: { plugins: [i18n] },
    })

    expect(wrapper.get('.form-label').text()).toBe('Configuration name')
  })

  it('shows the exact payload key for a technical field', () => {
    i18n.global.locale.value = 'zh-CN'
    const wrapper = mount(FormField, {
      props: { fieldPath: 'max_tokens', technical: true },
      slots: { default: '<input name="max_tokens">' },
      global: { plugins: [i18n] },
    })

    expect(wrapper.get('.form-label').text()).toBe('max_tokens')
    expect(wrapper.get('.form-label').classes()).toContain('font-monospace')
  })

  it('shows the full payload path in debug locale', () => {
    i18n.global.locale.value = 'debug'
    const wrapper = mount(FormField, {
      props: { fieldPath: 'middlewares.0.source' },
      slots: { default: '<input name="source">' },
      global: { plugins: [i18n] },
    })

    expect(wrapper.get('.form-label').text()).toBe('middlewares.0.source')
    expect(wrapper.get('.form-label').classes()).toContain('font-monospace')
  })
})
