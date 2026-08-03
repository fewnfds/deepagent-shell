import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { ManagementApiError } from '@/api'
import type {
  AgentAuthoringService,
  CapabilityManifest,
  PrimaryAgentProfile,
  SubagentProfile,
  ValidationReport,
} from '@/domain/agents'

import PrimaryAgentPage from './PrimaryAgentPage.vue'
import SubagentPage from './SubagentPage.vue'

const toastNotify = vi.hoisted(() => vi.fn())

vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ notify: toastNotify }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
    te: () => true,
  }),
}))

const validReport: ValidationReport = {
  valid: true,
  stage: 'draft_validation',
  issues: [],
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((accept) => {
    resolve = accept
  })
  return { promise, resolve }
}

const modelManifest: CapabilityManifest = {
  type: 'model',
  terminology_key: 'model',
  label: 'Model',
  order: 1,
  icon_key: 'bot',
  editor_key: 'model',
  subagent_overrideable: true,
  required: true,
  subagent_policy: 'inherit',
  tool_names: [],
}

const promptManifest: CapabilityManifest = {
  ...modelManifest,
  type: 'system-prompt',
  terminology_key: 'system-prompt',
  order: 2,
  required: false,
}

const filesystemManifest: CapabilityManifest = {
  ...modelManifest,
  type: 'filesystem',
  terminology_key: 'file-system',
  order: 3,
  subagent_overrideable: false,
  required: false,
  subagent_policy: 'inherit',
}

const outputModeManifest: CapabilityManifest = {
  ...modelManifest,
  type: 'output-mode',
  terminology_key: 'output-policy',
  order: 8,
  subagent_overrideable: false,
  subagent_policy: 'top-level-only',
}

const subagentManifest: CapabilityManifest = {
  ...modelManifest,
  type: 'subagent',
  terminology_key: 'delegation',
  order: 10,
  subagent_overrideable: true,
  required: false,
  subagent_policy: 'inherit',
}

function service(overrides: Partial<AgentAuthoringService> = {}): AgentAuthoringService {
  const primary: PrimaryAgentProfile = {
    id: '00000000-0000-0000-0000-000000000010',
    name: 'Shared name',
    capability_refs: [],
    subagents: [],
  }
  const subagent: SubagentProfile = {
    id: '00000000-0000-0000-0000-000000000020',
    component_name: 'Worker component',
    name: 'worker',
    description: 'Handles delegated work.',
    settings: { capability_overrides: [], subagents: [] },
  }
  return {
    getCatalog: vi.fn(async () => ({
      block_types: [modelManifest, promptManifest],
      editor_defaults: {},
    })),
    listBlocks: vi.fn(async (type) => [{
      id: `00000000-0000-0000-0000-${type === 'model' ? '000000000001' : '000000000002'}`,
      name: `${type} block`,
    }]),
    listAutomationWorkflows: vi.fn(async () => []),
    listPrimaryAgents: vi.fn(async () => [primary]),
    getPrimaryAgent: vi.fn(async () => primary),
    createPrimaryAgent: vi.fn(async (payload) => ({ ...primary, ...payload, id: 'created-primary' })),
    updatePrimaryAgent: vi.fn(async (id, payload) => ({ ...primary, ...payload, id })),
    listSubagents: vi.fn(async () => [subagent]),
    getSubagent: vi.fn(async () => subagent),
    createSubagent: vi.fn(async (payload) => ({ ...subagent, ...payload, id: 'created-subagent' })),
    updateSubagent: vi.fn(async (id, payload) => ({ ...subagent, ...payload, id })),
    validateDraft: vi.fn(async () => validReport),
    ...overrides,
  }
}

function buttonByText(wrapper: ReturnType<typeof mount>, text: string) {
  const button = wrapper.findAll('button').find((item) => item.text() === text)
  if (!button) throw new Error(`Button not found: ${text}`)
  return button
}

beforeEach(() => {
  toastNotify.mockReset()
})

async function mountPrimaryPage(
  api: AgentAuthoringService,
  path = '/agents/primary',
) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/agents/primary', component: PrimaryAgentPage }],
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(PrimaryAgentPage, {
    props: { service: api },
    global: { plugins: [router] },
  })
  await flushPromises()
  return { router, wrapper }
}

async function mountSubagentPage(
  api: AgentAuthoringService,
  path = '/agents/subagents',
) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/agents/subagents', component: SubagentPage }],
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(SubagentPage, {
    props: { service: api },
    global: { plugins: [router] },
  })
  await flushPromises()
  return { router, wrapper }
}

describe('agent authoring pages', () => {
  it('lets current editors remove an obsolete capability type before saving', async () => {
    const obsoleteType = 'removed-capability'
    const obsoleteBlockId = '00000000-0000-0000-0000-000000000099'
    const primaryId = '00000000-0000-0000-0000-000000000010'
    const primaryApi = service({
      getPrimaryAgent: vi.fn(async () => ({
        id: primaryId,
        name: 'Historical Primary',
        capability_refs: [{ type: obsoleteType, block_id: obsoleteBlockId }],
        subagents: [],
        automation: { hook_workflow_id: '', lifecycle_workflow_id: '' },
      })),
    })
    const primaryPage = await mountPrimaryPage(
      primaryApi,
      `/agents/primary?id=${primaryId}`,
    )

    expect(primaryPage.wrapper.get('[data-testid="obsolete-capability-references"]').text())
      .toContain(obsoleteType)
    await primaryPage.wrapper.get('[data-action="remove-obsolete-capability-reference"]')
      .trigger('click')
    await buttonByText(primaryPage.wrapper, 'common.save').trigger('click')
    await flushPromises()

    expect(primaryApi.updatePrimaryAgent).toHaveBeenCalledWith(
      primaryId,
      expect.objectContaining({ capability_refs: [] }),
    )
    primaryPage.wrapper.unmount()

    const subagentId = '00000000-0000-0000-0000-000000000020'
    const subagentApi = service({
      getSubagent: vi.fn(async () => ({
        id: subagentId,
        component_name: 'Historical Subagent',
        name: 'historical_worker',
        description: 'Historical worker.',
        settings: {
          capability_overrides: [{
            type: obsoleteType,
            mode: 'replace',
            block_id: obsoleteBlockId,
          }],
          subagents: [],
          automation: {
            hook_workflow: { mode: 'inherit', workflow_id: '' },
            lifecycle_workflow: { mode: 'inherit', workflow_id: '' },
          },
        },
      })),
    })
    const subagentPage = await mountSubagentPage(
      subagentApi,
      `/agents/subagents?id=${subagentId}`,
    )

    expect(subagentPage.wrapper.get('[data-testid="obsolete-capability-overrides"]').text())
      .toContain(obsoleteType)
    await subagentPage.wrapper.get('[data-action="remove-obsolete-capability-override"]')
      .trigger('click')
    await buttonByText(subagentPage.wrapper, 'common.save').trigger('click')
    await flushPromises()

    expect(subagentApi.updateSubagent).toHaveBeenCalledWith(
      subagentId,
      expect.objectContaining({
        settings: expect.objectContaining({ capability_overrides: [] }),
      }),
    )
    subagentPage.wrapper.unmount()
  })

  it('updates a Primary only after loading its explicit UUID', async () => {
    const api = service()
    const id = '00000000-0000-0000-0000-000000000010'
    const { wrapper } = await mountPrimaryPage(
      api,
      `/agents/primary?id=${id}`,
    )
    expect(wrapper.text()).not.toContain(id)
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()

    expect(api.getPrimaryAgent).toHaveBeenCalledWith(id)
    expect(api.updatePrimaryAgent).toHaveBeenCalledWith(
      id,
      expect.objectContaining({ name: 'Shared name' }),
    )
    expect(api.createPrimaryAgent).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('adds, selects, and removes ordered Subagent entity references', async () => {
    const api = service()
    const { wrapper } = await mountPrimaryPage(api)

    const addButton = wrapper.findAll('button').find((button) => button.text() === 'agents.primary.addReference')
    if (!addButton) throw new Error('add reference button not found')
    await addButton.trigger('click')
    await addButton.trigger('click')
    expect(wrapper.findAll('[data-testid="subagent-reference-card"]')).toHaveLength(2)
    expect(wrapper.findAll('[data-action="remove-subagent-reference"]').every((button) => (
      button.classes().includes('ms-auto')
    ))).toBe(true)

    await wrapper.findAll('[data-action="remove-subagent-reference"]')[0]?.trigger('click')
    expect(wrapper.findAll('[data-testid="subagent-reference-card"]')).toHaveLength(1)
    const card = wrapper.get('[data-testid="subagent-reference-card"]')
    await card.get('[data-testid="subagent-reference"]').setValue(
      '00000000-0000-0000-0000-000000000020',
    )
    await flushPromises()
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()

    expect(api.createPrimaryAgent).toHaveBeenCalledWith(expect.objectContaining({
      subagents: [{
        subagent_id: '00000000-0000-0000-0000-000000000020',
      }],
    }))
    wrapper.unmount()
  })

  it('uses the Primary layout and one select per Subagent capability', async () => {
    const api = service()
    const primaryPage = await mountPrimaryPage(api)
    const { wrapper } = await mountSubagentPage(api)

    expect(primaryPage.wrapper.get('section.col-lg-8')).toBeTruthy()
    expect(primaryPage.wrapper.get('aside.col-lg-4').classes()).toContain('validation-sidebar')
    expect(wrapper.get('section.col-lg-8')).toBeTruthy()
    expect(wrapper.get('aside.col-lg-4').classes()).toContain('validation-sidebar')
    expect(wrapper.findAll('[data-capability] input[type="radio"]')).toHaveLength(0)
    expect(wrapper.findAll('[data-capability] select')).toHaveLength(2)
    expect(primaryPage.wrapper.findAll('[data-capability] > .card')).toHaveLength(2)
    expect(wrapper.findAll('[data-capability] > .card')).toHaveLength(2)
    expect(primaryPage.wrapper.findAll('[data-capability] .badge').every((badge) => (
      badge.classes().includes('ms-auto')
    ))).toBe(true)
    expect(wrapper.findAll('[data-capability] .badge').every((badge) => (
      badge.classes().includes('ms-auto')
    ))).toBe(true)
    expect(primaryPage.wrapper.find('.card .card').exists()).toBe(false)
    expect(wrapper.find('.card .card').exists()).toBe(false)

    primaryPage.wrapper.unmount()
    wrapper.unmount()
  })

  it('shows fixed filesystem and output-mode values and the full Subagent capability choices', async () => {
    const api = service({
      getCatalog: vi.fn(async () => ({
        block_types: [
          modelManifest,
          promptManifest,
          filesystemManifest,
          outputModeManifest,
          subagentManifest,
        ],
        editor_defaults: {},
      })),
    })
    const { wrapper } = await mountSubagentPage(api)

    expect(wrapper.findAll('[data-capability]')).toHaveLength(5)

    const filesystem = wrapper.get('[data-testid="subagent-capability-filesystem"]')
    expect(filesystem.attributes('disabled')).toBeDefined()
    expect((filesystem.element as HTMLSelectElement).value).toBe('__inherit__')
    expect(filesystem.text()).toContain('agents.override.mode.inherit')

    const outputMode = wrapper.get('[data-testid="subagent-capability-output-mode"]')
    expect(outputMode.attributes('disabled')).toBeDefined()
    expect((outputMode.element as HTMLSelectElement).value).toBe('__invalid__')
    expect(outputMode.text()).toContain('agents.override.mode.invalid')

    const subagent = wrapper.get('[data-testid="subagent-capability-subagent"]')
    expect(subagent.attributes('disabled')).toBeUndefined()
    expect((subagent.element as HTMLSelectElement).value).toBe('__inherit__')
    expect(subagent.find('option[value="__inherit__"]').exists()).toBe(true)
    expect(subagent.find('option[value="__disabled__"]').exists()).toBe(true)
    expect(subagent.findAll('option')).toHaveLength(3)
    await subagent.setValue('00000000-0000-0000-0000-000000000002')
    expect((subagent.element as HTMLSelectElement).value).toBe('00000000-0000-0000-0000-000000000002')
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()
    expect(api.createSubagent).toHaveBeenCalledWith(expect.objectContaining({
      settings: expect.objectContaining({
        capability_overrides: [{
          type: 'subagent',
          mode: 'replace',
          block_id: '00000000-0000-0000-0000-000000000002',
        }],
      }),
    }))
    await subagent.setValue('__disabled__')
    expect((subagent.element as HTMLSelectElement).value).toBe('__disabled__')

    wrapper.unmount()
  })

  it('adds inherit to Subagent choices and stores disabled or replacement selections', async () => {
    const api = service()
    const { wrapper } = await mountSubagentPage(api)

    const modelSelect = wrapper.get('[data-testid="subagent-capability-model"]')
    const optionalSelect = wrapper.get('[data-testid="subagent-capability-system-prompt"]')
    expect(modelSelect.find('option[value="__inherit__"]').exists()).toBe(true)
    expect(modelSelect.find('option[value="__disabled__"]').exists()).toBe(false)
    expect(optionalSelect.find('option[value="__inherit__"]').exists()).toBe(true)
    expect(optionalSelect.find('option[value="__disabled__"]').exists()).toBe(true)

    await modelSelect.setValue('00000000-0000-0000-0000-000000000001')
    await optionalSelect.setValue('__disabled__')
    await flushPromises()
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()

    expect(api.createSubagent).toHaveBeenCalledWith({
      component_name: '',
      name: '',
      description: '',
      settings: {
        capability_overrides: [
          { type: 'model', mode: 'replace', block_id: '00000000-0000-0000-0000-000000000001' },
          { type: 'system-prompt', mode: 'disabled', block_id: '' },
        ],
        subagents: [],
        automation: {
          hook_workflow: { mode: 'inherit', workflow_id: '' },
          lifecycle_workflow: { mode: 'inherit', workflow_id: '' },
        },
      },
    })
    wrapper.unmount()
  })

  it('loads a Subagent entity from the configuration-library query UUID', async () => {
    const api = service()
    const id = '00000000-0000-0000-0000-000000000020'
    const { wrapper } = await mountSubagentPage(
      api,
      `/agents/subagents?id=${id}`,
    )

    expect(api.getSubagent).toHaveBeenCalledWith(id)
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()
    expect(api.updateSubagent).toHaveBeenCalledWith(
      id,
      expect.objectContaining({
        component_name: 'Worker component',
        name: 'worker',
      }),
    )
    wrapper.unmount()
  })

  it('adds an entity child to a Subagent and can reference itself', async () => {
    const api = service()
    const id = '00000000-0000-0000-0000-000000000020'
    const { wrapper } = await mountSubagentPage(api, `/agents/subagents?id=${id}`)

    await buttonByText(wrapper, 'agents.primary.addReference').trigger('click')
    const reference = wrapper.get('[data-testid="subagent-reference-card"]')
    await reference.get('[data-testid="subagent-reference"]').setValue(id)
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()

    expect(api.updateSubagent).toHaveBeenCalledWith(
      id,
      expect.objectContaining({
        settings: expect.objectContaining({
          subagents: [{ subagent_id: id }],
        }),
      }),
    )
    wrapper.unmount()
  })

  it('loads a new Primary when only the route query UUID changes', async () => {
    const id = '00000000-0000-0000-0000-000000000011'
    const api = service({
      getPrimaryAgent: vi.fn(async (requestedId) => ({
        id: requestedId,
        name: 'Routed Primary',
        capability_refs: [],
        subagents: [],
      })),
    })
    const { router, wrapper } = await mountPrimaryPage(api)

    await router.push({ path: '/agents/primary', query: { id } })
    await flushPromises()

    expect(api.getPrimaryAgent).toHaveBeenCalledWith(id)
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()
    expect(api.updatePrimaryAgent).toHaveBeenCalledWith(
      id,
      expect.objectContaining({ name: 'Routed Primary' }),
    )
    wrapper.unmount()
  })

  it('keeps the latest Agent route when an earlier query load finishes late', async () => {
    const firstPrimaryId = '00000000-0000-0000-0000-000000000031'
    const secondPrimaryId = '00000000-0000-0000-0000-000000000032'
    const firstPrimary = deferred<PrimaryAgentProfile>()
    const secondPrimary = deferred<PrimaryAgentProfile>()
    const getPrimaryAgent = vi.fn((id: string) => (
      id === firstPrimaryId ? firstPrimary.promise : secondPrimary.promise
    ))
    const primaryApi = service({ getPrimaryAgent })
    const primaryPage = await mountPrimaryPage(primaryApi)

    await primaryPage.router.push({ path: '/agents/primary', query: { id: firstPrimaryId } })
    await primaryPage.router.push({ path: '/agents/primary', query: { id: secondPrimaryId } })
    secondPrimary.resolve({
      id: secondPrimaryId,
      name: 'Latest Primary',
      capability_refs: [],
      subagents: [],
    })
    await flushPromises()
    firstPrimary.resolve({
      id: firstPrimaryId,
      name: 'Late Primary',
      capability_refs: [],
      subagents: [],
    })
    await flushPromises()
    await buttonByText(primaryPage.wrapper, 'common.save').trigger('click')
    await flushPromises()

    expect(primaryApi.updatePrimaryAgent).toHaveBeenCalledWith(
      secondPrimaryId,
      expect.objectContaining({ name: 'Latest Primary' }),
    )
    primaryPage.wrapper.unmount()

    const firstSubagentId = '00000000-0000-0000-0000-000000000041'
    const secondSubagentId = '00000000-0000-0000-0000-000000000042'
    const firstSubagent = deferred<SubagentProfile>()
    const secondSubagent = deferred<SubagentProfile>()
    const getSubagent = vi.fn((id: string) => (
      id === firstSubagentId ? firstSubagent.promise : secondSubagent.promise
    ))
    const subagentApi = service({ getSubagent })
    const subagentPage = await mountSubagentPage(subagentApi)

    await subagentPage.router.push({ path: '/agents/subagents', query: { id: firstSubagentId } })
    await subagentPage.router.push({ path: '/agents/subagents', query: { id: secondSubagentId } })
    secondSubagent.resolve({
      id: secondSubagentId,
      component_name: 'Latest Subagent',
      name: 'latest_worker',
      description: 'Latest worker.',
      settings: { capability_overrides: [], subagents: [] },
    })
    await flushPromises()
    firstSubagent.resolve({
      id: firstSubagentId,
      component_name: 'Late Subagent',
      name: 'late_worker',
      description: 'Late worker.',
      settings: { capability_overrides: [], subagents: [] },
    })
    await flushPromises()
    await buttonByText(subagentPage.wrapper, 'common.save').trigger('click')
    await flushPromises()

    expect(subagentApi.updateSubagent).toHaveBeenCalledWith(
      secondSubagentId,
      expect.objectContaining({ component_name: 'Latest Subagent' }),
    )
    subagentPage.wrapper.unmount()
  })

  it('keeps the loaded Primary identity when selecting another record fails', async () => {
    const currentId = '00000000-0000-0000-0000-000000000010'
    const failedId = '00000000-0000-0000-0000-000000000099'
    const api = service({
      listPrimaryAgents: vi.fn(async () => [
        {
          id: currentId,
          name: 'Current Primary',
          capability_refs: [],
          subagents: [],
        },
        {
          id: failedId,
          name: 'Unavailable Primary',
          capability_refs: [],
          subagents: [],
        },
      ]),
      getPrimaryAgent: vi.fn(async (id) => {
        if (id === failedId) throw new Error('load failed')
        return {
          id: currentId,
          name: 'Current Primary',
          capability_refs: [],
          subagents: [],
        }
      }),
    })
    const { wrapper } = await mountPrimaryPage(
      api,
      `/agents/primary?id=${currentId}`,
    )

    await wrapper.get('[data-testid="record-picker-select"]').setValue(failedId)
    await flushPromises()
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()

    expect(api.updatePrimaryAgent).toHaveBeenCalledWith(
      currentId,
      expect.objectContaining({ name: 'Current Primary' }),
    )
    expect(api.updatePrimaryAgent).not.toHaveBeenCalledWith(
      failedId,
      expect.anything(),
    )
    wrapper.unmount()
  })

  it('clears an old save error after the next Primary save succeeds', async () => {
    const createPrimaryAgent = vi.fn()
      .mockRejectedValueOnce(new ManagementApiError({
        status: 500,
        code: 'old_save_failure',
        message: 'The first save failed.',
      }))
      .mockResolvedValueOnce({
        id: 'created-primary',
        name: '',
        capability_refs: [],
        subagents: [],
      })
    const api = service({ createPrimaryAgent })
    const { wrapper } = await mountPrimaryPage(api)

    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('old_save_failure')

    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()
    expect(toastNotify).toHaveBeenCalledWith({
      tone: 'success',
      title: 'agents.feedback.saved',
    })
    expect(wrapper.find('[data-testid="page-feedback"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('old_save_failure')
    wrapper.unmount()
  })
})
