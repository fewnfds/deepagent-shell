import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  ManagementApiError,
  type BlockPayload,
  type BlockType,
  type CapabilityManifest,
  type SavedBlock,
  type WorkflowComponentManifest,
} from '@/api'
import { useConfirmation } from '@/composables/useConfirmation'

import ComponentsPage from './ComponentsPage.vue'

const api = vi.hoisted(() => ({
  getCatalog: vi.fn(),
  listBlocks: vi.fn(),
  getBlock: vi.fn(),
  saveBlock: vi.fn(),
  validateDraft: vi.fn(),
  validateRepository: vi.fn(),
  listCustomTools: vi.fn(),
  listMiddlewareTemplates: vi.fn(),
  listAgentEventOutputTemplates: vi.fn(),
  listWorkflowEventOutputTemplates: vi.fn(),
  listCommandTemplates: vi.fn(),
  listTaskDispatcherTemplates: vi.fn(),
  listSkills: vi.fn(),
  fetchModels: vi.fn(),
  listModelProviders: vi.fn(),
}))

const toastNotify = vi.hoisted(() => vi.fn())

vi.mock('@/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api')>()
  return { ...actual, managementApi: api }
})

vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ notify: toastNotify }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    locale: { value: 'en' },
    t: (key: string) => key,
    te: () => true,
  }),
}))

const modelManifest: CapabilityManifest = {
  type: 'model',
  terminology_key: 'model',
  label: 'Model manifest label',
  order: 1,
  icon_key: 'bot',
  editor_key: 'model',
  subagent_overrideable: true,
  required: true,
  subagent_policy: 'inherit',
  tool_names: [],
}

const skillManifest: CapabilityManifest = {
  ...modelManifest,
  type: 'skill',
  terminology_key: 'skill',
  label: 'Skill manifest label',
  order: 2,
  editor_key: 'skill',
  required: false,
}

const commandManifest: WorkflowComponentManifest = {
  type: 'command',
  terminology_key: 'command',
  label: 'Condition router',
  order: 1,
  icon_key: 'workflow',
  editor_key: 'command',
}

const taskDispatcherManifest: WorkflowComponentManifest = {
  ...commandManifest,
  type: 'task-dispatcher',
  terminology_key: 'task_dispatcher',
  label: 'Task dispatcher',
  editor_key: 'task-dispatcher',
}

const commandTemplate = {
  key: 'basic-router',
  format_version: 1 as const,
  family: 'workflow-node' as const,
  adapter: 'command' as const,
  name: 'Basic router',
  revision: 'template-revision',
  files: [{
    path: 'main.py', content: 'def create_command():\n    return route\n', exists: true,
  }],
}

function modelRecord(id: string): SavedBlock {
  return {
    id,
    name: 'Shared name',
    provider: 'openai',
    base_url: 'https://example.test/v1',
    credential: { status: 'masked' },
    model: 'test-model',
    provider_settings: {},
  }
}

function skillRecord(id: string): SavedBlock {
  return {
    id,
    name: 'Skill configuration',
    skills: ['fixture-skill'],
    instruction_override: null,
  }
}

async function mountAt(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/agent-components/:type', component: ComponentsPage }],
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(ComponentsPage, { global: { plugins: [router] } })
  await flushPromises()
  return { router, wrapper }
}

function buttonByText(wrapper: Awaited<ReturnType<typeof mountAt>>['wrapper'], text: string) {
  const button = wrapper.findAll('button').find((item) => item.text() === text)
  if (!button) throw new Error(`Button not found: ${text}`)
  return button
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((accept) => {
    resolve = accept
  })
  return { promise, resolve }
}

beforeEach(() => {
  useConfirmation().cancel()
  vi.clearAllMocks()
  api.getCatalog.mockResolvedValue({
    block_types: [skillManifest, modelManifest],
    workflow_component_types: [],
    editor_defaults: {
      skill: { system_prompt: 'default skill prompt', required_placeholders: [] },
    },
  })
  api.listBlocks.mockImplementation(async (type: BlockType) => (
    type === 'model'
      ? [modelRecord('00000000-0000-0000-0000-000000000001')]
      : [skillRecord('00000000-0000-0000-0000-000000000002')]
  ))
  api.getBlock.mockImplementation(async (type: BlockType, id: string) => (
    type === 'model' ? modelRecord(id) : skillRecord(id)
  ))
  api.saveBlock.mockImplementation(async (type: BlockType, data: BlockPayload & { id?: string }) => ({
    ...(type === 'model'
      ? modelRecord(data.id ?? '00000000-0000-0000-0000-000000000099')
      : skillRecord(data.id ?? '00000000-0000-0000-0000-000000000099')),
    ...data,
    id: data.id ?? '00000000-0000-0000-0000-000000000099',
  }))
  api.validateDraft.mockResolvedValue({ valid: true, stage: 'draft_validation', issues: [] })
  api.validateRepository.mockResolvedValue({ valid: true, stage: 'repository_load', issues: [] })
  api.listCustomTools.mockResolvedValue({ catalog: [], errors: {} })
  api.listMiddlewareTemplates.mockResolvedValue({ catalog: [], errors: {} })
  api.listAgentEventOutputTemplates.mockResolvedValue({ catalog: [], errors: {} })
  api.listWorkflowEventOutputTemplates.mockResolvedValue({ catalog: [], errors: {} })
  api.listCommandTemplates.mockResolvedValue({ catalog: [], errors: {} })
  api.listTaskDispatcherTemplates.mockResolvedValue({ catalog: [], errors: {} })
  api.listSkills.mockResolvedValue({
    catalog: [{ name: 'research', folder: 'research', description: 'Research skill' }],
    errors: {},
  })
  api.fetchModels.mockResolvedValue(['model-a'])
  api.listModelProviders.mockResolvedValue({
    langchain_version: '1.3.14',
    providers: [
      {
        provider: 'openai',
        package: 'langchain-openai',
        class_name: 'ChatOpenAI',
        installed: true,
        version: '1.4.1',
        documentation_url: 'https://docs.langchain.com/oss/python/integrations/providers/overview',
      },
    ],
  })
})

describe('ComponentsPage', () => {
  it('uses the Workflow Components section navigation without a duplicate type navigation', async () => {
    api.getCatalog.mockResolvedValueOnce({
      block_types: [skillManifest, modelManifest],
      workflow_component_types: [commandManifest],
      editor_defaults: { command: {} },
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{
        path: '/workflow-components/:type',
        component: ComponentsPage,
        props: { scope: 'workflow' },
      }],
    })
    await router.push('/workflow-components/command')
    await router.isReady()
    const wrapper = mount(ComponentsPage, {
      props: { scope: 'workflow' },
      global: { plugins: [router] },
    })
    await flushPromises()

    expect(api.listCommandTemplates).toHaveBeenCalledOnce()

    expect(wrapper.findAll('[data-testid="section-nav"] button').map((item) => item.text())).toEqual([
      'navigation.sections.workflowEventOutput',
      'navigation.sections.command',
      'navigation.sections.taskDispatcher',
    ])
    expect(wrapper.get('.page-action-dock').findAll('button').map((button) => button.text())).toEqual([
      'common.new',
      'common.reset',
      'common.save',
    ])
    wrapper.unmount()
  })

  it('resolves each base component route from the first scoped catalog manifest', async () => {
    api.getCatalog.mockResolvedValue({
      block_types: [skillManifest],
      workflow_component_types: [commandManifest],
      editor_defaults: {
        skill: { system_prompt: 'default skill prompt', required_placeholders: [] },
      },
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/agent-components', component: ComponentsPage },
        { path: '/agent-components/:type', component: ComponentsPage },
        {
          path: '/workflow-components',
          component: ComponentsPage,
          props: { scope: 'workflow' },
        },
        {
          path: '/workflow-components/:type',
          component: ComponentsPage,
          props: { scope: 'workflow' },
        },
      ],
    })
    await router.push('/agent-components')
    await router.isReady()
    const wrapper = mount({ template: '<RouterView />' }, { global: { plugins: [router] } })
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/agent-components/skill')
    expect(api.listBlocks).toHaveBeenLastCalledWith('skill')

    await router.push('/workflow-components')
    await flushPromises()

    await vi.waitFor(() => {
      expect(router.currentRoute.value.path).toBe('/workflow-components/command')
    })
    expect(api.listBlocks).toHaveBeenLastCalledWith('command')
    expect(wrapper.find('[data-editor="command"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('uses catalog order and loads only the routed type and explicit UUID', async () => {
    const id = '00000000-0000-0000-0000-000000000001'
    const { wrapper } = await mountAt(`/agent-components/model?id=${id}`)

    const navLabels = wrapper.findAll('[data-testid="section-nav"] button').map((item) => item.text())
    expect(navLabels).toEqual(['capabilities.model.label', 'capabilities.skill.label'])
    expect(wrapper.find('.app-content-header').exists()).toBe(false)
    expect(wrapper.find('[data-testid="editor-region"] > h2').exists()).toBe(false)
    expect(wrapper.get('.page-action-dock').findAll('button').map((button) => button.text())).toEqual([
      'common.new',
      'common.reset',
      'common.save',
    ])
    expect(api.listBlocks).toHaveBeenCalledTimes(1)
    expect(api.listBlocks).toHaveBeenCalledWith('model')
    expect(api.getBlock).toHaveBeenCalledWith('model', id)
    expect(wrapper.find('[data-editor="model"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="navigation-region"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="config-editor-layout"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="editor-region"]').find('[data-testid="validation-checklist"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="inspector-region"]').find('[data-testid="validation-checklist"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="component-layout"]').classes()).toContain('configuration-loading-surface')
    expect(wrapper.get('[data-testid="component-layout"]').attributes('data-loading')).toBe('false')
    expect(wrapper.text()).not.toContain('common.loading')
    expect(wrapper.text()).not.toContain(id)
    expect(api.listSkills).not.toHaveBeenCalled()
    expect(api.fetchModels).not.toHaveBeenCalled()

    const fetchButton = wrapper.findAll('[data-editor="model"] button')
      .find((button) => button.text() === 'editors.model.fetchModels')
    if (!fetchButton) throw new Error('fetch models button not found')
    await wrapper.get('[data-testid="model-fetch-group"]').trigger('submit')
    await flushPromises()
    expect(api.fetchModels).toHaveBeenCalledWith(
      'openai',
      'https://example.test/v1',
      null,
      id,
    )
    wrapper.unmount()
  })

  it('keeps route loading failures inline without also creating a toast', async () => {
    api.listBlocks.mockRejectedValueOnce(new Error('offline'))
    const { wrapper } = await mountAt('/agent-components/model')

    expect(wrapper.get('[data-testid="page-error"]').attributes('role')).toBe('alert')
    expect(toastNotify).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('scans resources only after the relevant editor requests a refresh', async () => {
    const { router, wrapper } = await mountAt('/agent-components/model')
    await router.push('/agent-components/skill')
    await flushPromises()

    expect(api.listBlocks).toHaveBeenLastCalledWith('skill')
    expect(api.listSkills).not.toHaveBeenCalled()
    const refresh = wrapper.findAll('[data-editor="skill"] button')
      .find((button) => button.text() === 'editors.common.refresh')
    if (!refresh) throw new Error('skill refresh button not found')
    await refresh.trigger('click')
    await flushPromises()

    expect(api.listSkills).toHaveBeenCalledOnce()
    expect(api.listCustomTools).not.toHaveBeenCalled()
    expect(api.listMiddlewareTemplates).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('loads templates without validating an extension before its first save', async () => {
    api.getCatalog.mockResolvedValueOnce({
      block_types: [skillManifest, modelManifest],
      workflow_component_types: [commandManifest],
      editor_defaults: { 'command': {} },
    })
    api.listBlocks.mockResolvedValueOnce([])
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{
        path: '/workflow-components/:type',
        component: ComponentsPage,
        props: { scope: 'workflow' },
      }],
    })
    await router.push('/workflow-components/command')
    await router.isReady()

    const wrapper = mount(ComponentsPage, {
      props: { scope: 'workflow' },
      global: { plugins: [router] },
    })
    await flushPromises()

    expect(api.listCommandTemplates).toHaveBeenCalledOnce()
    expect(api.listMiddlewareTemplates).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="validation-checklist"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('loads Task Dispatcher packages in the Workflow component editor', async () => {
    api.getCatalog.mockResolvedValueOnce({
      block_types: [skillManifest, modelManifest],
      workflow_component_types: [taskDispatcherManifest],
      editor_defaults: { 'task-dispatcher': {} },
    })
    api.listBlocks.mockResolvedValueOnce([])
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{
        path: '/workflow-components/:type',
        component: ComponentsPage,
        props: { scope: 'workflow' },
      }],
    })
    await router.push('/workflow-components/task-dispatcher')
    await router.isReady()

    const wrapper = mount(ComponentsPage, {
      props: { scope: 'workflow' },
      global: { plugins: [router] },
    })
    await flushPromises()

    expect(api.listTaskDispatcherTemplates).toHaveBeenCalledOnce()
    expect(wrapper.find('[data-editor="task-dispatcher"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('offers the empty template and rejects duplicate names for Python extensions', async () => {
    api.getCatalog.mockResolvedValueOnce({
      block_types: [skillManifest, modelManifest],
      workflow_component_types: [commandManifest],
      editor_defaults: { 'command': {} },
    })
    api.listBlocks.mockResolvedValueOnce([{
      id: '00000000-0000-4000-8000-000000000010',
      name: 'Existing router',
      python_package: {
        folder: '00000000-0000-4000-8000-000000000010',
        editable_files: ['main.py'],
      },
    }])
    api.listCommandTemplates.mockResolvedValueOnce({
      catalog: [commandTemplate],
      errors: {},
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{
        path: '/workflow-components/:type',
        component: ComponentsPage,
        props: { scope: 'workflow' },
      }],
    })
    await router.push('/workflow-components/command')
    await router.isReady()
    const wrapper = mount(ComponentsPage, {
      props: { scope: 'workflow' },
      global: { plugins: [router] },
    })
    await flushPromises()

    expect(wrapper.findAll('button').some((button) => (
      button.text() === 'editors.pythonPackage.applyEmptyTemplate'
    ))).toBe(true)
    await buttonByText(wrapper, 'common.save').trigger('click')
    expect(wrapper.get('[data-testid="page-error"]').text())
      .toContain('errors.pythonPackageTemplateRequired')
    expect(api.saveBlock).not.toHaveBeenCalled()

    await wrapper.get('[data-field="record-name"]').setValue('Existing router')
    await wrapper.get('[data-editor="command"] select').setValue('basic-router')
    await buttonByText(wrapper, 'common.save').trigger('click')
    expect(wrapper.get('[data-testid="page-error"]').text())
      .toContain('errors.configurationNameConflict')
    expect(useConfirmation().current.value).toBeNull()
    expect(api.saveBlock).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('updates with an explicit UUID and creates a uniquely named new draft', async () => {
    const id = '00000000-0000-0000-0000-000000000001'
    const { wrapper } = await mountAt(`/agent-components/model?id=${id}`)
    await wrapper.get('[data-field="record-name"]').setValue('Renamed configuration')
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()

    expect(api.saveBlock).toHaveBeenNthCalledWith(
      1,
      'model',
      expect.objectContaining({ id, name: 'Renamed configuration' }),
    )

    const newButton = wrapper.findAll('button').find((button) => button.text() === 'common.new')
    if (!newButton) throw new Error('new button not found')
    await newButton.trigger('click')
    await flushPromises()
    const nameInput = wrapper.get('[data-field="record-name"]')
    expect(nameInput.classes()).toContain('is-invalid')
    expect(nameInput.attributes('aria-invalid')).toBe('true')
    expect(wrapper.get('.record-picker-name-field .invalid-feedback').text()).toBe('')
    await nameInput.setValue('Another name')
    expect(nameInput.classes()).not.toContain('is-invalid')
    expect(nameInput.attributes('aria-invalid')).toBeUndefined()
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()

    const createPayload = api.saveBlock.mock.calls[1]?.[1]
    expect(createPayload).toEqual(expect.objectContaining({ name: 'Another name' }))
    expect(createPayload).not.toHaveProperty('id')
    wrapper.unmount()
  })

  it('confirms before replacing a saved configuration with the same name', async () => {
    const existingId = '00000000-0000-0000-0000-000000000001'
    const { wrapper } = await mountAt('/agent-components/model')
    await wrapper.get('[data-field="record-name"]').setValue('Shared name')

    await buttonByText(wrapper, 'common.save').trigger('click')

    expect(useConfirmation().current.value).toMatchObject({
      title: 'components.overwrite.title',
      confirmLabel: 'components.overwrite.confirm',
      dangerous: true,
    })
    expect(api.saveBlock).not.toHaveBeenCalled()

    useConfirmation().accept()
    await flushPromises()

    expect(api.saveBlock).toHaveBeenCalledWith(
      'model',
      expect.objectContaining({ id: existingId, name: 'Shared name' }),
    )
    wrapper.unmount()
  })

  it('keeps save enabled and renders validation returned by a failed save', async () => {
    const validation = {
      valid: false,
      stage: 'block_save',
      issues: [{
        code: 'field.required',
        scope: 'block',
        owner_id: '',
        owner_name: '',
        path: 'name',
        message: 'backend validation message',
        message_key: 'validation.issue.contract.fieldRequired',
        message_args: {},
      }],
    }
    api.saveBlock.mockRejectedValueOnce(new ManagementApiError({
      status: 422,
      code: 'configuration_validation_failed',
      message: 'save rejected',
      validation,
    }))
    const { wrapper } = await mountAt('/agent-components/model')
    const saveButton = buttonByText(wrapper, 'common.save')

    expect(saveButton.attributes('disabled')).toBeUndefined()
    await saveButton.trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="validation-checklist"]').attributes('data-status')).toBe('invalid')
    expect(wrapper.get('[data-testid="validation-checklist"]').text()).toContain('validation.issue.contract.fieldRequired')
    expect(wrapper.get('[data-testid="validation-checklist"]').text()).not.toContain('backend validation message')
    expect(toastNotify).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps a dirty draft until the user confirms a route change', async () => {
    const { router, wrapper } = await mountAt('/agent-components/model')
    await wrapper.get('[data-field="record-name"]').setValue('Unsaved name')

    const skillButton = wrapper.findAll('[data-testid="section-nav"] button')
      .find((button) => button.text().includes('capabilities.skill.label'))
    if (!skillButton) throw new Error('skill navigation button not found')

    await skillButton.trigger('click')
    expect(useConfirmation().current.value?.title).toBe('unsavedChanges.title')
    useConfirmation().cancel()
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/agent-components/model')
    expect(wrapper.get('[data-field="record-name"]').element).toHaveProperty('value', 'Unsaved name')

    await skillButton.trigger('click')
    useConfirmation().accept()
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/agent-components/skill')
    expect(wrapper.find('.app-content-header').exists()).toBe(false)
    wrapper.unmount()
  })

  it('clears model results when the connection changes or a query fails', async () => {
    const id = '00000000-0000-0000-0000-000000000001'
    const { wrapper } = await mountAt(`/agent-components/model?id=${id}`)
    const fetchButton = wrapper.findAll('[data-editor="model"] button')
      .find((button) => button.text() === 'editors.model.fetchModels')
    if (!fetchButton) throw new Error('fetch models button not found')

    await wrapper.get('[data-testid="model-fetch-group"]').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('model-a')

    await wrapper.get('[data-editor="model"] input[inputmode="url"]')
      .setValue('https://other.example/v1')
    await flushPromises()
    expect(wrapper.text()).not.toContain('model-a')

    api.fetchModels.mockRejectedValueOnce(new Error('catalog unavailable'))
    await wrapper.get('[data-testid="model-fetch-group"]').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).not.toContain('model-a')
    expect(toastNotify).toHaveBeenCalledWith(expect.objectContaining({ tone: 'danger' }))
    wrapper.unmount()
  })

  it('discards a stale model response after a newer connection query starts', async () => {
    const first = deferred<string[]>()
    const second = deferred<string[]>()
    api.fetchModels
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise)
    const id = '00000000-0000-0000-0000-000000000001'
    const { wrapper } = await mountAt(`/agent-components/model?id=${id}`)
    const fetchButton = wrapper.findAll('[data-editor="model"] button')
      .find((button) => button.text() === 'editors.model.fetchModels')
    if (!fetchButton) throw new Error('fetch models button not found')

    await wrapper.get('[data-testid="model-fetch-group"]').trigger('submit')
    await wrapper.get('[data-editor="model"] input[inputmode="url"]')
      .setValue('https://new.example/v1')
    await flushPromises()
    await wrapper.get('[data-testid="model-fetch-group"]').trigger('submit')

    first.resolve(['stale-model'])
    await flushPromises()
    expect(wrapper.text()).not.toContain('stale-model')

    second.resolve(['current-model'])
    await flushPromises()
    expect(wrapper.text()).toContain('current-model')
    wrapper.unmount()
  })
})
