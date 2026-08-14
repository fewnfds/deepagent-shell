import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { describe, expect, it } from 'vitest'

import {
  workflowInputContextAdapter,
  type WorkflowInputContextDefaults,
} from '@/domain/blocks'
import { zhCN } from '@/locales/zh-CN'

import WorkflowInputContextEditor from './WorkflowInputContextEditor.vue'

const defaults: WorkflowInputContextDefaults = {
  python_requirements: [],
  custom_transform_enabled: false,
  custom_transform_source: '',
  system_promote_enabled: false,
  system_promote_min_chars: 1_000_000,
  demote_non_top_system: false,
  slots: [],
}

describe('WorkflowInputContextEditor', () => {
  it('renders the system threshold before two disabled-by-default rules', () => {
    const wrapper = mount(WorkflowInputContextEditor, {
      props: {
        modelValue: workflowInputContextAdapter.blank(defaults),
        defaults,
      },
      global: {
        plugins: [createI18n({
          legacy: false,
          locale: 'zh-CN',
          messages: { 'zh-CN': zhCN },
        })],
      },
    })
    const card = wrapper.findAll('section.card').find((item) => (
      item.get('.card-title').text() === 'System 消息规则'
    ))

    expect(card).toBeDefined()
    expect(card!.findAll('input').map((input) => input.attributes('id'))).toEqual([
      'workflow-input-context-system-chars',
      'workflow-input-context-promote',
      'workflow-input-context-demote',
    ])
    expect(card!.get<HTMLInputElement>('#workflow-input-context-system-chars').element.value)
      .toBe('1000000')
    expect(card!.get('.input-group-text').text()).toBe('字符')
    expect(card!.get<HTMLInputElement>('#workflow-input-context-promote').element.checked).toBe(false)
    expect(card!.get<HTMLInputElement>('#workflow-input-context-demote').element.checked).toBe(false)
    const rules = card!.get('[data-testid="workflow-input-context-system-rules"]')
    expect(rules.classes()).toEqual(expect.arrayContaining(['d-flex', 'flex-column']))
    expect(rules.findAll(':scope > .form-switch')).toHaveLength(2)
    expect(card!.get('label[for="workflow-input-context-promote"]').text())
      .toBe('将字符数大于等于阈值的 system 消息上提到顶部')
    expect(card!.get('label[for="workflow-input-context-demote"]').text())
      .toBe('将字符数小于阈值的非顶部 system 消息转换为 user')
  })

  it('keeps the append action in the card body and omits the transform implementation hint', async () => {
    const wrapper = mount(WorkflowInputContextEditor, {
      props: {
        modelValue: workflowInputContextAdapter.blank(defaults),
        defaults,
      },
      global: {
        plugins: [createI18n({
          legacy: false,
          locale: 'zh-CN',
          messages: { 'zh-CN': zhCN },
        })],
      },
    })
    const card = wrapper.findAll('section.card').find((item) => (
      item.get('.card-title').text() === '追加消息'
    ))

    expect(card).toBeDefined()
    expect(wrapper.text()).not.toContain('定义 def transform')
    expect(card!.find('.card-header [data-action="add-workflow-input-slot"]').exists()).toBe(false)

    const addButton = card!.get('.card-body [data-action="add-workflow-input-slot"]')
    expect(addButton.classes()).toContain('btn-success')
    expect(addButton.get('.bi-plus-lg').attributes('aria-hidden')).toBe('true')
    await addButton.trigger('click')
    expect(card!.findAll('.list-group-item')).toHaveLength(1)
  })
})
