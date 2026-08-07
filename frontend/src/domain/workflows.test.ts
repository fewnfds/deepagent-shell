import { describe, expect, it } from 'vitest'

import { blankWorkflow, nextNodeId, normalizeWorkflow } from './workflows'

describe('workflow domain adapters', () => {
  it('creates a graph with a configurable Main Agent node', () => {
    const draft = blankWorkflow()
    expect(draft.schema_version).toBe(3)
    expect(draft.nodes.map((node) => node.id)).toEqual(['agent-1'])
    expect(draft.interface.inputs).toEqual([])
  })

  it('normalizes incomplete server data without changing the current contract', () => {
    const normalized = normalizeWorkflow({ id: 'workflow-id', revision: 3, name: 'Saved' })
    expect(normalized.id).toBe('workflow-id')
    expect(normalized.revision).toBe(3)
    expect(normalized.nodes.map((node) => node.id)).toEqual(['agent-1'])
  })

  it('allocates stable node ids without colliding', () => {
    const draft = blankWorkflow()
    expect(nextNodeId(draft.nodes, 'builtin.agent')).toBe('agent-2')
    draft.nodes.push({ id: 'agent-2', type: 'builtin.agent', version: '1.0.0', config: {} })
    expect(nextNodeId(draft.nodes, 'builtin.agent')).toBe('agent-3')
  })
})
