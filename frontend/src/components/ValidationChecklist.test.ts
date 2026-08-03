import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { describe, expect, it } from 'vitest'

import { zhCN } from '@/locales/zh-CN'

import ValidationChecklist from './ValidationChecklist.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  messages: { 'zh-CN': zhCN },
})

function mountChecklist(validation: Record<string, unknown>) {
  return mount(ValidationChecklist, {
    props: { title: '配置检查', validation },
    global: { plugins: [i18n] },
  })
}

describe('ValidationChecklist', () => {
  it('shows a compact success title and icon without a redundant status badge', () => {
    const wrapper = mountChecklist({
      status: 'valid',
      error: '',
      report: {
        valid: true,
        stage: 'draft_validation',
        issues: [],
      },
    })

    expect(wrapper.find('[data-testid="validation-status"]').exists()).toBe(false)
    expect(wrapper.findAll('.card')).toHaveLength(1)
    expect(wrapper.get('header i').classes()).toContain('bi-check-circle')
    expect(wrapper.find('header p').exists()).toBe(false)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('通过')
  })

  it('keeps the alert open while each localized issue starts collapsed', async () => {
    const wrapper = mountChecklist({
      status: 'invalid',
      error: '',
      report: {
        valid: false,
        stage: 'draft_validation',
        issues: [
          {
            code: 'contract.invalid_value',
            scope: 'subagent',
            owner_id: 'profile-id',
            owner_name: 'Profile',
            path: 'subagents[0].name',
            message: 'backend report message',
            message_key: 'validation.issue.contract.invalidValue',
            message_args: {},
          },
          {
            code: 'contract.text_too_short',
            scope: 'primary',
            owner_id: 'profile-id',
            owner_name: '',
            path: 'name',
            message: 'fallback report message',
            message_key: 'validation.issue.contract.textTooShort',
            message_args: {},
          },
        ],
      },
    })

    expect(wrapper.text()).toContain('Subagent 名称')
    expect(wrapper.find('details').exists()).toBe(false)
    expect(wrapper.get('header').text()).toContain('2 个问题，展开查看完整内容')
    expect(wrapper.find('[data-testid="validation-status"]').exists()).toBe(false)
    expect(wrapper.findAll('.card')).toHaveLength(1)
    expect(wrapper.find('.accordion').exists()).toBe(true)
    expect(wrapper.get('.accordion').classes()).toContain('accordion-flush')
    expect(wrapper.find('.card .card').exists()).toBe(false)
    const issueButtons = wrapper.findAll('.accordion-button')
    expect(issueButtons).toHaveLength(2)
    expect(issueButtons.every((button) => button.attributes('aria-expanded') === 'false')).toBe(true)
    expect(wrapper.findAll('.accordion-collapse')
      .every((panel) => panel.attributes('style')?.includes('display: none'))).toBe(true)

    await issueButtons[0].trigger('click')
    expect(issueButtons[0].attributes('aria-expanded')).toBe('true')
    expect(issueButtons[1].attributes('aria-expanded')).toBe('false')
    expect(wrapper.text()).toContain('subagents[0].name')
    expect(wrapper.text()).toContain('配置名称不能为空。')
    expect(wrapper.text()).toContain('Subagent 名称未通过当前配置规则')
    expect(wrapper.text()).not.toContain('backend report message')
    expect(wrapper.text()).toContain('当前编辑的 Primary Agent 配置')
  })

  it('pinpoints malformed output templates and always provides a concrete next step', () => {
    const wrapper = mountChecklist({
      status: 'invalid',
      error: '',
      report: {
        valid: false,
        stage: 'draft_validation',
        issues: [{
          code: 'contract.output_template_malformed',
          scope: 'block',
          owner_id: 'output-id',
          owner_name: 'Default output',
          owner_type: 'output-mode',
          path: 'event_templates.assistant_text.template',
          message: 'safe backend detail',
          message_key: 'validation.issue.contract.outputTemplateMalformed',
          message_args: { event_name: 'assistant_text' },
        }],
      },
    })

    const card = wrapper.get('[data-testid="validation-issue"]')
    expect(card.get('[data-testid="validation-owner"]').text())
      .toBe('组件类型 输出模式 配置名称 Default output')
    expect(card.text()).toContain('事件模板下的模型回答下的完整事件模板')
    expect(card.text()).toContain('模型回答模板包含未闭合或缺少一侧的双花括号。')
    expect(card.get('[data-testid="validation-resolution"]').text())
      .toContain('确保变量名称两侧各有两个完整且成对的花括号')
    expect(card.text()).not.toMatch(/[\u300c\u300d\u201c\u201d\u00b7\u2192]/)
  })

  it('renders field-level Subagent binding errors with specific reasons and fixes', () => {
    const cases = [
      {
        code: 'contract.subagent_name_required',
        path: 'subagents[0].name',
        message_key: 'validation.issue.contract.subagentNameRequired',
        reason: 'Subagent 必须填写名称。',
        resolution: '为这个 Subagent 填写名称，然后重新保存。',
      },
      {
        code: 'contract.subagent_name_format_invalid',
        path: 'subagents[1].name',
        message_key: 'validation.issue.contract.subagentNameFormatInvalid',
        reason: 'Subagent 名称格式不正确。',
        resolution: '名称必须以英文字母或下划线开头',
      },
      {
        code: 'contract.subagent_description_required',
        path: 'subagents[2].description',
        message_key: 'validation.issue.contract.subagentDescriptionRequired',
        reason: 'Subagent 必须填写说明。',
        resolution: '说明 Primary Agent 应在什么情况下把任务交给这个 Subagent',
      },
      {
        code: 'contract.subagent_name_duplicate',
        path: 'subagents[3].name',
        message_key: 'validation.issue.contract.subagentNameDuplicate',
        reason: '这个 Subagent 名称已被另一个 Subagent 使用。',
        resolution: '为每个 Subagent 使用不同的名称',
      },
    ]
    const wrapper = mountChecklist({
      status: 'invalid',
      error: '',
      report: {
        valid: false,
        stage: 'draft_validation',
        issues: cases.map(({ code, path, message_key }) => ({
          code,
          path,
          message_key,
          scope: 'primary',
          owner_id: 'primary-id',
          owner_name: 'coordinator',
          message: 'safe backend detail',
          message_args: {},
        })),
      },
    })

    const cards = wrapper.findAll('[data-testid="validation-issue"]')
    expect(cards).toHaveLength(cases.length)
    cases.forEach((item, index) => {
      expect(cards[index].get('[data-testid="validation-technical-path"]').text()).toBe(item.path)
      expect(cards[index].get('[data-testid="validation-reason"]').text()).toContain(item.reason)
      expect(cards[index].get('[data-testid="validation-resolution"]').text()).toContain(item.resolution)
    })
    expect(wrapper.text()).not.toContain('整份配置未通过当前配置规则')
  })

  it('keeps reason and resolution non-empty for unrecognized validation issues', () => {
    const wrapper = mountChecklist({
      status: 'invalid',
      error: '',
      report: {
        valid: false,
        stage: 'repository_validation',
        issues: [{
          code: 'future.unmapped_issue',
          scope: 'block',
          owner_id: 'future-id',
          owner_name: 'Future configuration',
          path: '',
          message: 'safe backend detail',
          message_key: 'validation.issue.future.unmapped',
          message_args: {},
        }],
      },
    })

    const card = wrapper.get('[data-testid="validation-issue"]')
    expect(card.get('[data-testid="validation-location"]').text()).toBe('整份配置')
    expect(card.get('[data-testid="validation-reason"]').text())
      .toContain('错误代码：future.unmapped_issue')
    expect(card.get('[data-testid="validation-resolution"]').text())
      .toContain('根据错误代码 future.unmapped_issue 更正内容')
  })

  it('shows an unsupported component type and name without a dot separator', () => {
    const wrapper = mountChecklist({
      status: 'invalid',
      error: '',
      report: {
        valid: false,
        stage: 'repository_validation',
        issues: [{
          code: 'storage.unknown_block_type',
          scope: 'block',
          owner_id: 'legacy-id',
          owner_name: 'tag-test',
          owner_type: 'prompt-injection',
          path: 'block_type',
          message: 'safe backend detail',
          message_key: 'errors.unknownConfigurationType',
          message_args: { type: 'prompt-injection' },
        }],
      },
    })

    const owner = wrapper.get('[data-testid="validation-owner"]').text()
    expect(owner).toBe('组件类型 prompt-injection 配置名称 tag-test')
    expect(owner).not.toContain('·')
  })

  it('separates owner, friendly location, technical path, reason, and resolution', () => {
    const wrapper = mountChecklist({
      status: 'invalid',
      error: '',
      report: {
        valid: false,
        stage: 'repository_validation',
        issues: [{
          code: 'contract.unknown_field',
          scope: 'primary',
          owner_id: 'primary-id',
          owner_name: 'test-primary-agent',
          path: 'subagents[0].inherit_all',
          message: 'raw backend report message',
          message_key: 'validation.issue.contract.unknownField',
          message_args: {},
        }],
      },
    })

    const card = wrapper.get('[data-testid="validation-issue"]')
    expect(card.get('[data-testid="validation-owner"]').text()).toContain('test-primary-agent 的 Primary Agent 配置')
    expect(card.get('dl').text()).toContain('问题位置')
    expect(card.get('[data-testid="validation-location"]').text()).toContain('Subagent 绑定中的第 1 项下的inherit_all 字段')
    const technicalPath = card.get('[data-testid="validation-technical-path"]')
    expect(technicalPath.text()).toBe('subagents[0].inherit_all')
    expect(technicalPath.element.tagName).toBe('DD')
    expect(technicalPath.classes()).toContain('font-monospace')
    expect(card.get('[data-testid="validation-reason"]').text())
      .toContain('inherit_all 字段不属于当前配置结构，可能已被删除或名称有误。')
    expect(card.get('[data-testid="validation-resolution"]').text())
      .toContain('打开 test-primary-agent 对应的 Primary Agent 配置，找到第 1 个 Subagent')
    expect(card.text()).not.toContain('配置项')
    expect(card.text()).not.toContain('raw backend report message')
    expect(card.text()).not.toMatch(/[\u300c\u300d\u201c\u201d\u00b7\u2192]/)
    expect(card.find('code').exists()).toBe(false)

    const text = card.text()
    expect(text.indexOf('所属配置')).toBeLessThan(text.indexOf('问题位置'))
    expect(text.indexOf('问题位置')).toBeLessThan(text.indexOf('技术路径'))
    expect(text.indexOf('技术路径')).toBeLessThan(text.indexOf('问题原因'))
    expect(text.indexOf('问题原因')).toBeLessThan(text.indexOf('处理方法'))
  })

  it('turns capability slugs into product labels and gives a concrete next step', () => {
    const wrapper = mountChecklist({
      status: 'invalid',
      error: '',
      report: {
        valid: false,
        stage: 'draft_validation',
        issues: [{
          code: 'assembly.required_capability_missing',
          scope: 'primary',
          owner_id: 'primary-id',
          owner_name: 'writer',
          path: 'capability_refs.output-mode',
          message: 'raw backend report message',
          message_key: 'validation.issue.assembly.requiredCapabilityMissing',
          message_args: { capability_type: 'output-mode' },
        }],
      },
    })

    const card = wrapper.get('[data-testid="validation-issue"]')
    const problemLocation = card.get('[data-testid="validation-location"]')
    expect(problemLocation.text()).toContain('能力引用下的输出模式')
    expect(problemLocation.text()).not.toContain('output-mode')
    expect(card.text()).toContain('尚未选择输出模式配置。')
    expect(card.get('[data-testid="validation-resolution"]').text())
      .toContain('在所属配置中选择一份输出模式配置。')
    expect(card.get('[data-testid="validation-technical-path"]').text()).toBe('capability_refs.output-mode')
    expect(card.text()).not.toContain('raw backend report message')
  })
})
