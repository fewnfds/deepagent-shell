import { describe, expect, it } from 'vitest'

import { blankWorkflow, defaultWorkflowPublicId, nextNodeId, normalizeWorkflow } from './workflows'

describe('workflow domain adapters', () => {
  it('creates the chat boundary and a deterministic public id', () => {
    const draft = blankWorkflow()
    expect(draft.nodes.map((node) => node.id)).toEqual(['input', 'output'])
    expect(defaultWorkflowPublicId('Daily Report')).toBe('workflow-daily-report')
    expect(defaultWorkflowPublicId('中文')).toBe('workflow-config')
  })

  it('normalizes incomplete server data without changing the current contract', () => {
    const normalized = normalizeWorkflow({ id: 'workflow-id', revision: 3, name: 'Saved' })
    expect(normalized.id).toBe('workflow-id')
    expect(normalized.revision).toBe(3)
    expect(normalized.nodes.map((node) => node.id)).toEqual(['input', 'output'])
  })

  it('allocates stable node ids without colliding', () => {
    const draft = blankWorkflow()
    expect(nextNodeId(draft.nodes, 'builtin.agent.call')).toBe('call-1')
    draft.nodes.push({ id: 'call-1', type: 'builtin.agent.call', version: '1.0.0', config: {} })
    expect(nextNodeId(draft.nodes, 'builtin.agent.call')).toBe('call-2')
  })
})
