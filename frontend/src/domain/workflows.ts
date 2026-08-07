import type {
  Workflow,
  WorkflowDefinition,
  WorkflowEdge,
  WorkflowNode,
  WorkflowNodeCatalogItem,
} from '@/api'

export function defaultWorkflowPublicId(name: string): string {
  const slug = name.normalize('NFKD').replace(/[^\u0000-\u007F]/g, '').toLowerCase()
    .replace(/[^a-z]+/g, '-').replace(/^-+|-+$/g, '')
  return `workflow-${slug || 'config'}`
}

export function blankWorkflow(): WorkflowDefinition {
  const input: WorkflowNode = { id: 'input', type: 'builtin.input.messages', version: '1.0.0', config: {} }
  const output: WorkflowNode = { id: 'output', type: 'builtin.output.message', version: '1.0.0', config: {} }
  const edge: WorkflowEdge = {
    id: 'input-output',
    source: { node: 'input', port: 'messages' },
    target: { node: 'output', port: 'messages' },
  }
  return {
    public_id: '',
    name: '',
    description: '',
    schema_version: 1,
    enabled: true,
    root_interface: { kind: 'chat', input: 'messages', output: 'message' },
    agent_base: null,
    preparation: [],
    nodes: [input, output],
    edges: [edge],
    layout: {},
  }
}

export function normalizeWorkflow(value: unknown): Workflow {
  const source = value && typeof value === 'object' ? value as Record<string, any> : {}
  return {
    ...blankWorkflow(),
    ...source,
    id: typeof source.id === 'string' ? source.id : '',
    revision: typeof source.revision === 'number' ? source.revision : 0,
    nodes: Array.isArray(source.nodes) ? source.nodes : blankWorkflow().nodes,
    edges: Array.isArray(source.edges) ? source.edges : blankWorkflow().edges,
    layout: source.layout && typeof source.layout === 'object' ? source.layout : {},
  }
}

export function workflowPayload(value: WorkflowDefinition | Workflow): WorkflowDefinition | Workflow {
  return JSON.parse(JSON.stringify(value)) as WorkflowDefinition | Workflow
}

export function nodeCatalogItem(catalog: WorkflowNodeCatalogItem[], type: string): WorkflowNodeCatalogItem | undefined {
  return catalog.find((item) => item.type === type)
}

export function nextNodeId(nodes: WorkflowNode[], type: string): string {
  const prefix = type.split('.').at(-1)?.replace(/[^a-z]+/g, '-') || 'node'
  let index = 1
  while (nodes.some((node) => node.id === `${prefix}-${index}`)) index += 1
  return `${prefix}-${index}`
}

