import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { describe, expect, it, vi } from 'vitest'

import type { MainAgent, WorkflowNodeCatalogItem } from '@/api'
import {
  newAgentCanvasNode,
  WORKFLOW_NODE_DRAG_MIME,
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
  input_handles: [{ id: 'in', kind: 'control', max_connections: 1 }],
  output_handles: [{ id: 'next', kind: 'control', max_connections: 1 }],
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
    const node = newAgentCanvasNode(agents[0]!.id)
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
})
