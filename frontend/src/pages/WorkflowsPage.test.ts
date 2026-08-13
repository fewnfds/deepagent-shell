import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import {
  managementApi,
  type SavedBlock,
  type Workflow,
  type WorkflowGraphDocument,
} from '@/api'
import { useConfirmation } from '@/composables/useConfirmation'
import { useToasts } from '@/composables/useToasts'
import {
  workflowCanvasToDocument,
  workflowDocumentToCanvas,
} from '@/domain/workflowGraph'
import { en } from '@/locales/en'

import WorkflowsPage from './WorkflowsPage.vue'

function i18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

const workflow: Workflow = {
  id: 'workflow-1',
  name: 'Research Workflow',
  description: 'Runs the research agent.',
  filesystem_id: 'filesystem-1',
  workflow_prepare_id: null,
  enabled: true,
}
const filesystem: SavedBlock = {
  id: 'filesystem-1',
  name: 'Shared Filesystem',
}

function testRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/workflows', component: { template: '<div />' } },
      { path: '/workflows/:id/editor', component: { template: '<div />' } },
    ],
  })
}

afterEach(() => {
  vi.restoreAllMocks()
  useConfirmation().cancel()
  const toasts = useToasts()
  for (const toast of toasts.items.value) toasts.dismiss(toast.id)
})

describe('WorkflowsPage', () => {
  it('loads Workflows and performs create and delete operations', async () => {
    vi.spyOn(managementApi, 'listWorkflows').mockResolvedValue([workflow])
    vi.spyOn(managementApi, 'listBlocks').mockResolvedValue([filesystem])
    const create = vi.spyOn(managementApi, 'createWorkflow').mockResolvedValue(workflow)
    const remove = vi.spyOn(managementApi, 'deleteWorkflow').mockResolvedValue({ ok: true })
    const router = testRouter()
    await router.push('/workflows')
    await router.isReady()

    const wrapper = mount(WorkflowsPage, { global: { plugins: [i18n(), router] } })
    await flushPromises()

    expect(wrapper.text()).toContain(workflow.name)
    expect(wrapper.text()).toContain('Configure')
    expect(wrapper.text()).toContain('Edit Flow')
    await wrapper.findAll('button').find((button) => button.text() === 'New')!.trigger('click')
    await flushPromises()

    await wrapper.get('#workflow-form input[type="text"]').setValue('New Workflow')
    await wrapper.get('#workflow-form textarea').setValue('New description')
    await wrapper.get('#workflow-form select[required]').setValue(filesystem.id)
    await wrapper.get('#workflow-form').trigger('submit')
    await flushPromises()

    expect(create).toHaveBeenCalledWith({
      name: 'New Workflow',
      description: 'New description',
      filesystem_id: filesystem.id,
      workflow_prepare_id: null,
      enabled: true,
    })

    await wrapper.findAll('button').find((button) => button.text() === 'Delete')!.trigger('click')
    useConfirmation().accept()
    await flushPromises()

    expect(remove).toHaveBeenCalledWith(workflow.id)
    wrapper.unmount()
  })

  it('round-trips the current Vue Flow document and viewport', () => {
    const document: WorkflowGraphDocument = {
      definition: {
        schema_version: 1,
        state_contract: 'agent-shell.workflow.agent-invocations.v1',
        nodes: [
          { id: 'start', type: 'start', type_version: 1, config: {} },
          {
            id: 'agent',
            type: 'agent',
            type_version: 1,
            config: { main_agent_id: '11111111-1111-4111-8111-111111111111' },
          },
          { id: 'end', type: 'end', type_version: 1, config: {} },
        ],
        edges: [
          {
            id: 'edge-start-agent',
            source: 'start',
            source_handle: 'next',
            target: 'agent',
            target_handle: 'in',
          },
          {
            id: 'edge-agent-end',
            source: 'agent',
            source_handle: 'next',
            target: 'end',
            target_handle: 'in',
          },
        ],
      },
      layout: {
        nodes: {
          start: { x: 80, y: 180 },
          agent: { x: 360, y: 180 },
          end: { x: 680, y: 180 },
        },
        viewport: { x: 25, y: 40, zoom: 1.25 },
      },
    }

    const canvas = workflowDocumentToCanvas(document, [
      {
        type: 'start',
        type_version: 1,
        runtime_kind: 'graph_entry',
        title_key: '',
        description_key: '',
        config_schema: {},
        input_handles: [],
        output_handles: [{ id: 'next', kind: 'control', edge_type: 'normal', max_connections: null }],
      },
      {
        type: 'agent',
        type_version: 1,
        runtime_kind: 'agent_wrapper',
        title_key: '',
        description_key: '',
        config_schema: {},
        input_handles: [{ id: 'in', kind: 'control', edge_type: 'normal', max_connections: null }],
        output_handles: [{ id: 'next', kind: 'control', edge_type: 'normal', max_connections: null }],
      },
      {
        type: 'end',
        type_version: 1,
        runtime_kind: 'graph_exit',
        title_key: '',
        description_key: '',
        config_schema: {},
        input_handles: [{ id: 'in', kind: 'control', edge_type: 'normal', max_connections: null }],
        output_handles: [],
      },
    ])

    expect(workflowCanvasToDocument(canvas.nodes, canvas.edges, canvas.viewport)).toEqual(document)
  })
})
