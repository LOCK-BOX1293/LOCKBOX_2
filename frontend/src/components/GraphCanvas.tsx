import React, { useMemo } from 'react';
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
  // Convert backend data to React Flow format
  const initialNodes: Node[] = useMemo(() => {
    if (!data?.nodes) return [];
    return data.nodes.map((n: any, i: number) => {
      const nodeType = n.node_type || n.type || 'file';
      const label = n.label || n.name || n.id;
      // Basic circle layout math if no positions are given
      const angle = (i / data.nodes.length) * Math.PI * 2;
      const radius = 200 + (Math.random() * 100);
      return {
        id: n.id,
        position: { x: Math.cos(angle) * radius + 400, y: Math.sin(angle) * radius + 300 },
        data: { label, type: nodeType },
        type: 'default',
        style: nodeType === 'symbol' ? customNodeStyles.symbol : customNodeStyles.file
      };
    });
  }, [data]);

  const initialEdges: Edge[] = useMemo(() => {
    if (!data?.edges) return [];
    return data.edges.map((e: any, i: number) => {
      const relation = e.relation || e.type || '';
      return ({
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
      labelStyle: { fill: '#aaa', fontSize: 10, fontWeight: 700 }
    });
    });
  }, [data]);

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
