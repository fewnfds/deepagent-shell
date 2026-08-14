import {
  MarkerType,
  type Connection,
  type Edge,
  type Node,
  type ViewportTransform,
  type XYPosition,
} from '@vue-flow/core'

import type {
  WorkflowGraphDocument,
  WorkflowGraphEdge,
  WorkflowGraphNode,
  WorkflowConditionOperator,
  WorkflowNodeHandleSpec,
  WorkflowNodeCatalogItem,
  WorkflowNodeType,
} from '@/api'

export interface WorkflowCanvasNodeData {
  nodeType: WorkflowNodeType
  mainAgentId: string
  defer?: boolean
  conditionSource?: 'state' | 'context'
  conditionPath?: string
  conditionOperator?: WorkflowConditionOperator
  conditionValueJson?: string
}

export type WorkflowCanvasNode = Node<WorkflowCanvasNodeData>

export interface WorkflowCanvasEdgeData {
  edgeType: string
}

export type WorkflowCanvasEdge = Edge<WorkflowCanvasEdgeData>

export const WORKFLOW_NODE_DRAG_MIME = 'application/x-agent-shell-workflow-node'
export const WORKFLOW_EDGE_MARKER = MarkerType.ArrowClosed

export const WORKFLOW_CANVAS_EDGE_TYPES = ['normal', 'conditional'] as const
export type WorkflowCanvasEdgeType = (typeof WORKFLOW_CANVAS_EDGE_TYPES)[number]
export type WorkflowEndpointDirection = 'input' | 'output'

export interface WorkflowCanvasState {
  nodes: WorkflowCanvasNode[]
  edges: WorkflowCanvasEdge[]
  viewport: ViewportTransform
}

const defaultPositions = {
  start: { x: 80, y: 180 },
  agent: { x: 360, y: 180 },
  condition: { x: 620, y: 180 },
  end: { x: 680, y: 180 },
} satisfies Record<WorkflowNodeType, { x: number; y: number }>

function canvasNode(node: WorkflowGraphNode, document: WorkflowGraphDocument): WorkflowCanvasNode {
  return {
    id: node.id,
    type: node.type,
    position: document.layout.nodes[node.id] ?? defaultPositions[node.type],
    deletable: node.type === 'agent' || node.type === 'condition',
    data: {
      nodeType: node.type,
      mainAgentId: node.config.main_agent_id ?? '',
      defer: node.config.defer ?? false,
      conditionSource: node.config.source ?? 'state',
      conditionPath: node.config.path ?? '',
      conditionOperator: node.config.operator ?? 'equals',
      conditionValueJson: JSON.stringify(node.config.value ?? null),
    },
  }
}

function isWorkflowCanvasEdgeType(value: string): value is WorkflowCanvasEdgeType {
  return WORKFLOW_CANVAS_EDGE_TYPES.some((edgeType) => edgeType === value)
}

export function workflowCanvasNodeEndpoints(
  catalog: WorkflowNodeCatalogItem[],
  nodeType: WorkflowNodeType,
  direction: WorkflowEndpointDirection,
): WorkflowNodeHandleSpec[] {
  const nodeTypeSpec = catalog.find((item) => item.type === nodeType)
  if (!nodeTypeSpec) return []
  const endpoints = direction === 'output'
    ? nodeTypeSpec.output_handles
    : nodeTypeSpec.input_handles
  return endpoints.filter((endpoint) => isWorkflowCanvasEdgeType(endpoint.edge_type))
}

function catalogHandle(
  catalog: WorkflowNodeCatalogItem[],
  nodeType: WorkflowNodeType,
  handleId: string | null | undefined,
  direction: WorkflowEndpointDirection,
): WorkflowNodeHandleSpec | null {
  if (!handleId) return null
  return workflowCanvasNodeEndpoints(catalog, nodeType, direction)
    .find((endpoint) => endpoint.id === handleId) ?? null
}

function documentEdgeType(
  edge: WorkflowGraphEdge,
  document: WorkflowGraphDocument,
  catalog: WorkflowNodeCatalogItem[],
): string {
  const source = document.definition.nodes.find((node) => node.id === edge.source)
  const target = document.definition.nodes.find((node) => node.id === edge.target)
  if (!source || !target) return ''
  const sourceHandle = catalogHandle(catalog, source.type, edge.source_handle, 'output')
  const targetHandle = catalogHandle(catalog, target.type, edge.target_handle, 'input')
  if (!sourceHandle || !targetHandle) return ''
  return sourceHandle.edge_type === targetHandle.edge_type ? sourceHandle.edge_type : ''
}

export function workflowDocumentToCanvas(
  document: WorkflowGraphDocument,
  catalog: WorkflowNodeCatalogItem[],
): WorkflowCanvasState {
  const sourceNodes = document.definition.nodes.length > 0
    ? document.definition.nodes
    : [
        { id: 'start', type: 'start', type_version: 1, config: {} },
        { id: 'end', type: 'end', type_version: 1, config: {} },
      ] satisfies WorkflowGraphNode[]

  return {
    nodes: sourceNodes.map((node) => canvasNode(node, document)),
    edges: document.definition.edges.map((edge) => {
      const edgeType = documentEdgeType(edge, document, catalog)
      if (!isWorkflowCanvasEdgeType(edgeType)) {
        throw new Error(`Unsupported Workflow edge: ${edge.id}`)
      }
      return {
        id: edge.id,
        source: edge.source,
        sourceHandle: edge.source_handle,
        target: edge.target,
        targetHandle: edge.target_handle,
        type: 'smoothstep',
        markerEnd: WORKFLOW_EDGE_MARKER,
        class: edgeType === 'conditional' ? 'workflow-edge--conditional' : undefined,
        data: { edgeType },
      }
    }),
    viewport: { ...document.layout.viewport },
  }
}

export function workflowCanvasToDocument(
  nodes: WorkflowCanvasNode[],
  edges: WorkflowCanvasEdge[],
  viewport: ViewportTransform,
): WorkflowGraphDocument {
  return {
    definition: {
      schema_version: 1,
      state_contract: 'agent-shell.workflow.agent-invocations.v1',
      nodes: nodes.map((node) => {
        const config = node.data.nodeType === 'agent'
          ? {
              main_agent_id: node.data.mainAgentId,
              ...(node.data.defer ? { defer: true } : {}),
            }
          : node.data.nodeType === 'condition'
            ? {
                source: node.data.conditionSource ?? 'state',
                path: node.data.conditionPath ?? '',
                operator: node.data.conditionOperator ?? 'equals',
                value: ['equals', 'not_equals'].includes(node.data.conditionOperator ?? 'equals')
                  ? JSON.parse(node.data.conditionValueJson ?? 'null') as unknown
                  : null,
              }
          : {}
        return {
          id: node.id,
          type: node.data.nodeType,
          type_version: 1,
          config,
        }
      }),
      edges: edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        source_handle: edge.sourceHandle ?? '',
        target: edge.target,
        target_handle: edge.targetHandle ?? '',
      })),
    },
    layout: {
      nodes: Object.fromEntries(
        nodes.map((node) => [node.id, { x: node.position.x, y: node.position.y }]),
      ),
      viewport: { ...viewport },
    },
  }
}

export function newAgentCanvasNode(
  id: string,
  mainAgentId: string,
  position: XYPosition = defaultPositions.agent,
): WorkflowCanvasNode {
  return {
    id,
    type: 'agent',
    position: { ...position },
    deletable: true,
    data: { nodeType: 'agent', mainAgentId, defer: false },
  }
}

export function newConditionCanvasNode(
  id: string,
  position: XYPosition = defaultPositions.condition,
): WorkflowCanvasNode {
  return {
    id,
    type: 'condition',
    position: { ...position },
    deletable: true,
    data: {
      nodeType: 'condition',
      mainAgentId: '',
      conditionSource: 'context',
      conditionPath: '/prepare/approved',
      conditionOperator: 'equals',
      conditionValueJson: 'true',
    },
  }
}

export function isConditionValueJsonValid(node: WorkflowCanvasNode): boolean {
  if (node.data.nodeType !== 'condition') return true
  if (!['equals', 'not_equals'].includes(node.data.conditionOperator ?? 'equals')) return true
  try {
    JSON.parse(node.data.conditionValueJson ?? '')
    return true
  } catch {
    return false
  }
}

export function nextWorkflowCanvasEdgeId(edges: WorkflowCanvasEdge[]): string {
  let index = 1
  while (edges.some((edge) => edge.id === `edge-${index}`)) index += 1
  return `edge-${index}`
}

export function workflowConnectionEdgeType(
  connection: Connection & { id?: string },
  nodes: WorkflowCanvasNode[],
  edges: WorkflowCanvasEdge[],
  catalog: WorkflowNodeCatalogItem[],
): WorkflowCanvasEdgeType | null {
  const source = nodes.find((node) => node.id === connection.source)
  const target = nodes.find((node) => node.id === connection.target)
  if (!source || !target || source.id === target.id) return null

  const sourceHandle = catalogHandle(
    catalog,
    source.data.nodeType,
    connection.sourceHandle,
    'output',
  )
  const targetHandle = catalogHandle(
    catalog,
    target.data.nodeType,
    connection.targetHandle,
    'input',
  )
  if (
    !sourceHandle
    || !targetHandle
    || !isWorkflowCanvasEdgeType(sourceHandle.edge_type)
    || targetHandle.edge_type !== sourceHandle.edge_type
  ) return null

  const duplicate = edges.some((edge) => (
    edge.id !== connection.id
    && edge.source === connection.source
    && edge.sourceHandle === connection.sourceHandle
    && edge.target === connection.target
    && edge.targetHandle === connection.targetHandle
  ))
  if (duplicate) return null

  const sourceConnections = edges.filter((edge) => (
    edge.id !== connection.id
    && edge.source === connection.source
    && edge.sourceHandle === connection.sourceHandle
  )).length
  if (
    sourceHandle.max_connections !== null
    && sourceConnections >= sourceHandle.max_connections
  ) return null
  const targetConnections = edges.filter((edge) => (
    edge.id !== connection.id
    && edge.target === connection.target
    && edge.targetHandle === connection.targetHandle
  )).length
  if (
    targetHandle.max_connections !== null
    && targetConnections >= targetHandle.max_connections
  ) return null
  return sourceHandle.edge_type
}

export function workflowCanvasEdgeTypesBetween(
  source: WorkflowCanvasNode | null,
  target: WorkflowCanvasNode | null,
  catalog: WorkflowNodeCatalogItem[],
): WorkflowCanvasEdgeType[] {
  if (!source || !target) return []
  const sourceTypes = new Set(
    workflowCanvasNodeEndpoints(catalog, source.data.nodeType, 'output')
      .map((endpoint) => endpoint.edge_type),
  )
  return WORKFLOW_CANVAS_EDGE_TYPES.filter((edgeType) => (
    sourceTypes.has(edgeType)
    && workflowCanvasNodeEndpoints(catalog, target.data.nodeType, 'input')
      .some((endpoint) => endpoint.edge_type === edgeType)
  ))
}
