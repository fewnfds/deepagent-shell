import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  WorkflowComponentDefinition,
  WorkflowComponentInstance,
} from '@/api'

import WorkflowComponentsPage from './WorkflowComponentsPage.vue'

const api = vi.hoisted(() => ({
  listWorkflowComponentDefinitions: vi.fn(),
  saveWorkflowComponentDefinition: vi.fn(),
  deleteWorkflowComponentDefinition: vi.fn(),
  listWorkflowComponentInstances: vi.fn(),
  saveWorkflowComponentInstance: vi.fn(),
  deleteWorkflowComponentInstance: vi.fn(),
}))

const notify = vi.hoisted(() => vi.fn())

vi.mock('@/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api')>()
  return { ...actual, managementApi: api }
})

vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ notify }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

const definition: WorkflowComponentDefinition = {
  id: '11111111-1111-4111-8111-111111111111',
  name: 'Approval router',
  description: 'Routes approvals.',
  runtime_kind: 'python-command',
  state_contract: 'agent-shell.workflow.agent-invocations.v1',
  input_endpoints: [{
    id: 'in',
    label: 'Input',
    activation: 'any',
    accepted_edge_types: ['normal', 'conditional'],
    max_connections: null,
  }],
  output_endpoints: [{
    id: 'approved',
    label: 'Approved',
    edge_type: 'conditional',
    max_connections: 1,
  }],
  config_schema: {
    type: 'object',
    properties: { threshold: { type: 'integer' } },
    required: ['threshold'],
    additionalProperties: false,
  },
  python_source: 'async def run(input):\n    return {"update": {}, "route": "approved"}\n',
  python_requirements: ['httpx>=0.28'],
  requirements_fingerprint: 'fingerprint',
}

const instance: WorkflowComponentInstance = {
  id: '22222222-2222-4222-8222-222222222222',
  definition_id: definition.id,
  name: 'High risk approval',
  description: 'Materialized config.',
  config: { threshold: 3 },
}

beforeEach(() => {
  vi.clearAllMocks()
  api.listWorkflowComponentDefinitions.mockResolvedValue([definition])
  api.listWorkflowComponentInstances.mockResolvedValue([instance])
  api.saveWorkflowComponentDefinition.mockImplementation(async (payload) => ({
    ...definition,
    ...payload,
  }))
  api.saveWorkflowComponentInstance.mockImplementation(async (payload) => ({
    ...instance,
    ...payload,
  }))
})

async function mountPage() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/workflow-components', component: WorkflowComponentsPage },
      { path: '/workflow-components/prepare', component: { template: '<div />' } },
    ],
  })
  await router.push('/workflow-components')
  await router.isReady()
  const wrapper = mount(WorkflowComponentsPage, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

describe('WorkflowComponentsPage', () => {
  it('loads definitions and their materialized instances', async () => {
    const wrapper = await mountPage()

    expect(api.listWorkflowComponentDefinitions).toHaveBeenCalledOnce()
    expect(api.listWorkflowComponentInstances).toHaveBeenCalledWith(definition.id)
    expect(wrapper.get('#workflow-component-definition-name').element).toHaveProperty(
      'value',
      definition.name,
    )
    expect(wrapper.get('#workflow-component-instance-name').element).toHaveProperty(
      'value',
      instance.name,
    )
    expect(wrapper.get('a').attributes('href')).toContain('/workflow-components/prepare')
  })

  it('submits parsed definition and instance JSON to the management API', async () => {
    const wrapper = await mountPage()

    await wrapper.get('#workflow-component-definition-name').setValue('Updated router')
    const definitionSection = wrapper.get('[aria-labelledby="workflow-component-definition-heading"]')
    await definitionSection.findAll('button').at(-1)?.trigger('click')
    await flushPromises()

    expect(api.saveWorkflowComponentDefinition).toHaveBeenCalledWith(
      expect.objectContaining({
        id: definition.id,
        name: 'Updated router',
        input_endpoints: definition.input_endpoints,
        config_schema: definition.config_schema,
      }),
    )

    await wrapper.get('#workflow-component-instance-config').setValue('{"threshold": 7}')
    const instanceSection = wrapper.get('[aria-labelledby="workflow-component-instance-heading"]')
    await instanceSection.findAll('button').at(-1)?.trigger('click')
    await flushPromises()

    expect(api.saveWorkflowComponentInstance).toHaveBeenCalledWith(
      expect.objectContaining({
        id: instance.id,
        definition_id: definition.id,
        config: { threshold: 7 },
      }),
    )
  })
})
