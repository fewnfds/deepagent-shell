import { describe, expect, it } from 'vitest'

import {
  blankPrimaryAgent,
  blankSubagentOverride,
  normalizeSubagentBinding,
  overrideSelection,
  primaryAgentPayload,
  setOverrideSelection,
  setReference,
  subagentOverridePayload,
} from './agents'

describe('agent profile adapters', () => {
  it('keeps explicit UUID references and never derives them from names', () => {
    const draft = blankPrimaryAgent()
    draft.name = 'Repeated display name'
    setReference(draft, 'model', '00000000-0000-0000-0000-000000000001')
    draft.capability_refs.push({ type: 'unknown', block_id: 'discarded' })

    expect(primaryAgentPayload(draft)).toEqual({
      name: 'Repeated display name',
      capability_refs: [{
        type: 'model',
        block_id: '00000000-0000-0000-0000-000000000001',
      }, { type: 'unknown', block_id: 'discarded' }],
      subagents: [],
    })
  })

  it('stores only explicit replace or disabled override entries', () => {
    const draft = blankSubagentOverride()
    setOverrideSelection(draft, 'model', 'replace', '00000000-0000-0000-0000-000000000002')
    expect(overrideSelection(draft, 'model').mode).toBe('replace')

    setOverrideSelection(draft, 'model', 'inherit')
    expect(overrideSelection(draft, 'model').mode).toBe('inherit')
    expect(subagentOverridePayload(draft).capability_overrides).toEqual([])
    expect(subagentOverridePayload(draft).subagents).toEqual([])
  })

  it('projects named Subagents from an override with all binding fields', () => {
    const draft = blankSubagentOverride()
    draft.subagents.push({
      name: ' self_worker ',
      description: 'Continue the same role.',
      subagent_override_id: '00000000-0000-0000-0000-000000000020',
    })

    expect(subagentOverridePayload(draft).subagents).toEqual([{
      name: 'self_worker',
      description: 'Continue the same role.',
      subagent_override_id: '00000000-0000-0000-0000-000000000020',
    }])
  })

  it('projects Subagent bindings without removed fields', () => {
    expect(normalizeSubagentBinding({
      enabled: false,
      name: 'researcher',
      description: 'Research delegated topics',
      subagent_override_id: '',
    })).toEqual({
      name: 'researcher',
      description: 'Research delegated topics',
      subagent_override_id: '',
    })
  })
})
