import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { describe, expect, it, vi } from 'vitest'

import type { MainAgent, WorkflowNodeCatalogItem } from '@/api'
import {
  newAgentCanvasNode,
  newConditionCanvasNode,
  nextWorkflowCanvasEdgeId,
  WORKFLOW_NODE_DRAG_MIME,
  workflowCanvasEdgeTypesBetween,
  workflowCanvasNodeEndpoints,
  workflowCanvasToDocument,
  workflowConnectionEdgeType,
  workflowDocumentToCanvas,
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
  runtime_kind: 'agent_wrapper',
  title_key: 'workflow.nodes.agent.title',
  description_key: 'workflow.nodes.agent.description',
  config_schema: {},
  input_handles: [
    { id: 'in', kind: 'control', edge_type: 'normal', max_connections: null },
    { id: 'when', kind: 'control', edge_type: 'conditional', max_connections: null },
  ],
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
  input_handles: [
    { id: 'in', kind: 'control', edge_type: 'normal', max_connections: null },
    { id: 'when', kind: 'control', edge_type: 'conditional', max_connections: null },
  ],
  output_handles: [],
}

const conditionCatalog: WorkflowNodeCatalogItem = {
  type: 'condition',
  type_version: 1,
  runtime_kind: 'state_condition',
  title_key: 'workflow.nodes.condition.title',
  description_key: 'workflow.nodes.condition.description',
  config_schema: {},
  input_handles: agentCatalog.input_handles,
  output_handles: [
    { id: 'match', kind: 'control', edge_type: 'conditional', max_connections: 1 },
    { id: 'otherwise', kind: 'control', edge_type: 'conditional', max_connections: 1 },
  ],
}

const agents: MainAgent[] = [
  { id: 'agent-1', name: 'Research Agent', capability_refs: [], subagents: [] },
  { id: 'agent-2', name: 'Review Agent', capability_refs: [], subagents: [] },
]

describe('Workflow canvas panels', () => {
  it('exposes the backend Agent and Condition node classes', async () => {
    const wrapper = mount(WorkflowNodeLibrary, {
      props: {
        agent: agentCatalog,
        condition: conditionCatalog,
        collapsed: false,
        agentDisabled: false,
        conditionDisabled: false,
      },
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
    expect(wrapper.findAll('.workflow-node-library-item')).toHaveLength(2)
  })

  it('edits the selected Agent reference in the property panel', async () => {
    const node = newAgentCanvasNode('agent-1', agents[0]!.id)
    const wrapper = mount(WorkflowInspector, {
      props: {
        collapsed: false,
        edge: null,
        edgeSourceEndpoints: [],
        edgeTargetEndpoints: [],
        edgeTypeOptions: [],
        inputEndpoints: agentCatalog.input_handles,
        mainAgents: agents,
        node,
        outputEndpoints: agentCatalog.output_handles,
        stateContract: 'agent-shell.workflow.agent-invocations.v1',
        workflowName: 'Research Workflow',
      },
      global: { plugins: [i18n()] },
    })

    await wrapper.get('select').setValue(agents[1]!.id)

    expect(wrapper.emitted('updateAgent')).toEqual([[node.id, agents[1]!.id]])
    expect(wrapper.text()).toContain('Main Agent')
    expect(wrapper.text()).toContain('Input endpoint')
    expect(wrapper.text()).toContain('Normal Edge · in')
  })

  it('selects the semantic Edge class and its declared endpoint identities', async () => {
    const edge: WorkflowCanvasEdge = {
      id: 'edge-agent-end',
      source: 'agent-1',
      sourceHandle: 'next',
      target: 'end',
      targetHandle: 'in',
      data: { edgeType: 'normal' },
    }
    const wrapper = mount(WorkflowInspector, {
      props: {
        collapsed: false,
        edge,
        edgeSourceEndpoints: agentCatalog.output_handles,
        edgeTargetEndpoints: endCatalog.input_handles,
        edgeTypeOptions: ['normal'],
        inputEndpoints: [],
        mainAgents: agents,
        node: null,
        outputEndpoints: [],
        stateContract: 'agent-shell.workflow.agent-invocations.v1',
        workflowName: 'Research Workflow',
      },
      global: { plugins: [i18n()] },
    })

    await wrapper.get('select[name="edge-type"]').setValue('normal')
    await wrapper.get('select[name="source-endpoint"]').setValue('next')
    await wrapper.get('select[name="target-endpoint"]').setValue('in')

    expect(wrapper.emitted('selectEdgeType')).toEqual([[edge.id, 'normal']])
    expect(wrapper.emitted('selectEdgeSourceEndpoint')).toEqual([[edge.id, 'next']])
    expect(wrapper.emitted('selectEdgeTargetEndpoint')).toEqual([[edge.id, 'in']])
  })

  it('edits a Condition source, JSON Pointer, operator, and JSON value', async () => {
    const node = newConditionCanvasNode('condition-1')
    const wrapper = mount(WorkflowInspector, {
      props: {
        collapsed: false,
        edge: null,
        edgeSourceEndpoints: [],
        edgeTargetEndpoints: [],
        edgeTypeOptions: [],
        inputEndpoints: conditionCatalog.input_handles,
        mainAgents: agents,
        node,
        outputEndpoints: conditionCatalog.output_handles,
        stateContract: 'agent-shell.workflow.agent-invocations.v1',
        workflowName: 'Research Workflow',
      },
      global: { plugins: [i18n()] },
    })

    await wrapper.get('#workflow-condition-source').setValue('state')
    await wrapper.get('#workflow-condition-path').setValue('/agent_invocations')
    await wrapper.get('#workflow-condition-operator').setValue('not_equals')
    await wrapper.get('#workflow-condition-value').setValue('null')

    expect(wrapper.emitted('updateConditionSource')).toEqual([[node.id, 'state']])
    expect(wrapper.emitted('updateConditionPath')).toEqual([[node.id, '/agent_invocations']])
    expect(wrapper.emitted('updateConditionOperator')).toEqual([[node.id, 'not_equals']])
    expect(wrapper.emitted('updateConditionValue')).toEqual([[node.id, 'null']])
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

    expect(workflowCanvasNodeEndpoints(catalog, 'agent', 'output')).toEqual(
      agentCatalog.output_handles,
    )
    expect(workflowCanvasEdgeTypesBetween(first, end, catalog)).toEqual(['normal'])
    expect(nextWorkflowCanvasEdgeId([
      existing,
      { ...existing, id: 'edge-1' },
    ])).toBe('edge-2')

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
    expect(workflowConnectionEdgeType(existing, nodes, [existing], catalog)).toBe('normal')
  })

  it('projects conditional endpoints and enforces their declared connection limit', () => {
    const condition = newConditionCanvasNode('condition-1')
    const end: WorkflowCanvasNode = {
      id: 'end',
      type: 'end',
      position: { x: 720, y: 0 },
      data: { nodeType: 'end', mainAgentId: '' },
    }
    const edge: WorkflowCanvasEdge = {
      id: 'edge-1',
      source: condition.id,
      sourceHandle: 'match',
      target: end.id,
      targetHandle: 'when',
      data: { edgeType: 'conditional' },
    }
    const catalog = [conditionCatalog, endCatalog]

    expect(workflowCanvasEdgeTypesBetween(condition, end, catalog)).toEqual(['conditional'])
    expect(workflowConnectionEdgeType(edge, [condition, end], [], catalog)).toBe('conditional')
    expect(workflowConnectionEdgeType({
      source: condition.id,
      sourceHandle: 'match',
      target: end.id,
      targetHandle: 'when',
    }, [condition, end], [edge], catalog)).toBeNull()
  })

  it('round-trips Condition config and conditional Edge presentation', () => {
    const condition = newConditionCanvasNode('condition-1')
    const end: WorkflowCanvasNode = {
      id: 'end',
      type: 'end',
      position: { x: 720, y: 0 },
      data: { nodeType: 'end', mainAgentId: '' },
    }
    const edges: WorkflowCanvasEdge[] = [
      {
        id: 'edge-match',
        source: condition.id,
        sourceHandle: 'match',
        target: end.id,
        targetHandle: 'when',
        data: { edgeType: 'conditional' },
      },
      {
        id: 'edge-otherwise',
        source: condition.id,
        sourceHandle: 'otherwise',
        target: end.id,
        targetHandle: 'when',
        data: { edgeType: 'conditional' },
      },
    ]
    const document = workflowCanvasToDocument(
      [condition, end],
      edges,
      { x: 0, y: 0, zoom: 1 },
    )

    expect(document.definition.nodes[0]?.config).toEqual({
      source: 'context',
      path: '/prepare/approved',
      operator: 'equals',
      value: true,
    })

    const canvas = workflowDocumentToCanvas(
      document,
      [conditionCatalog, endCatalog],
    )
    expect(canvas.nodes[0]?.deletable).toBe(true)
    expect(canvas.nodes[0]?.data.conditionPath).toBe('/prepare/approved')
    expect(canvas.edges.every((edge) => edge.class === 'workflow-edge--conditional')).toBe(true)
  })
})
