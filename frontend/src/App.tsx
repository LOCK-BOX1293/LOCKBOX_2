import { useState, useEffect } from 'react';
import { Toolbar } from './components/Toolbar';
import { GraphCanvas } from './components/GraphCanvas';
import { InspectorPanel } from './components/InspectorPanel';
import { fetchGraphOverview, fetchNodeDetails, fetchEdgeContext, askQuestion } from './api';

function App() {
  const [mode, setMode] = useState<'full' | 'focused'>('full');
  const [query, setQuery] = useState('');
  const [role, setRole] = useState<'backend' | 'frontend' | 'security' | 'architect' | 'debugger'>('backend');
  const [graphData, setGraphData] = useState<{ nodes: any[], edges: any[] }>({ nodes: [], edges: [] });
  const [answerData, setAnswerData] = useState<any>(null);
  const [, setLoading] = useState(false);
  
  // Right panel states
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [panelData, setPanelData] = useState<any>(null);

  const [repoId] = useState('hackbyte-small');
  const [branch] = useState('main');
  const [sessionId] = useState(`sess-${Date.now()}`);

  // Load initial graph
  useEffect(() => {
    loadGraph();
  }, [mode]);

  const loadGraph = async (forcedQuery?: string) => {
    try {
      setLoading(true);
      const data = await fetchGraphOverview(repoId, branch, mode, forcedQuery || query);
      setGraphData(data);
      setSelectedNodeId(null);
      setPanelData(null);
    } catch (e) {
      console.error('Failed to load graph from backend', e);
      setGraphData({ nodes: [], edges: [] });
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const ask = await askQuestion(repoId, query, sessionId, role);
      setAnswerData(ask);

      if (ask?.graph?.nodes && ask?.graph?.edges) {
        setGraphData({ nodes: ask.graph.nodes, edges: ask.graph.edges });
      } else {
        const focused = await fetchGraphOverview(repoId, branch, 'focused', query);
        setGraphData(focused);
      }

      setMode('focused');
    } catch (e) {
      console.error('Failed to ask backend', e);
      // fallback focused graph for resilience
      await loadGraph(query);
    } finally {
      setLoading(false);
    }
  };

  const handleNodeClick = async (node: any) => {
    setSelectedNodeId(node.id);
    const type = node.data?.type || 'file';
    try {
      const data = await fetchNodeDetails(node.id, repoId, type, branch);
      setPanelData(data);
    } catch (e) {
      console.error('Failed to load node details from backend', e);
      setPanelData({
        title: node.id,
        file_path: 'unknown',
        functions: [],
        code: 'Failed to fetch node details from backend.',
        key_points: []
      });
    }
  };

  const handleEdgeClick = async (edge: any) => {
    try {
      const data = await fetchEdgeContext(edge.source, edge.target, repoId, branch);
      setSelectedNodeId(`${edge.source} -> ${edge.target}`);
      setPanelData(data);
    } catch (e) {
      console.error('Failed to load edge context from backend', e);
      setSelectedNodeId(`${edge.source} -> ${edge.target}`);
      setPanelData({
        title: `Edge Context: ${edge.source} to ${edge.target}`,
        edge_context: 'Failed to fetch edge context from backend.',
        edge_code_snippet: ''
      });
    }
  };

  return (
    <div className="layout-container">
      <Toolbar 
        mode={mode} 
        setMode={setMode} 
        query={query} 
        setQuery={setQuery} 
        role={role}
        setRole={setRole}
        onSearch={handleSearch} 
      />
      {answerData && (
        <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--border-color)', background: 'var(--bg-surface)' }}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>Answer ({answerData.intent})</div>
          <div style={{ fontSize: '0.92rem', whiteSpace: 'pre-wrap' }}>{answerData.answer}</div>
          <div style={{ marginTop: 8, fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            confidence: {Number(answerData.confidence || 0).toFixed(2)} | citations: {Array.isArray(answerData.citations) ? answerData.citations.length : 0}
          </div>
        </div>
      )}
      <div className="workspace">
        <div className="graph-canvas">
          <GraphCanvas 
            data={graphData} 
            onNodeClick={handleNodeClick}
            onEdgeClick={handleEdgeClick}
          />
        </div>
        {selectedNodeId && (
          <InspectorPanel 
            nodeId={selectedNodeId} 
            nodeData={panelData} 
            onClose={() => setSelectedNodeId(null)} 
          />
        )}
      </div>
    </div>
  );
}

export default App;
