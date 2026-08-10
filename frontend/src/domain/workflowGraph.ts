import type { Edge, Node, ViewportTransform, XYPosition } from '@vue-flow/core'

import type {
  WorkflowGraphDocument,
  WorkflowGraphNode,
  WorkflowNodeType,
} from '@/api'

export interface WorkflowCanvasNodeData {
  nodeType: WorkflowNodeType
  mainAgentId: string
}

export type WorkflowCanvasNode = Node<WorkflowCanvasNodeData>

export interface WorkflowCanvasEdgeData {
  edgeType: 'normal'
}

export type WorkflowCanvasEdge = Edge<WorkflowCanvasEdgeData>

export const WORKFLOW_NODE_DRAG_MIME = 'application/x-agent-shell-workflow-node'

export interface WorkflowCanvasState {
  nodes: WorkflowCanvasNode[]
  edges: WorkflowCanvasEdge[]
  viewport: ViewportTransform
}

const defaultPositions = {
  start: { x: 80, y: 180 },
  agent: { x: 360, y: 180 },
  end: { x: 680, y: 180 },
} satisfies Record<WorkflowNodeType, { x: number; y: number }>

function canvasNode(node: WorkflowGraphNode, document: WorkflowGraphDocument): WorkflowCanvasNode {
  return {
    id: node.id,
    type: node.type,
    position: document.layout.nodes[node.id] ?? defaultPositions[node.type],
    deletable: node.type === 'agent',
    data: {
      nodeType: node.type,
      mainAgentId: node.config.main_agent_id ?? '',
    },
  }
}

export function workflowDocumentToCanvas(document: WorkflowGraphDocument): WorkflowCanvasState {
  const sourceNodes = document.definition.nodes.length > 0
    ? document.definition.nodes
    : [
        { id: 'start', type: 'start', type_version: 1, config: {} },
        { id: 'end', type: 'end', type_version: 1, config: {} },
      ] satisfies WorkflowGraphNode[]

  return {
    nodes: sourceNodes.map((node) => canvasNode(node, document)),
    edges: document.definition.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      sourceHandle: edge.source_handle,
      target: edge.target,
      targetHandle: edge.target_handle,
      type: 'smoothstep',
      data: { edgeType: 'normal' },
    })),
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
      state_contract: 'agent-shell.workflow.messages.v1',
      nodes: nodes.map((node) => ({
        id: node.id,
        type: node.data.nodeType,
        type_version: 1,
        config: node.data.nodeType === 'agent'
          ? { main_agent_id: node.data.mainAgentId }
          : {},
      })),
      edges: edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        source_handle: edge.sourceHandle ?? 'next',
        target: edge.target,
        target_handle: edge.targetHandle ?? 'in',
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
  mainAgentId: string,
  position: XYPosition = defaultPositions.agent,
): WorkflowCanvasNode {
  return {
    id: 'agent',
    type: 'agent',
    position: { ...position },
    deletable: true,
    data: { nodeType: 'agent', mainAgentId },
  }
}
