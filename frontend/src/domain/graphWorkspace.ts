import type {
  EntryScript,
  Workflow,
  WorkflowDefinition,
  WorkflowEdge,
  WorkflowNode,
  WorkflowNodeCatalogItem,
  WorkflowPosition,
} from '@/api'
import type { Edge, Node } from '@vue-flow/core'

export const API_BOUNDARY_ID = 'boundary-api'
export const ENTRY_BOUNDARY_ID = 'boundary-entry'

export interface BoundaryNodeData {
  boundary: 'api' | 'entry'
  label: string
  detail: string
  entryScriptId?: string
}

export interface GraphNodeData {
  label: string
  type: string
  status?: string
  input_ports: string[]
  output_ports: string[]
  boundary?: BoundaryNodeData['boundary']
}

export function cloneWorkflow(value: WorkflowDefinition | Workflow): WorkflowDefinition | Workflow {
  return JSON.parse(JSON.stringify(value)) as WorkflowDefinition | Workflow
}

export function catalogItem(catalog: WorkflowNodeCatalogItem[], type: string): WorkflowNodeCatalogItem | undefined {
  return catalog.find((item) => item.type === type)
}

function nodePosition(layout: Record<string, WorkflowPosition>, id: string, fallback: WorkflowPosition): WorkflowPosition {
  const value = layout[id]
  return value ? { x: value.x, y: value.y } : { x: fallback.x, y: fallback.y }
}

export function toFlowNodes(
  workflow: WorkflowDefinition,
  catalog: WorkflowNodeCatalogItem[],
  statuses: Record<string, string>,
  entryScript?: EntryScript,
): Node<GraphNodeData>[] {
  const hasCanvasLayout = Object.hasOwn(workflow.layout, API_BOUNDARY_ID)
    && Object.hasOwn(workflow.layout, ENTRY_BOUNDARY_ID)
  const graphNodes = workflow.nodes.map((node, index) => {
    const definition = catalogItem(catalog, node.type)
    const position = hasCanvasLayout
      ? nodePosition(workflow.layout, node.id, { x: 620 + index * 260, y: 160 + index * 100 })
      : { x: 620 + index * 260, y: 160 + index * 100 }
    return {
      id: node.id,
      type: 'graph-node',
      position,
      data: {
        label: node.id,
        type: definition?.title ?? node.type,
        status: statuses[node.id],
        input_ports: definition?.input_ports.map((port) => port.name) ?? [],
        output_ports: definition?.output_ports.map((port) => port.name) ?? [],
      },
    } satisfies Node<GraphNodeData>
  })

  const firstNode = workflow.entry_nodes[0] ?? workflow.nodes[0]?.id
  const boundaryNodes: Node<GraphNodeData>[] = [
    {
      id: API_BOUNDARY_ID,
      type: 'boundary-node',
      position: hasCanvasLayout ? nodePosition(workflow.layout, API_BOUNDARY_ID, { x: 0, y: 160 }) : { x: 0, y: 160 },
      draggable: true,
      selectable: false,
      data: {
        label: 'OpenAI Chat Completions',
        type: 'POST /v1/chat/completions',
        input_ports: [],
        output_ports: ['messages'],
        boundary: 'api',
      },
    },
    {
      id: ENTRY_BOUNDARY_ID,
      type: 'boundary-node',
      position: hasCanvasLayout ? nodePosition(workflow.layout, ENTRY_BOUNDARY_ID, { x: 300, y: 160 }) : { x: 300, y: 160 },
      draggable: true,
      selectable: false,
      data: {
        label: entryScript?.name || 'Entry Script',
        type: entryScript ? 'prepare(messages) → shared State' : 'select an entry script',
        input_ports: ['messages'],
        output_ports: ['state'],
        boundary: 'entry',
        entryScriptId: entryScript?.id,
      },
    },
  ]

  if (!firstNode) return boundaryNodes
  return [...boundaryNodes, ...graphNodes]
}

export function toFlowEdges(
  workflow: WorkflowDefinition,
  catalog: WorkflowNodeCatalogItem[],
  statuses: Record<string, string>,
): Edge[] {
  const definitionEdges = workflow.edges.map((edge) => ({
    id: edge.id,
    type: edge.kind === 'data' ? 'data-edge' : 'control-edge',
    source: edge.source.node,
    target: edge.target.node,
    sourceHandle: edge.source.port,
    targetHandle: edge.target.port,
    animated: edge.kind === 'control' && Boolean(statuses[edge.source.node]),
    data: edge,
  }))
  const firstNode = workflow.entry_nodes[0] ?? workflow.nodes[0]?.id
  const boundaryEdges: Edge[] = [
    {
      id: 'boundary-api-entry',
      type: 'control-edge',
      source: API_BOUNDARY_ID,
      target: ENTRY_BOUNDARY_ID,
      sourceHandle: 'messages',
      targetHandle: 'messages',
      animated: false,
      selectable: false,
      data: { id: 'boundary-api-entry', kind: 'control', source: { node: API_BOUNDARY_ID, port: 'messages' }, target: { node: ENTRY_BOUNDARY_ID, port: 'messages' }, condition: null, system: true },
    },
  ]
  if (firstNode) {
    const firstDefinition = workflow.nodes.find((node) => node.id === firstNode)
    const firstInput = firstDefinition
      ? catalogItem(catalog, firstDefinition.type)?.input_ports[0]?.name
      : undefined
    if (!firstInput) return [...boundaryEdges, ...definitionEdges]
    boundaryEdges.push({
      id: 'boundary-entry-graph',
      type: 'control-edge',
      source: ENTRY_BOUNDARY_ID,
      target: firstNode,
      sourceHandle: 'state',
      targetHandle: firstInput,
      animated: false,
      selectable: false,
      data: { id: 'boundary-entry-graph', kind: 'control', source: { node: ENTRY_BOUNDARY_ID, port: 'state' }, target: { node: firstNode, port: firstInput }, condition: null, system: true },
    })
  }
  return [...boundaryEdges, ...definitionEdges]
}

export function edgeToDefinition(edge: Edge): WorkflowEdge | null {
  const value = edge.data as WorkflowEdge | undefined
  if (!value || edge.id.startsWith('boundary-')) return null
  return {
    id: edge.id,
    kind: value.kind === 'data' ? 'data' : 'control',
    source: { node: edge.source, port: edge.sourceHandle ?? value.source.port },
    target: { node: edge.target, port: edge.targetHandle ?? value.target.port },
    condition: value.condition ?? null,
  }
}

export function nodeFromFlow(node: Node<GraphNodeData>, catalog: WorkflowNodeCatalogItem[], current: WorkflowNode): WorkflowNode {
  const definition = catalogItem(catalog, current.type)
  return {
    ...current,
    type: definition?.type ?? current.type,
    config: { ...current.config },
    id: node.id,
  }
}
