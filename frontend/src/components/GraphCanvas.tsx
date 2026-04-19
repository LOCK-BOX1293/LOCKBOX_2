import { useEffect, useMemo, useRef } from 'react';
import dagre from 'dagre';
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  MarkerType,
  type Edge,
  type Node,
  type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

interface GraphCanvasProps {
  data: any;
  onNodeClick: (node: Node) => void;
  onEdgeClick: (edge: Edge) => void;
  loading?: boolean;
}

type NodeKind = 'query' | 'focus' | 'file' | 'symbol' | 'unknown';

interface RawGraphNode {
  id: string;
  label: string;
  displayLabel: string;
  kind: NodeKind;
  score: number;
  reason: string;
}

interface RawGraphEdge {
  source: string;
  target: string;
  relation: string;
}

function normalizeKind(value: unknown): NodeKind {
  const kind = String(value || '').toLowerCase();
  if (kind === 'query' || kind === 'focus' || kind === 'file' || kind === 'symbol') return kind;
  return 'unknown';
}

function normalizeNodes(data: any): RawGraphNode[] {
  const rows: any[] = Array.isArray(data?.nodes) ? data.nodes : [];
  return rows
    .map((row: any): RawGraphNode | null => {
      const id = String(row?.id || '').trim();
      if (!id) return null;
      const label = String(row?.focus_name || row?.label || row?.name || id);
      const displayLabel = String(row?.display_label || row?.label || row?.name || id);
      return {
        id,
        label,
        displayLabel,
        kind: normalizeKind(row?.node_type || row?.type),
        score: Number(row?.relevance_score || 0),
        reason: String(row?.reason || ''),
      };
    })
    .filter((row: RawGraphNode | null): row is RawGraphNode => Boolean(row));
}

function normalizeEdges(data: any): RawGraphEdge[] {
  const rows: any[] = Array.isArray(data?.edges) ? data.edges : [];
  return rows
    .map((row: any): RawGraphEdge | null => {
      const source = String(row?.source || '').trim();
      const target = String(row?.target || '').trim();
      if (!source || !target) return null;
      return {
        source,
        target,
        relation: String(row?.relation || row?.type || row?.edge_type || 'related'),
      };
    })
    .filter((row: RawGraphEdge | null): row is RawGraphEdge => Boolean(row));
}

function edgeColor(relation: string): string {
  if (relation === 'fallbacks_to') return '#e45757';
  if (relation === 'verifies') return '#00c2a8';
  if (relation === 'checks_coverage') return '#69a8ff';
  if (relation === 'focuses_on') return '#9cc8ff';
  if (relation === 'selects') return '#8f7dff';
  if (relation === 'maps_to') return '#b594ff';
  if (relation === 'contains') return '#8d96ab';
  return 'var(--color-edge)';
}

function shortFileLabel(label: string): string {
  if (label.includes('/')) return label.split('/').slice(-1)[0];
  return label;
}

function nodeStyle(kind: NodeKind, isTerminal: boolean): React.CSSProperties {
  if (isTerminal) {
    return {
      padding: '10px 14px',
      borderRadius: '12px',
      minWidth: 200,
      maxWidth: 280,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: '#2fa66f',
      color: '#f7fff9',
      border: '2px solid rgba(255,255,255,0.3)',
      boxShadow: '0 5px 16px rgba(0,0,0,0.35)',
      fontSize: '0.72rem',
      fontWeight: 700,
      textAlign: 'center',
      lineHeight: 1.3,
    };
  }

  if (kind === 'query') {
    return {
      padding: '10px 14px',
      borderRadius: '14px',
      minWidth: 250,
      maxWidth: 330,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: '#2d6cdf',
      color: '#fff',
      border: '2px solid rgba(255,255,255,0.28)',
      boxShadow: '0 6px 16px rgba(0,0,0,0.45)',
      fontSize: '0.74rem',
      fontWeight: 700,
      textAlign: 'center',
      lineHeight: 1.35,
    };
  }

  if (kind === 'focus') {
    return {
      padding: '8px 12px',
      borderRadius: '12px',
      minWidth: 170,
      maxWidth: 240,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: '#7b4dff',
      color: '#fff',
      border: '2px solid rgba(255,255,255,0.25)',
      boxShadow: '0 5px 14px rgba(0,0,0,0.42)',
      fontSize: '0.68rem',
      fontWeight: 700,
      textAlign: 'center',
      lineHeight: 1.3,
    };
  }

  if (kind === 'symbol') {
    return {
      padding: '8px 12px',
      borderRadius: '10px',
      minWidth: 150,
      maxWidth: 220,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--color-node-symbol)',
      color: '#1f1400',
      border: '2px solid rgba(0,0,0,0.2)',
      boxShadow: '0 4px 12px rgba(0,0,0,0.36)',
      fontSize: '0.66rem',
      fontWeight: 800,
      textAlign: 'center',
      lineHeight: 1.3,
    };
  }

  return {
    padding: '9px 13px',
    borderRadius: '10px',
    minWidth: 170,
    maxWidth: 250,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'var(--color-node-file)',
    color: '#fff',
    border: '2px solid rgba(255,255,255,0.2)',
    boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
    fontSize: '0.66rem',
    fontWeight: 700,
    textAlign: 'center',
    lineHeight: 1.3,
    wordBreak: 'break-word',
  };
}

function buildStandardGraph(data: any): { nodes: Node[]; edges: Edge[]; summary: string } {
  const nodes = normalizeNodes(data);
  const edges = normalizeEdges(data);

  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 120, edgesep: 20 });
  g.setDefaultEdgeLabel(() => ({}));

  for (const n of nodes) {
    const width = n.kind === 'query' ? 300 : n.kind === 'focus' ? 180 : n.kind === 'file' ? 230 : 180;
    const height = n.kind === 'query' ? 78 : n.kind === 'focus' ? 58 : n.kind === 'file' ? 72 : 58;
    g.setNode(n.id, { width, height });
  }

  for (const e of edges) {
    g.setEdge(e.source, e.target);
  }

  dagre.layout(g);

  const outDegree = new Map<string, number>();
  for (const n of nodes) outDegree.set(n.id, 0);
  for (const e of edges) outDegree.set(e.source, (outDegree.get(e.source) || 0) + 1);

  const rfNodes = nodes.map((n) => {
    const dims = g.node(n.id) || { x: 0, y: 0, width: 180, height: 60 };
    const visibleLabel = n.kind === 'file' ? shortFileLabel(n.displayLabel) : n.label;
    return {
      id: n.id,
      position: {
        x: (dims.x || 0) - (dims.width || 180) / 2,
        y: (dims.y || 0) - (dims.height || 60) / 2,
      },
      data: {
        label: visibleLabel,
        fullLabel: n.displayLabel,
        type: n.kind,
        score: n.score,
        reason: n.reason,
      },
      type: 'default',
      style: nodeStyle(n.kind, (outDegree.get(n.id) || 0) === 0),
    } as Node;
  });

  const rfEdges = edges.map((e, i) => {
    const color = edgeColor(e.relation);
    return {
      id: `e${i}-${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      animated: e.relation !== 'contains',
      style: { stroke: color, strokeWidth: 2.4 },
      markerEnd: { type: MarkerType.ArrowClosed, color },
      label: e.relation,
      labelStyle: { fill: '#bbb', fontSize: 10, fontWeight: 800 },
    } as Edge;
  });

  return {
    nodes: rfNodes,
    edges: rfEdges,
    summary: `Standard graph: ${rfNodes.length} nodes, ${rfEdges.length} edges`,
  };
}

export function GraphCanvas({ data, onNodeClick, onEdgeClick, loading = false }: GraphCanvasProps) {
  const flowRef = useRef<ReactFlowInstance | null>(null);
  const graph = useMemo(() => buildStandardGraph(data), [data]);
  const [nodes, setNodes, onNodesChange] = useNodesState(graph.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(graph.edges);

  useEffect(() => {
    setNodes(graph.nodes);
    setEdges(graph.edges);
  }, [graph.nodes, graph.edges, setNodes, setEdges]);

  useEffect(() => {
    if (!loading && flowRef.current) {
      setTimeout(() => {
        flowRef.current?.fitView({
          padding: 0.25,
          minZoom: 0.2,
          maxZoom: 1.0,
          includeHiddenNodes: false,
        });
      }, 0);
    }
  }, [loading, nodes.length, edges.length]);

  return (
    <div className="graphflow-root">
      {loading && <div className="graphflow-loading">Loading graph...</div>}

      {!loading && (!nodes || nodes.length === 0) && (
        <div className="graphflow-empty">
          No nodes to show for this repository/query.
          <br />Try changing query, role, or include tests/docs.
        </div>
      )}

      <ReactFlow
        onInit={(instance) => {
          flowRef.current = instance;
        }}
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={(_, node) => onNodeClick(node)}
        onEdgeClick={(_, edge) => onEdgeClick(edge)}
        fitView
        minZoom={0.15}
        maxZoom={1.4}
        defaultViewport={{ x: 0, y: 0, zoom: 0.75 }}
        nodeDragThreshold={2}
        edgesReconnectable={false}
        fitViewOptions={{
          padding: 0.25,
          minZoom: 0.2,
          maxZoom: 1.0,
          includeHiddenNodes: false,
        }}
      >
        <Controls style={{ bottom: 20, left: 20 }} />
        <MiniMap
          nodeColor={(n) => {
            const t = String(n.data?.type || '');
            if (t === 'query') return '#2d6cdf';
            if (t === 'focus') return '#7b4dff';
            if (t === 'symbol') return '#ffb86a';
            return '#4d96ff';
          }}
          maskColor="rgba(0, 0, 0, 0.6)"
          style={{ background: 'var(--bg-surface)' }}
        />
        <Background color="var(--border-highlight)" gap={16} />
      </ReactFlow>
    </div>
  );
}
