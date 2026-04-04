import React, { useMemo } from 'react';
import dagre from 'dagre';
import type {
  Node,
  Edge,
} from '@xyflow/react';
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  MarkerType,
  type ReactFlowInstance
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';


interface GraphCanvasProps {
  data: any;
  onNodeClick: (node: Node) => void;
  onEdgeClick: (edge: Edge) => void;
  loading?: boolean;
}

const customNodeStyles = {
  query: {
    padding: '10px 14px',
    borderRadius: '14px',
    minWidth: 220,
    maxWidth: 300,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: '#2d6cdf',
    color: '#fff',
    border: '2px solid rgba(255,255,255,0.28)',
    boxShadow: '0 6px 16px rgba(0,0,0,0.45)',
    fontSize: '0.72rem',
    fontWeight: 700,
    textAlign: 'center',
  },
  focus: {
    padding: '8px 12px',
    borderRadius: '12px',
    minWidth: 140,
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
  },
  file: {
    padding: '10px 14px',
    borderRadius: '8px',
    minWidth: 150,
    maxWidth: 220,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'var(--color-node-file)',
    color: '#fff',
    border: '2px solid rgba(255,255,255,0.2)',
    boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
    fontSize: '0.65rem',
    wordBreak: 'break-word',
    textAlign: 'center'
  },
  symbol: {
    padding: '8px 12px',
    borderRadius: '8px',
    minWidth: 120,
    maxWidth: 170,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'var(--color-node-symbol)',
    color: '#fff',
    border: '2px solid rgba(255,255,255,0.2)',
    boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
    fontSize: '0.6rem',
    wordBreak: 'break-word',
    textAlign: 'center'
  }
};

export function GraphCanvas({ data, onNodeClick, onEdgeClick, loading = false }: GraphCanvasProps) {
  const flowRef = React.useRef<ReactFlowInstance | null>(null);
  const layouted = useMemo(() => {
    const rawNodes = (data?.nodes || []) as any[];
    const rawEdges = (data?.edges || []) as any[];

    const g = new dagre.graphlib.Graph();
    g.setGraph({
      rankdir: 'LR',
      nodesep: 40,
      ranksep: 120,
      edgesep: 20,
    });
    g.setDefaultEdgeLabel(() => ({}));

    for (const n of rawNodes) {
      const nodeType = n.node_type || n.type || 'file';
      const width =
        nodeType === 'query' ? 280 : nodeType === 'focus' ? 170 : nodeType === 'file' ? 220 : 170;
      const height = nodeType === 'query' ? 76 : nodeType === 'focus' ? 56 : nodeType === 'file' ? 74 : 58;
      g.setNode(n.id, { width, height, nodeType });
    }

    for (const e of rawEdges) {
      if (e?.source && e?.target) {
        g.setEdge(e.source, e.target);
      }
    }

    dagre.layout(g);

    const positionedNodes = rawNodes.map((n: any) => {
      const nodeType = n.node_type || n.type || 'file';
      const fullLabel = n.display_label || n.label || n.name || n.id;
      const shortLabel = String(fullLabel).split('/').slice(-1)[0];
      const dims = g.node(n.id) || { x: 0, y: 0, width: 180, height: 60 };
      return {
        id: n.id,
        position: {
          x: (dims.x || 0) - (dims.width || 180) / 2,
          y: (dims.y || 0) - (dims.height || 60) / 2,
        },
        data: {
          label: shortLabel,
          fullLabel,
          type: nodeType,
          score: n.relevance_score,
          reason: n.reason,
        },
        type: 'default',
        style:
          nodeType === 'query'
            ? customNodeStyles.query
            : nodeType === 'focus'
              ? customNodeStyles.focus
              : nodeType === 'symbol'
                ? customNodeStyles.symbol
                : customNodeStyles.file,
      } as Node;
    });

    const positionedEdges = rawEdges.map((e: any, i: number) => {
      const relation = e.relation || e.type || '';
      return {
        id: `e${i}-${e.source}-${e.target}`,
        source: e.source,
        target: e.target,
        animated: relation !== 'contains',
        style: { stroke: 'var(--color-edge)', strokeWidth: 2 },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: 'var(--color-edge)',
        },
        label: relation,
        labelStyle: { fill: '#aaa', fontSize: 10, fontWeight: 700 },
      } as Edge;
    });

    return { nodes: positionedNodes, edges: positionedEdges };
  }, [data]);

  // Convert backend data to React Flow format
  const initialNodes: Node[] = useMemo(() => {
    return layouted.nodes;
  }, [layouted]);

  const initialEdges: Edge[] = useMemo(() => {
    return layouted.edges;
  }, [layouted]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Update when data changes
  React.useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  React.useEffect(() => {
    if (!loading && flowRef.current) {
      // Re-center graph when data changes so focused graph is visible immediately.
      setTimeout(() => {
        flowRef.current?.fitView({
          padding: 0.25,
          minZoom: 0.25,
          maxZoom: 1.0,
          includeHiddenNodes: false,
        });
      }, 0);
    }
  }, [loading, nodes.length, edges.length]);

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      {loading && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: 'rgba(0,0,0,0.35)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 20,
            color: '#fff',
            fontWeight: 700,
            letterSpacing: 0.3,
          }}
        >
          Loading graph...
        </div>
      )}

      {!loading && (!nodes || nodes.length === 0) && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 10,
            color: 'var(--text-muted)',
            textAlign: 'center',
            padding: 24,
          }}
        >
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
        minZoom={0.2}
        maxZoom={1.4}
        defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
        nodeDragThreshold={2}
        edgesReconnectable={false}
        fitViewOptions={{
          padding: 0.25,
          minZoom: 0.25,
          maxZoom: 1.0,
          includeHiddenNodes: false,
        }}
      >
        <Controls style={{ bottom: 20, left: 20 }} />
        <MiniMap 
          nodeColor={(n) => {
            return n.data?.type === 'symbol' ? '#ff9800' : '#2196f3';
          }}
          maskColor="rgba(0, 0, 0, 0.6)"
          style={{ background: 'var(--bg-surface)' }}
        />
        <Background color="var(--border-highlight)" gap={16} />
      </ReactFlow>
    </div>
  );
}
