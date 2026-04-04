import { useEffect, useMemo, useRef } from 'react';
import dagre from 'dagre';
import {
  Background,
  Controls,
  MarkerType,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
  type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

interface QueryTraceBoardProps {
  trace: any;
  query: string;
  answer: string;
  onNodeSelect?: (node: TraceNode) => void;
  onEdgeSelect?: (payload: { edge: TraceEdge; sourceNode?: TraceNode; targetNode?: TraceNode }) => void;
}

export type TraceNode = {
  id: string;
  label: string;
  display_label?: string;
  type?: string;
  stage?: string;
  reason?: string;
  relevance_score?: number;
  meta?: Record<string, any>;
};

export type TraceEdge = {
  source: string;
  target: string;
  type?: string;
};

const STAGE_ORDER = ['question', 'route', 'retrieve', 'evidence', 'rank', 'explain', 'citation', 'answer'];

const STAGE_TITLES: Record<string, string> = {
  question: 'Question',
  route: 'Route',
  retrieve: 'Retrieval',
  evidence: 'Evidence',
  rank: 'Path Select',
  explain: 'Synthesis',
  citation: 'Citations',
  answer: 'Answer',
};

function stageIndex(stage?: string): number {
  const index = STAGE_ORDER.indexOf(stage || '');
  return index === -1 ? STAGE_ORDER.length : index;
}

function summarize(node: TraceNode): string {
  if (node.type === 'answer') return node.reason || 'Grounded final answer';
  if (node.reason) return node.reason;
  if (node.type === 'file') return 'Relevant file for this answer.';
  if (node.type === 'symbol') return 'Relevant symbol for this answer.';
  return node.display_label || node.label;
}

function shortMeta(node: TraceNode): string {
  if (node.meta?.file_path) {
    const span = node.meta?.start_line && node.meta?.end_line ? `:${node.meta.start_line}-${node.meta.end_line}` : '';
    return `${node.meta.file_path}${span}`;
  }
  if (typeof node.relevance_score === 'number' && node.relevance_score > 0) return `score ${node.relevance_score.toFixed(2)}`;
  return STAGE_TITLES[node.stage || ''] || (node.stage || node.type || 'trace');
}

function nodeTone(node: TraceNode): string {
  switch (node.type) {
    case 'query':
      return 'query';
    case 'answer':
      return 'answer';
    case 'citation':
      return 'citation';
    case 'file':
      return 'file';
    case 'symbol':
      return 'symbol';
    default:
      return 'stage';
  }
}

function nodeDimensions(node: TraceNode) {
  switch (node.type) {
    case 'query':
      return { width: 320, height: 150 };
    case 'answer':
      return { width: 280, height: 150 };
    case 'file':
      return { width: 228, height: 124 };
    case 'symbol':
      return { width: 214, height: 118 };
    case 'citation':
      return { width: 216, height: 114 };
    default:
      return { width: 198, height: 108 };
  }
}

function relationColor(type?: string): string {
  switch (type) {
    case 'enters':
      return '#8dc2ff';
    case 'runs':
      return '#8e7cff';
    case 'collects':
      return '#f5b667';
    case 'retrieves':
      return '#5bb3ff';
    case 'supports':
      return '#95a6c5';
    case 'highlights':
      return '#ffb05a';
    case 'grounds':
      return '#66d9b2';
    case 'cites':
      return '#6bc89e';
    case 'verifies':
      return '#38d39f';
    case 'produces':
      return '#9df59c';
    default:
      return '#7f8aa5';
  }
}

function buildTraceGraph(trace: any) {
  const nodes: TraceNode[] = Array.isArray(trace?.nodes) ? trace.nodes : [];
  const edges: TraceEdge[] = Array.isArray(trace?.edges) ? trace.edges : [];
  const g = new dagre.graphlib.Graph();
  g.setGraph({
    rankdir: 'LR',
    ranksep: 136,
    nodesep: 34,
    marginx: 48,
    marginy: 32,
  });
  g.setDefaultEdgeLabel(() => ({}));

  for (const node of nodes) {
    const dims = nodeDimensions(node);
    g.setNode(node.id, { ...dims, rank: stageIndex(node.stage) });
  }

  for (const edge of edges) {
    g.setEdge(edge.source, edge.target);
  }

  dagre.layout(g);

  const nodeIndex = new Map(nodes.map((node) => [node.id, node]));
  const rfNodes: Node[] = nodes.map((node) => {
    const dims = g.node(node.id) || { x: 0, y: 0, width: 220, height: 126 };
    const tone = nodeTone(node);
    return {
      id: node.id,
      className: `trace-flow-node trace-flow-node-${tone}`,
      position: {
        x: (dims.x || 0) - (dims.width || 220) / 2,
        y: (dims.y || 0) - (dims.height || 126) / 2,
      },
      data: {
        label: (
          <div className={`trace-node-card trace-node-card-${tone}`}>
            <div className="trace-node-card-topline">
              <span className="trace-node-card-stage-label">{STAGE_TITLES[node.stage || ''] || (node.stage || node.type || 'trace')}</span>
              <span className="trace-node-card-kind">{node.type || 'node'}</span>
            </div>
            <div className="trace-node-card-title">{node.display_label || node.label}</div>
            <div className="trace-node-card-body">{summarize(node)}</div>
            <div className="trace-node-card-meta">{shortMeta(node)}</div>
          </div>
        ),
      },
      type: 'default',
      draggable: true,
      selectable: true,
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      style: {
        width: dims.width || 220,
        minHeight: dims.height || 126,
        padding: 0,
        border: 'none',
        background: 'transparent',
        boxShadow: 'none',
      },
    };
  });

  const rfEdges: Edge[] = edges.map((edge, index) => {
    const color = relationColor(edge.type);
    return {
      id: `trace-edge-${index}-${edge.source}-${edge.target}`,
      source: edge.source,
      target: edge.target,
      type: 'smoothstep',
      animated: edge.type !== 'supports' && edge.type !== 'contains',
      label: edge.type || 'flows_to',
      labelStyle: {
        fill: '#d9e2f7',
        fontSize: 10,
        fontWeight: 800,
      },
      labelBgStyle: {
        fill: 'rgba(9, 12, 18, 0.92)',
        fillOpacity: 1,
        rx: 8,
        ry: 8,
      },
      style: {
        stroke: color,
        strokeWidth: edge.type === 'produces' || edge.type === 'verifies' ? 3.1 : 2.3,
        strokeDasharray: edge.type === 'supports' ? '5 5' : undefined,
      },
      markerEnd: { type: MarkerType.ArrowClosed, color },
      data: {
        sourceNode: nodeIndex.get(edge.source),
        targetNode: nodeIndex.get(edge.target),
      },
    };
  });

  return { nodes: rfNodes, edges: rfEdges, nodeIndex };
}

export function QueryTraceBoard({ trace, query, answer, onNodeSelect, onEdgeSelect }: QueryTraceBoardProps) {
  const flowRef = useRef<ReactFlowInstance | null>(null);
  const traceGraph = useMemo(() => buildTraceGraph(trace), [trace]);
  const [nodes, setNodes, onNodesChange] = useNodesState(traceGraph.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(traceGraph.edges);
  const traceNodes: TraceNode[] = Array.isArray(trace?.nodes) ? trace.nodes : [];
  const traceEdges: TraceEdge[] = Array.isArray(trace?.edges) ? trace.edges : [];

  useEffect(() => {
    setNodes(traceGraph.nodes);
    setEdges(traceGraph.edges);
    requestAnimationFrame(() => {
      flowRef.current?.fitView({ padding: 0.14, duration: 500, maxZoom: 1.1 });
    });
  }, [traceGraph, setEdges, setNodes]);

  return (
    <div className="trace-session">
      <div className="trace-session-head">
        <div>
          <div className="trace-session-kicker">Query Trace Session</div>
          <h2 className="trace-session-title">{query}</h2>
          <div className="trace-session-subtitle">
            Horizontal memory canvas for the actual query trace. Click nodes or links to inspect their details.
          </div>
        </div>
        <div className="trace-session-stats">
          <span>{traceNodes.length} nodes</span>
          <span>{traceEdges.length} links</span>
          <span>confidence {Number(trace?.meta?.confidence || 0).toFixed(2)}</span>
          <span>{trace?.meta?.retrieved_files || 0} retrieved files</span>
        </div>
      </div>

      <div className="trace-canvas-shell">
        <div className="trace-canvas-legend">
          <span className="trace-legend-chip query">query</span>
          <span className="trace-legend-chip stage">system stage</span>
          <span className="trace-legend-chip file">document</span>
          <span className="trace-legend-chip symbol">code node</span>
          <span className="trace-legend-chip citation">evidence</span>
          <span className="trace-legend-chip answer">answer</span>
        </div>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onInit={(instance) => {
            flowRef.current = instance;
          }}
          onNodeClick={(_, node) => {
            const traceNode = traceGraph.nodeIndex.get(node.id);
            if (traceNode) onNodeSelect?.(traceNode);
          }}
          onEdgeClick={(_, edge) => {
            const edgeData = (edge.data || {}) as { sourceNode?: TraceNode; targetNode?: TraceNode };
            onEdgeSelect?.({
              edge: {
                source: edge.source,
                target: edge.target,
                type: String(edge.label || ''),
              },
              sourceNode: edgeData.sourceNode,
              targetNode: edgeData.targetNode,
            });
          }}
          fitView
          fitViewOptions={{ padding: 0.14 }}
          panOnDrag
          zoomOnScroll
          nodesDraggable
          elementsSelectable
          proOptions={{ hideAttribution: true }}
          className="trace-flow"
        >
          <Background gap={22} size={1.1} color="rgba(179, 191, 220, 0.12)" />
          <Controls showInteractive={false} position="bottom-right" />
        </ReactFlow>
      </div>

      <div className="trace-answer-panel">
        <div className="trace-answer-label">Rendered Answer</div>
        <div className="trace-answer-text">{answer}</div>
      </div>
    </div>
  );
}
