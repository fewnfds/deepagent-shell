import type { AgentSessionTimeline, AgentSessionTimelineRun } from '@/api'

type SessionTimelineKind =
  | 'request_input'
  | 'agent_input'
  | 'model_request'
  | 'model_response'
  | 'tool_call'
  | 'tool_result'
  | 'tool_error'
  | 'subagent'
  | 'request_output'

export interface SessionTimelineEntry {
  id: string
  stepId: string
  kind: SessionTimelineKind
  modelRequestNumber: number | null
  timestamp: string
  run: AgentSessionTimelineRun
  data: Record<string, unknown>
}

const DISPLAYED_EVENT_KINDS = new Set<SessionTimelineKind>([
  'agent_input',
  'model_request',
  'model_response',
  'tool_call',
  'tool_result',
  'tool_error',
  'subagent',
])

function eventData(event: Record<string, unknown>): Record<string, unknown> {
  const data = event.data
  return data && typeof data === 'object' && !Array.isArray(data)
    ? data as Record<string, unknown>
    : {}
}

/**
 * Projects persisted events onto one session-wide model-request sequence.
 * Events emitted after a model request keep that request's number until the
 * next model_request event appears. External request input/output remain
 * visible without inventing a model-request number when no model was called.
 */
export function buildSessionTimeline(session: AgentSessionTimeline): SessionTimelineEntry[] {
  const entries: SessionTimelineEntry[] = []
  let modelRequestNumber = 0

  for (const run of session.runs) {
    let activeModelRequestNumber: number | null = null
    entries.push({
      id: `${run.id}:input`,
      stepId: 'input',
      kind: 'request_input',
      modelRequestNumber: null,
      timestamp: run.started_at,
      run,
      data: {},
    })

    run.timeline.forEach((event) => {
      const kind = typeof event.kind === 'string' ? event.kind as SessionTimelineKind : null
      if (!kind || !DISPLAYED_EVENT_KINDS.has(kind)) return
      if (kind === 'model_request') activeModelRequestNumber = ++modelRequestNumber
      entries.push({
        id: `${run.id}:${event.step_id}`,
        stepId: event.step_id,
        kind,
        modelRequestNumber: activeModelRequestNumber,
        timestamp: typeof event.timestamp === 'string' ? event.timestamp : run.started_at,
        run,
        data: eventData(event),
      })
    })

    entries.push({
      id: `${run.id}:output`,
      stepId: 'output',
      kind: 'request_output',
      modelRequestNumber: activeModelRequestNumber,
      timestamp: run.finished_at,
      run,
      data: {},
    })
  }

  return entries
}
