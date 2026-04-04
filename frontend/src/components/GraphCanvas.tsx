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
  MarkerType
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';


interface GraphCanvasProps {
  data: any;
  onNodeClick: (node: Node) => void;
  onEdgeClick: (edge: Edge) => void;
}

const customNodeStyles = {
  file: {
    padding: '10px',
    borderRadius: '50%',
    width: 60,
    height: 60,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'var(--color-node-file)',
    color: '#fff',
    border: '2px solid rgba(255,255,255,0.2)',
    boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
    fontSize: '0.65rem'
  },
  symbol: {
    padding: '8px',
    borderRadius: '50%',
    width: 50,
    height: 50,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'var(--color-node-symbol)',
    color: '#fff',
    border: '2px solid rgba(255,255,255,0.2)',
    boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
    fontSize: '0.6rem'
  }
};

export function GraphCanvas({ data, onNodeClick, onEdgeClick }: GraphCanvasProps) {
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
      const width = nodeType === 'file' ? 220 : 170;
      const height = nodeType === 'file' ? 74 : 58;
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
      const label = n.label || n.name || n.id;
      const dims = g.node(n.id) || { x: 0, y: 0, width: 180, height: 60 };
      return {
        id: n.id,
        position: {
          x: (dims.x || 0) - (dims.width || 180) / 2,
          y: (dims.y || 0) - (dims.height || 60) / 2,
        },
        data: {
          label,
          type: nodeType,
          score: n.relevance_score,
          reason: n.reason,
        },
        type: 'default',
        style: nodeType === 'symbol' ? customNodeStyles.symbol : customNodeStyles.file,
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

  return (
    <div style={{ width: '100%', height: '100%' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={(_, node) => onNodeClick(node)}
        onEdgeClick={(_, edge) => onEdgeClick(edge)}
        fitView
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
