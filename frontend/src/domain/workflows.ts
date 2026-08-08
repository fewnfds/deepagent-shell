import type {
  Workflow,
  WorkflowDefinition,
  WorkflowEdge,
  WorkflowNode,
  WorkflowNodeCatalogItem,
} from '@/api'

export function blankWorkflow(): WorkflowDefinition {
  return {
    name: '',
    description: '',
    schema_version: 3,
    enabled: true,
    interface: { inputs: [], outputs: [] },
    setup: [],
    nodes: [{ id: 'agent-1', type: 'builtin.agent', version: '1.0.0', config: { profile_id: '' } }],
    entry_nodes: ['agent-1'],
    edges: [],
    layout: {
      'boundary-api': { x: 0, y: 160 },
      'boundary-entry': { x: 300, y: 160 },
      'agent-1': { x: 620, y: 160 },
    },
    recursion_limit: 100,
  }
}

export function normalizeWorkflow(value: unknown): Workflow {
  const source = value && typeof value === 'object' ? value as Record<string, any> : {}
  const blank = blankWorkflow()
  const nodes = Array.isArray(source.nodes) ? source.nodes : blank.nodes
  const layout = source.layout && typeof source.layout === 'object' ? source.layout : {}
  return {
    ...blank,
    ...source,
    id: typeof source.id === 'string' ? source.id : '',
    revision: typeof source.revision === 'number' ? source.revision : 0,
    interface: source.interface && typeof source.interface === 'object' ? source.interface : blank.interface,
    setup: Array.isArray(source.setup) ? source.setup : [],
    nodes,
    entry_nodes: Array.isArray(source.entry_nodes) ? source.entry_nodes : blank.entry_nodes,
    edges: Array.isArray(source.edges) ? source.edges : [],
    layout,
    recursion_limit: typeof source.recursion_limit === 'number' ? source.recursion_limit : blank.recursion_limit,
  }
}

export function workflowPayload(value: WorkflowDefinition | Workflow): WorkflowDefinition | Workflow {
  return JSON.parse(JSON.stringify(value)) as WorkflowDefinition | Workflow
}

export function nodeCatalogItem(catalog: WorkflowNodeCatalogItem[], type: string): WorkflowNodeCatalogItem | undefined {
  return catalog.find((item) => item.type === type)
}

export function nextNodeId(nodes: WorkflowNode[], type: string): string {
  const prefix = type.split('.').at(-1)?.replace(/[^a-z0-9]+/g, '-') || 'node'
  let index = 1
  while (nodes.some((node) => node.id === `${prefix}-${index}`)) index += 1
  return `${prefix}-${index}`
}

export function edgeId(edges: WorkflowEdge[]): string {
  let index = edges.length + 1
  while (edges.some((edge) => edge.id === `edge-${index}`)) index += 1
  return `edge-${index}`
}
