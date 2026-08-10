import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { describe, expect, it, vi } from 'vitest'

import type { MainAgent, WorkflowNodeCatalogItem } from '@/api'
import {
  newAgentCanvasNode,
  WORKFLOW_NODE_DRAG_MIME,
  workflowConnectionEdgeType,
  type WorkflowCanvasEdge,
  type WorkflowCanvasNode,
} from '@/domain/workflowGraph'
import { en } from '@/locales/en'

import WorkflowInspector from './WorkflowInspector.vue'
import WorkflowNodeLibrary from './WorkflowNodeLibrary.vue'

function i18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

const agentCatalog: WorkflowNodeCatalogItem = {
  type: 'agent',
  type_version: 1,
  runtime_kind: 'compiled_subgraph',
  title_key: 'workflow.nodes.agent.title',
  description_key: 'workflow.nodes.agent.description',
  config_schema: {},
  input_handles: [{ id: 'in', kind: 'control', edge_type: 'normal', max_connections: null }],
  output_handles: [{ id: 'next', kind: 'control', edge_type: 'normal', max_connections: null }],
}

const startCatalog: WorkflowNodeCatalogItem = {
  type: 'start',
  type_version: 1,
  runtime_kind: 'graph_entry',
  title_key: 'workflow.nodes.start.title',
  description_key: 'workflow.nodes.start.description',
  config_schema: {},
  input_handles: [],
  output_handles: [{ id: 'next', kind: 'control', edge_type: 'normal', max_connections: null }],
}

const endCatalog: WorkflowNodeCatalogItem = {
  type: 'end',
  type_version: 1,
  runtime_kind: 'graph_exit',
  title_key: 'workflow.nodes.end.title',
  description_key: 'workflow.nodes.end.description',
  config_schema: {},
  input_handles: [{ id: 'in', kind: 'control', edge_type: 'normal', max_connections: null }],
  output_handles: [],
}

const agents: MainAgent[] = [
  { id: 'agent-1', name: 'Research Agent', capability_refs: [], subagents: [] },
  { id: 'agent-2', name: 'Review Agent', capability_refs: [], subagents: [] },
]

describe('Workflow canvas panels', () => {
  it('exposes the backend Agent node as the only drag source', async () => {
    const wrapper = mount(WorkflowNodeLibrary, {
      props: { agent: agentCatalog, collapsed: false, disabled: false },
      global: { plugins: [i18n()] },
    })
    const item = wrapper.get('.workflow-node-library-item')
    const setData = vi.fn()
    const dataTransfer = { effectAllowed: '', setData }

    await item.trigger('dragstart', { dataTransfer })
    await item.trigger('click')

    expect(setData).toHaveBeenCalledWith(WORKFLOW_NODE_DRAG_MIME, 'agent')
    expect(dataTransfer.effectAllowed).toBe('copy')
    expect(wrapper.emitted('addAgent')).toHaveLength(1)
  })

  it('edits the selected Agent reference in the property panel', async () => {
    const node = newAgentCanvasNode('agent-1', agents[0]!.id)
    const wrapper = mount(WorkflowInspector, {
      props: {
        collapsed: false,
        edge: null,
        mainAgents: agents,
        node,
        stateContract: 'agent-shell.workflow.messages.v1',
        workflowName: 'Research Workflow',
      },
      global: { plugins: [i18n()] },
    })

    await wrapper.get('select').setValue(agents[1]!.id)

    expect(wrapper.emitted('updateAgent')).toEqual([[node.id, agents[1]!.id]])
    expect(wrapper.text()).toContain('Main Agent')
  })

  it('allows repeated Agent nodes and multiple normal activation directions', () => {
    const start: WorkflowCanvasNode = {
      id: 'start',
      type: 'start',
      position: { x: 0, y: 0 },
      data: { nodeType: 'start', mainAgentId: '' },
    }
    const first = newAgentCanvasNode('agent-1', agents[0]!.id)
    const second = newAgentCanvasNode('agent-2', agents[0]!.id)
    const end: WorkflowCanvasNode = {
      id: 'end',
      type: 'end',
      position: { x: 720, y: 0 },
      data: { nodeType: 'end', mainAgentId: '' },
    }
    const existing: WorkflowCanvasEdge = {
      id: 'edge-agent-1-end',
      source: first.id,
      sourceHandle: 'next',
      target: end.id,
      targetHandle: 'in',
      data: { edgeType: 'normal' },
    }
    const catalog = [startCatalog, agentCatalog, endCatalog]
    const nodes = [start, first, second, end]

    expect(workflowConnectionEdgeType({
      source: first.id,
      sourceHandle: 'next',
      target: second.id,
      targetHandle: 'in',
    }, nodes, [existing], catalog)).toBe('normal')
    expect(workflowConnectionEdgeType({
      source: second.id,
      sourceHandle: 'next',
      target: end.id,
      targetHandle: 'in',
    }, nodes, [existing], catalog)).toBe('normal')
    expect(workflowConnectionEdgeType({
      source: first.id,
      sourceHandle: 'next',
      target: end.id,
      targetHandle: 'in',
    }, nodes, [existing], catalog)).toBeNull()
  })
})
