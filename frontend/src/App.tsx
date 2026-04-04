import { useState, useEffect } from 'react';
import { Toolbar } from './components/Toolbar';
import { GraphCanvas } from './components/GraphCanvas';
import { InspectorPanel } from './components/InspectorPanel';
import { fetchGraphOverview, fetchNodeDetails, fetchEdgeContext, askQuestion, fetchRepos, runFullIndex, getResolvedApiBase } from './api';

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
  const [selectedRepo, setSelectedRepo] = useState<string | null>(null);
  const [repoList, setRepoList] = useState<any[]>([]);
  const [repoPathInput, setRepoPathInput] = useState('');
  const [newRepoId, setNewRepoId] = useState('');
  const [repoError, setRepoError] = useState<string | null>(null);
  const [includeTests, setIncludeTests] = useState(false);

  const loadRepos = async () => {
    try {
      setRepoError(null);
      const data = await fetchRepos();
      const repos = data?.repos || [];
      setRepoList(repos);
      if (repos.length > 0 && !selectedRepo) {
        const first = repos[0].repo_id || repos[0].id;
        if (first) setSelectedRepo(first);
      }
      if (repos.length === 0) {
        setRepoError(`Connected to ${getResolvedApiBase()} but no repos found in database.`);
      }
    } catch (e) {
      console.error('Failed to load repos', e);
      setRepoError(`Failed to load repos from ${getResolvedApiBase()}. Is backend running and CORS enabled?`);
    }
  };

  // Load initial graph
  useEffect(() => {
    if (selectedRepo) loadGraph();
  }, [mode]);

  useEffect(() => {
    loadRepos();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadGraph = async (forcedQuery?: string) => {
    try {
      setLoading(true);
      const activeRepo = selectedRepo || repoId;
      const data = await fetchGraphOverview(activeRepo, branch, mode, forcedQuery || query, includeTests);
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
      const activeRepo = selectedRepo || repoId;
      const ask = await askQuestion(activeRepo, query, sessionId, role);
      setAnswerData(ask);

      if (ask?.graph?.nodes && ask?.graph?.edges) {
        setGraphData({ nodes: ask.graph.nodes, edges: ask.graph.edges });
      } else {
        const focused = await fetchGraphOverview(activeRepo, branch, 'focused', query, includeTests);
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
      const activeRepo = selectedRepo || repoId;
      const data = await fetchNodeDetails(node.id, activeRepo, type, branch);
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
      const activeRepo = selectedRepo || repoId;
      const data = await fetchEdgeContext(edge.source, edge.target, activeRepo, branch);
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
      <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--border-color)', display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <strong>Repository</strong>
        <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>API: {getResolvedApiBase()}</span>
        <select
          value={selectedRepo || ''}
          onChange={(e) => {
            setSelectedRepo(e.target.value || null);
            setMode('full');
            setAnswerData(null);
            setSelectedNodeId(null);
            setPanelData(null);
            setTimeout(() => loadGraph(), 0);
          }}
          style={{ background: 'var(--bg-base)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: '8px 10px' }}
        >
          <option value="">Select repository...</option>
          {repoList.map((r: any) => {
            const id = r.repo_id || r.id;
            const name = r.name || id;
            return <option key={id} value={id}>{name} ({id})</option>;
          })}
        </select>

        <button
          className="nav-button"
          onClick={loadRepos}
          title="Reload repositories"
        >
          Refresh Repos
        </button>

        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--text-muted)', fontSize: 12 }}>
          <input
            type="checkbox"
            checked={includeTests}
            onChange={(e) => setIncludeTests(e.target.checked)}
          />
          include tests/docs in focused search
        </label>

        <span style={{ color: 'var(--text-muted)' }}>or bring your own:</span>
        <input
          placeholder="repo id"
          value={newRepoId}
          onChange={(e) => setNewRepoId(e.target.value)}
          style={{ background: 'var(--bg-base)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: '8px 10px' }}
        />
        <input
          placeholder="repo path (/home/...)"
          value={repoPathInput}
          onChange={(e) => setRepoPathInput(e.target.value)}
          style={{ minWidth: 280, background: 'var(--bg-base)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: '8px 10px' }}
        />
        <button
          className="nav-button active"
          onClick={async () => {
            if (!newRepoId.trim() || !repoPathInput.trim()) return;
            try {
              await runFullIndex(repoPathInput.trim(), newRepoId.trim(), branch);
              await loadRepos();
              setSelectedRepo(newRepoId.trim());
              setMode('full');
              setTimeout(() => loadGraph(), 0);
            } catch (e) {
              console.error('Index failed', e);
            }
          }}
        >
          Index Repo
        </button>
      </div>
      {repoError && (
        <div style={{ padding: '8px 16px', color: '#ff8a80', borderBottom: '1px solid var(--border-color)', fontSize: 13 }}>
          {repoError}
        </div>
      )}

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
