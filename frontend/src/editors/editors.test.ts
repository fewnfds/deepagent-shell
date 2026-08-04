import { mount, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { describe, expect, it } from 'vitest'
import type { Component } from 'vue'

import {
  customToolAdapter,
  filesystemAdapter,
  filesystemPermissionsAdapter,
  modelAdapter,
  outputModeAdapter,
  skillAdapter,
  systemPromptAdapter,
  type FilesystemDefaults,
  type FilesystemPermissionsDefaults,
  type OutputModeDefaults,
  type SkillDefaults,
} from '@/domain/blocks'
import { zhCN } from '@/locales/zh-CN'

import {
  CustomToolEditor,
  FilesystemEditor,
  FilesystemPermissionsEditor,
  ModelEditor,
  OutputModeEditor,
  SkillEditor,
  SystemPromptEditor,
} from './index'

const filesystemDefaults: FilesystemDefaults = {
  system_prompt: 'filesystem default',
  tool_token_limit_before_evict: 20_000,
  tools: [
    { name: 'ls', configurable: true, visible: true, default_description: 'ls default' },
    { name: 'read_file', configurable: false, visible: true, default_description: 'read default' },
    { name: 'write_file', configurable: true, visible: true, default_description: 'write default' },
    { name: 'edit_file', configurable: true, visible: true, default_description: 'edit default' },
    { name: 'delete', configurable: true, visible: false, default_description: 'delete default' },
    { name: 'glob', configurable: true, visible: true, default_description: 'glob default' },
    { name: 'grep', configurable: true, visible: true, default_description: 'grep default' },
    { name: 'execute', configurable: false, visible: false, default_description: 'execute default' },
  ],
}
const filesystemPermissionsDefaults: FilesystemPermissionsDefaults = {
  system_prompt: filesystemDefaults.system_prompt,
  tools: filesystemDefaults.tools,
}
const outputDefaults: OutputModeDefaults = {
  events: [{ key: 'assistant_text', variables: ['message'] }],
  filter_fields: ['message'],
  default_value: {
    filter_mode: 'blocklist', filter_mappings: [], variable_encoding: 'plain',
    event_templates: {
      assistant_text: {
        enabled: true, template: '{{message}}',
      },
    },
  },
}
const skillDefaults: SkillDefaults = {
  system_prompt: 'skill default',
  required_placeholders: ['{skills_locations}', '{skills_load_warnings}', '{skills_list}'],
}
const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: {} },
})

const localizedI18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  missingWarn: false,
  fallbackWarn: false,
  messages: { 'zh-CN': zhCN },
})

function mountEditor(component: Component, props: Record<string, unknown>): VueWrapper {
  return mount(component, {
    props,
    global: { plugins: [i18n] },
  })
}

describe('dedicated block editors', () => {
  it('round-trips filesystem permission rules and atomic overrides', () => {
    const apiValue = {
      id: 'permissions-id',
      name: 'Review policy',
      permissions: [
        { path: '/source/**', permission: 'read-only' as const },
        { path: '/private/**', permission: 'no-access' as const },
      ],
      system_prompt_override: { value: '' },
      tool_overrides: {
        write_file: { visible: false, description_override: 'Policy write tool' },
      },
    }

    const draft = filesystemPermissionsAdapter.fromApi(
      apiValue,
      filesystemPermissionsDefaults,
    )

    expect(draft.system_prompt_override_enabled).toBe(true)
    expect(draft.system_prompt_use_default).toBe(false)
    expect(draft.system_prompt_value).toBe('')
    expect(draft.tool_overrides.write_file?.override).toBe(true)
    expect(filesystemPermissionsAdapter.toPayload(
      draft,
      filesystemPermissionsDefaults,
    )).toEqual({
      name: 'Review policy',
      permissions: apiValue.permissions,
      system_prompt_override: { value: '' },
      tool_overrides: {
        write_file: { visible: false, description_override: 'Policy write tool' },
      },
    })
  })

  it('quick-loads paths from multiple filesystems without adding duplicates', async () => {
    const editor = mountEditor(FilesystemPermissionsEditor, {
      modelValue: filesystemPermissionsAdapter.blank(filesystemPermissionsDefaults),
      defaults: filesystemPermissionsDefaults,
      filesystems: [
        {
          id: 'filesystem-a',
          name: 'Filesystem A',
          mapped_directories: [{ virtual_path: '/workspace/', local_path: 'C:/workspace' }],
          virtual_directories: [{ virtual_path: '/drafts/', source_path: 'C:/drafts' }],
          virtual_files: [{ virtual_path: '/README.md', source_path: 'C:/README.md' }],
        },
        {
          id: 'filesystem-b',
          name: 'Filesystem B',
          mapped_directories: [{ virtual_path: '/other/', local_path: 'C:/other' }],
        },
      ],
    })
    const selects = editor.findAll('select')
    await selects[0]?.setValue('filesystem-a')
    await selects[1]?.setValue('no-access')
    await editor.get('[data-action="import-filesystem-paths"]').trigger('click')
    await editor.get('[data-action="import-filesystem-paths"]').trigger('click')

    expect(editor.findAll('[data-testid="filesystem-permission-row"]')).toHaveLength(3)
    expect(editor.findAll('[data-testid="filesystem-permission-row"] input').map(
      (input) => (input.element as HTMLInputElement).value,
    )).toEqual(['/workspace/**', '/drafts/**', '/README.md'])
    expect(editor.findAll('[data-testid="filesystem-permission-row"] select').map(
      (select) => (select.element as HTMLSelectElement).value,
    )).toEqual(['no-access', 'no-access', 'no-access'])

    await selects[0]?.setValue('filesystem-b')
    await editor.get('[data-action="import-filesystem-paths"]').trigger('click')
    expect(editor.findAll('[data-testid="filesystem-permission-row"]')).toHaveLength(4)
    expect(editor.findAll('[data-testid="filesystem-permission-row"] input').at(-1)?.element)
      .toHaveProperty('value', '/other/**')

    await editor.findAll('[data-action="remove-filesystem-permission"]')[0]?.trigger('click')
    expect(editor.findAll('[data-testid="filesystem-permission-row"]')).toHaveLength(3)
  })

  it('keeps mapping labels product-facing and add actions available at both ends', async () => {
    const permissionsDraft = filesystemPermissionsAdapter.blank(filesystemPermissionsDefaults)
    permissionsDraft.permissions.push({ path: '/workspace/**', permission: 'read-write' })
    const permissions = mount(FilesystemPermissionsEditor, {
      props: {
        modelValue: permissionsDraft,
        defaults: filesystemPermissionsDefaults,
        filesystems: [],
      },
      global: { plugins: [localizedI18n] },
    })
    const permissionRow = permissions.get('[data-testid="filesystem-permission-row"]')
    expect(permissionRow.text()).not.toContain('permissions.0.path')
    expect(permissionRow.get('label[for="filesystem-permission-path-0"]').text()).toBe('路径')
    expect(permissions.findAll('[data-action="add-filesystem-permission"]')).toHaveLength(2)
    await permissions.findAll('[data-action="add-filesystem-permission"]')[1]?.trigger('click')
    expect(permissions.findAll('[data-testid="filesystem-permission-row"]')).toHaveLength(2)

    const filesystemDraft = filesystemAdapter.blank(filesystemDefaults)
    filesystemDraft.mapped_directories.push({
      virtual_path: '/workspace',
      local_path: 'C:/workspace',
    })
    const filesystem = mount(FilesystemEditor, {
      props: { modelValue: filesystemDraft, defaults: filesystemDefaults },
      global: { plugins: [localizedI18n] },
    })
    expect(filesystem.findAll('[data-action="add-mapped-directory"]')).toHaveLength(2)

    const outputDraft = outputModeAdapter.blank(outputDefaults)
    outputDraft.filter_mappings.push({ field: 'message', value: 'secret' })
    const output = mount(OutputModeEditor, {
      props: { modelValue: outputDraft, defaults: outputDefaults },
      global: { plugins: [localizedI18n] },
    })
    expect(output.findAll('[data-action="add-filter-mapping"]')).toHaveLength(2)
  })

  it('emits model queries and resource refresh requests instead of calling APIs', async () => {
    const model = mountEditor(ModelEditor, { modelValue: modelAdapter.blank() })
    await model.get('[data-testid="model-fetch-group"]').trigger('submit')
    expect(model.emitted('fetch-models')?.[0]).toEqual([{
      provider: 'openai', baseUrl: '', credential: '', blockId: '',
    }])

    const tools = mountEditor(CustomToolEditor, { modelValue: customToolAdapter.blank() })
    await tools.get('[data-action="refresh"]').trigger('click')
    expect(tools.emitted('refresh')).toHaveLength(1)
  })

  it('renders all three LangChain model request settings with their distinct input forms', () => {
    const editor = mount(ModelEditor, {
      props: { modelValue: modelAdapter.blank() },
      global: { plugins: [localizedI18n] },
    })
    const settings = editor.findAll('[data-request-setting]')

    expect(settings.map((field) => field.attributes('data-request-setting'))).toEqual([
      'tool_choice',
      'response_format',
      'model_settings',
    ])
    expect(settings[0]?.find('input[list="tool-choice-options"]').exists()).toBe(true)
    expect(settings[1]?.find('textarea').exists()).toBe(true)
    expect(settings[2]?.find('textarea').exists()).toBe(true)
  })

  it('emits an updated draft when a visible field changes', async () => {
    const editor = mountEditor(SystemPromptEditor, { modelValue: systemPromptAdapter.blank() })
    expect(editor.get('.card-header').text()).toBe('capabilities.system-prompt.label')
    await editor.get('textarea').setValue('System prompt')
    expect(editor.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({
      system_prompt: 'System prompt',
    })
  })

  it('can disable the Skill system prompt without disabling the Skill component', async () => {
    const editor = mountEditor(SkillEditor, {
      modelValue: skillAdapter.blank(skillDefaults), defaults: skillDefaults,
    })
    const toggle = editor.get('[data-testid="skill-system-prompt-enabled"]')
    expect(editor.get('textarea').attributes('disabled')).toBeUndefined()

    await toggle.setValue(false)

    expect(editor.get('textarea').attributes('disabled')).toBeDefined()
    expect(editor.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({
      system_prompt_enabled: false,
    })
  })

  it('renders queried models as selectable cards', async () => {
    const editor = mountEditor(ModelEditor, {
      modelValue: modelAdapter.blank(),
      models: ['model-a', 'model-b'],
    })

    const cards = editor.findAll('[data-testid="model-option"]')
    expect(cards).toHaveLength(2)
    const fetchGroup = editor.get('[data-testid="model-fetch-group"]')
    expect(fetchGroup.element.tagName).toBe('FORM')
    const fetchButton = fetchGroup.get('[data-action="fetch-models"]')
    expect(fetchButton.attributes('type')).toBe('submit')
    await cards[1]?.trigger('click')

    const updatedCards = editor.findAll('[data-testid="model-option"]')
    expect(updatedCards[1]?.attributes('aria-pressed')).toBe('true')
    expect(editor.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ model: 'model-b' })
  })

  it('lists installed Providers and resets provider-specific settings on selection', async () => {
    const draft = modelAdapter.blank()
    draft.provider_settings = { max_completion_tokens: 200 }
    const editor = mountEditor(ModelEditor, {
      modelValue: draft,
      providers: [
        {
          provider: 'openai',
          package: 'langchain-openai',
          class_name: 'ChatOpenAI',
          installed: true,
          version: '1.4.1',
          documentation_url: 'https://docs.langchain.com/providers',
        },
        {
          provider: 'google_vertexai',
          package: 'langchain-google-vertexai',
          class_name: 'ChatVertexAI',
          installed: true,
          version: '3.2.4',
          documentation_url: 'https://docs.langchain.com/providers',
        },
      ],
    })
    const select = editor.get('[data-testid="model-provider-input"]')
    expect(select.element.tagName).toBe('SELECT')
    expect(select.findAll('option').map((option) => option.attributes('value'))).toEqual([
      '',
      'openai',
      'google_vertexai',
    ])
    expect(select.findAll('option').map((option) => option.text())).toEqual([
      'editors.model.providerPlaceholder',
      'openai · langchain-openai',
      'google_vertexai · langchain-google-vertexai',
    ])

    await select.setValue('google_vertexai')
    expect(editor.get('[data-testid="provider-details"]').text()).toContain(
      'langchain-google-vertexai',
    )
    expect(editor.get('[data-testid="provider-details"]').text()).toContain('3.2.4')
    expect(editor.find('[data-provider-setting="max_completion_tokens"]').exists()).toBe(false)
    expect(editor.find('[data-provider-setting="max_tokens"]').exists()).toBe(true)
    expect(editor.find('[data-provider-setting="thinking_budget"]').exists()).toBe(true)
    expect(editor.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({
      provider: 'google_vertexai',
      provider_settings: {},
    })
  })

  it('labels every custom tool identifier explicitly', () => {
    const editor = mountEditor(CustomToolEditor, {
      modelValue: customToolAdapter.blank(),
      catalog: [
        {
          name: 'safe_tool',
          function: 'word_count',
          tool_name: 'count_words',
          filename: 'safe_tool.py',
          description: 'Count words.',
        },
      ],
    })

    const items = editor.findAll('[data-testid="custom-tool-item"]')
    const identifiers = items[0]?.get('[data-testid="tool-identifiers"]').findAll('div').map((row) => [
      row.get('dt').text(),
      row.get('dd').text(),
    ])
    expect(identifiers).toEqual([
      ['tool_name', 'count_words'],
      ['function', 'word_count'],
      ['resource_name', 'safe_tool'],
      ['filename', 'safe_tool.py'],
    ])
  })

  it('localizes structured resource scan errors without a string fallback', () => {
    const editor = mountEditor(CustomToolEditor, {
      modelValue: customToolAdapter.blank(),
      errors: {
        'unsafe.py': {
          message_key: 'resource.error.customTool.syntax',
          message_args: { filename: 'unsafe.py' },
        },
      },
    })

    expect(editor.text()).toContain('resource.error.customTool.syntax')
    expect(editor.text()).toContain('unsafe.py')
  })
})
