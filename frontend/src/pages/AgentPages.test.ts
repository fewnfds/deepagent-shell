import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { ManagementApiError } from '@/api'
import type {
  AgentAuthoringService,
  CapabilityManifest,
  PrimaryAgentProfile,
  SubagentOverrideProfile,
  ValidationReport,
} from '@/domain/agents'

import PrimaryAgentPage from './PrimaryAgentPage.vue'
import SubagentOverridePage from './SubagentOverridePage.vue'

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

function service(overrides: Partial<AgentAuthoringService> = {}): AgentAuthoringService {
  const primary: PrimaryAgentProfile = {
    id: '00000000-0000-0000-0000-000000000010',
    name: 'Shared name',
    capability_refs: [],
    subagents: [],
  }
  const subagentOverride: SubagentOverrideProfile = {
    id: '00000000-0000-0000-0000-000000000020',
    name: 'Override',
    capability_overrides: [],
    subagents: [],
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
    listPrimaryAgents: vi.fn(async () => [primary]),
    getPrimaryAgent: vi.fn(async () => primary),
    createPrimaryAgent: vi.fn(async (payload) => ({ ...primary, ...payload, id: 'created-primary' })),
    updatePrimaryAgent: vi.fn(async (id, payload) => ({ ...primary, ...payload, id })),
    listSubagentOverrides: vi.fn(async () => [subagentOverride]),
    getSubagentOverride: vi.fn(async () => subagentOverride),
    createSubagentOverride: vi.fn(async (payload) => ({ ...subagentOverride, ...payload, id: 'created-override' })),
    updateSubagentOverride: vi.fn(async (id, payload) => ({ ...subagentOverride, ...payload, id })),
    validateDraft: vi.fn(async () => validReport),
    ...overrides,
  }
}

function buttonByText(wrapper: ReturnType<typeof mount>, text: string) {
  const button = wrapper.findAll('button').find((item) => item.text() === text)
  if (!button) throw new Error(`Button not found: ${text}`)
  return button
}

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
    routes: [{ path: '/agents/subagents', component: SubagentOverridePage }],
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(SubagentOverridePage, {
    props: { service: api },
    global: { plugins: [router] },
  })
  await flushPromises()
  return { router, wrapper }
}

describe('agent authoring pages', () => {
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

  it('adds, edits, overrides, and removes explicit Subagent bindings', async () => {
    const api = service()
    const { wrapper } = await mountPrimaryPage(api)

    const addButton = wrapper.findAll('button').find((button) => button.text() === 'agents.primary.addBinding')
    if (!addButton) throw new Error('add binding button not found')
    await addButton.trigger('click')
    await addButton.trigger('click')
    expect(wrapper.findAll('[data-testid="binding-card"]')).toHaveLength(2)
    expect(wrapper.findAll('[data-action="remove-binding"]').every((button) => (
      button.classes().includes('ms-auto')
    ))).toBe(true)

    await wrapper.findAll('[data-action="remove-binding"]')[0]?.trigger('click')
    expect(wrapper.findAll('[data-testid="binding-card"]')).toHaveLength(1)
    const card = wrapper.get('[data-testid="binding-card"]')
    expect(card.find('[data-action="toggle-binding"]').exists()).toBe(false)
    expect(card.find('input[type="checkbox"]').exists()).toBe(true)
    expect(card.get('[data-testid="binding-body"]').exists()).toBe(true)
    const fields = card.get('[data-testid="binding-body"] .row').element.children
    expect([...fields].map((field) => field.className)).toEqual([
      'col-md-6',
      'col-md-6',
      'col-12',
      'col-12',
    ])
    await card.get('[data-testid="binding-body"] input[autocomplete="off"]').setValue('researcher')
    await card.get('textarea').setValue('Research delegated topics')
    await card.get('[data-testid="binding-override"]').setValue(
      '00000000-0000-0000-0000-000000000020',
    )
    await flushPromises()
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()

    expect(api.createPrimaryAgent).toHaveBeenCalledWith(expect.objectContaining({
      subagents: [{
        name: 'researcher',
        description: 'Research delegated topics',
        subagent_override_id: '00000000-0000-0000-0000-000000000020',
        include_client_messages: false,
      }],
    }))
    wrapper.unmount()
  })

  it('uses the Primary layout and one select per Subagent capability', async () => {
    const api = service()
    const primaryPage = await mountPrimaryPage(api)
    const { wrapper } = await mountSubagentPage(api)

    expect(primaryPage.wrapper.get('section.col-lg-8')).toBeTruthy()
    expect(primaryPage.wrapper.get('aside.col-lg-4')).toBeTruthy()
    expect(wrapper.get('section.col-lg-8')).toBeTruthy()
    expect(wrapper.get('aside.col-lg-4')).toBeTruthy()
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

    expect(api.createSubagentOverride).toHaveBeenCalledWith({
      name: '',
      capability_overrides: [
        { type: 'model', mode: 'replace', block_id: '00000000-0000-0000-0000-000000000001' },
        { type: 'system-prompt', mode: 'disabled', block_id: '' },
      ],
      subagents: [],
    })
    wrapper.unmount()
  })

  it('loads a Subagent override from the configuration-library query UUID', async () => {
    const api = service()
    const id = '00000000-0000-0000-0000-000000000020'
    const { wrapper } = await mountSubagentPage(
      api,
      `/agents/subagents?id=${id}`,
    )

    expect(api.getSubagentOverride).toHaveBeenCalledWith(id)
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()
    expect(api.updateSubagentOverride).toHaveBeenCalledWith(
      id,
      expect.objectContaining({ name: 'Override' }),
    )
    wrapper.unmount()
  })

  it('adds a named child to a Subagent override and can reference itself', async () => {
    const api = service()
    const id = '00000000-0000-0000-0000-000000000020'
    const { wrapper } = await mountSubagentPage(api, `/agents/subagents?id=${id}`)

    await buttonByText(wrapper, 'agents.primary.addBinding').trigger('click')
    const binding = wrapper.get('[data-testid="binding-card"]')
    await binding.get('input[autocomplete="off"]').setValue('self_worker')
    await binding.get('textarea').setValue('Continue the same role.')
    await binding.get('[data-testid="binding-override"]').setValue(id)
    await binding.get('input[type="checkbox"]').setValue(true)
    await buttonByText(wrapper, 'common.save').trigger('click')
    await flushPromises()

    expect(api.updateSubagentOverride).toHaveBeenCalledWith(
      id,
      expect.objectContaining({
        subagents: [{
          name: 'self_worker',
          description: 'Continue the same role.',
          subagent_override_id: id,
          include_client_messages: true,
        }],
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

    const firstOverrideId = '00000000-0000-0000-0000-000000000041'
    const secondOverrideId = '00000000-0000-0000-0000-000000000042'
    const firstOverride = deferred<SubagentOverrideProfile>()
    const secondOverride = deferred<SubagentOverrideProfile>()
    const getSubagentOverride = vi.fn((id: string) => (
      id === firstOverrideId ? firstOverride.promise : secondOverride.promise
    ))
    const overrideApi = service({ getSubagentOverride })
    const overridePage = await mountSubagentPage(overrideApi)

    await overridePage.router.push({ path: '/agents/subagents', query: { id: firstOverrideId } })
    await overridePage.router.push({ path: '/agents/subagents', query: { id: secondOverrideId } })
    secondOverride.resolve({
      id: secondOverrideId,
      name: 'Latest Override',
      capability_overrides: [],
      subagents: [],
    })
    await flushPromises()
    firstOverride.resolve({
      id: firstOverrideId,
      name: 'Late Override',
      capability_overrides: [],
      subagents: [],
    })
    await flushPromises()
    await buttonByText(overridePage.wrapper, 'common.save').trigger('click')
    await flushPromises()

    expect(overrideApi.updateSubagentOverride).toHaveBeenCalledWith(
      secondOverrideId,
      expect.objectContaining({ name: 'Latest Override' }),
    )
    overridePage.wrapper.unmount()
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
    expect(wrapper.text()).toContain('agents.feedback.saved')
    expect(wrapper.text()).not.toContain('old_save_failure')
    wrapper.unmount()
  })
})
