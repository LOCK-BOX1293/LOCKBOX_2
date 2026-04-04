import { useState, useEffect } from 'react';
import { Toolbar } from './components/Toolbar';
import { GraphCanvas } from './components/GraphCanvas';
import { QueryTraceBoard, type TraceNode, type TraceEdge } from './components/QueryTraceBoard';
import { InspectorPanel } from './components/InspectorPanel';
import { fetchGraphOverview, fetchNodeDetails, fetchEdgeContext, askQuestion, fetchRepos, runFullIndex, getResolvedApiBase } from './api';

type QuerySession = {
  id: string;
  query: string;
  answer: any;
  trace: any;
};

function markdownToPlainText(value: string): string {
  const src = String(value || '').replace(/\\n/g, '\n').replace(/\\t/g, '\t');
  return src
    .replace(/\r/g, '')
    .replace(/```[\s\S]*?```/g, (m) => m.replace(/```/g, '').trim())
    .replace(/`([^`]+)`/g, '$1')
    .replace(/!?\[([^\]]+)\]\(([^)]+)\)/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/#{1,6}\s*/g, '')
    .replace(/^>\s?/gm, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/_([^_]+)_/g, '$1')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/^\s*\d+\.\s+/gm, '')
    .replace(/<[^>]+>/g, '')
    .replace(/[\t ]{2,}/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function App() {
  const [mode, setMode] = useState<'full' | 'focused'>('full');
  const [query, setQuery] = useState('');
  const [role, setRole] = useState<'backend' | 'frontend' | 'security' | 'architect' | 'debugger'>('backend');
  const [graphData, setGraphData] = useState<{ nodes: any[], edges: any[] }>({ nodes: [], edges: [] });
  const [answerData, setAnswerData] = useState<any>(null);
  const [querySessions, setQuerySessions] = useState<QuerySession[]>([]);
  const [activeQuerySessionId, setActiveQuerySessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  
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

  const activeRepo = selectedRepo || repoId;
  const activeQuerySession = querySessions.find((session) => session.id === activeQuerySessionId) || null;

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

  // Load graph for browsing mode only. Query mode manages its own trace graph.
  useEffect(() => {
    if (selectedRepo && !answerData) loadGraph();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, selectedRepo, answerData]);

  useEffect(() => {
    loadRepos();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadGraph = async (forcedQuery?: string) => {
    try {
      setLoading(true);
      const q = (forcedQuery || query || '').trim();
      const requestedMode = mode === 'focused' && !q ? 'full' : mode;
      const data = await fetchGraphOverview(activeRepo, branch, requestedMode, q, includeTests);
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
      const ask = await askQuestion(activeRepo, query, sessionId, role);
      const structure = {
        query,
        role,
        repo: activeRepo,
        citations: Array.isArray(ask?.citations) ? ask.citations.length : 0,
        confidence: Number(ask?.confidence || 0),
        intent: ask?.intent || 'unknown',
      };
      setAnswerData({
        ...ask,
        note_summary: `Intent: ${structure.intent}. Confidence: ${structure.confidence.toFixed(2)}. Citations: ${structure.citations}.`,
        query_structure: structure,
      });
      const traceGraph = {
        ...ask?.graph,
        nodes: Array.isArray(ask?.graph?.nodes) ? ask.graph.nodes : [],
        edges: Array.isArray(ask?.graph?.edges) ? ask.graph.edges : [],
        meta: ask?.graph?.meta || {},
      };
      const nextSession: QuerySession = {
        id: String(ask?.graph?.run_id || `${Date.now()}-${query}`),
        query,
        answer: {
          ...ask,
          note_summary: `Intent: ${structure.intent}. Confidence: ${structure.confidence.toFixed(2)}. Citations: ${structure.citations}.`,
          query_structure: structure,
        },
        trace: traceGraph,
      };

      setQuerySessions((prev) => [nextSession, ...prev.filter((session) => session.id !== nextSession.id)].slice(0, 8));
      setActiveQuerySessionId(nextSession.id);
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
      const data = await fetchNodeDetails(node.id, activeRepo, type, branch);
      setPanelData({
        ...data,
        note_summary: `Node selected from ${mode} graph for query context${query ? `: "${query}"` : ''}.`,
      });
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
      const data = await fetchEdgeContext(edge.source, edge.target, activeRepo, branch);
      setSelectedNodeId(`${edge.source} -> ${edge.target}`);
      setPanelData({
        ...data,
        edge_context: `${data?.edge?.edge_type || 'related'} connection between selected nodes`,
        edge_code_snippet: `${(data?.from?.code || '').slice(0, 800)}\n\n---\n\n${(data?.to?.code || '').slice(0, 800)}`,
        note_summary: `Connection picked for query${query ? `: "${query}"` : ''}.`,
        query_structure: {
          source: edge.source,
          target: edge.target,
          relation: edge.label || edge.type || 'related',
        },
      });
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

  const buildTraceNodePanel = async (node: TraceNode) => {
    setSelectedNodeId(node.id);

    if (node.type === 'file' && node.meta?.file_path) {
      try {
        const data = await fetchNodeDetails(node.meta.file_path, activeRepo, 'file', branch);
        setPanelData({
          ...data,
          title: node.display_label || node.label,
          file_path: node.meta.file_path,
          note_summary: `Trace node from query "${activeQuerySession?.query || query}".`,
          query_structure: {
            trace_node_id: node.id,
            type: node.type,
            stage: node.stage,
            relation_role: node.reason,
            relevance_score: node.relevance_score,
            meta: node.meta || {},
          },
          key_points: [node.reason || 'Trace file node', `stage: ${node.stage || 'unknown'}`],
        });
        return;
      } catch (e) {
        console.error('Failed to enrich trace file node details', e);
      }
    }

    setPanelData({
      title: node.display_label || node.label,
      file_path: node.meta?.file_path || `trace/${node.stage || node.type || 'node'}`,
      functions: [],
      code: node.type === 'answer' ? answerData?.answer || '' : JSON.stringify(node.meta || {}, null, 2),
      key_points: [node.reason || 'Trace node', `stage: ${node.stage || 'unknown'}`, `type: ${node.type || 'unknown'}`],
      note_summary: `Trace node selected from query session "${activeQuerySession?.query || query}".`,
      query_structure: {
        trace_node_id: node.id,
        type: node.type,
        stage: node.stage,
        relevance_score: node.relevance_score,
        meta: node.meta || {},
      },
    });
  };

  const buildTraceEdgePanel = (payload: { edge: TraceEdge; sourceNode?: TraceNode; targetNode?: TraceNode }) => {
    const { edge, sourceNode, targetNode } = payload;
    const sourceTitle = sourceNode?.display_label || sourceNode?.label || edge.source;
    const targetTitle = targetNode?.display_label || targetNode?.label || edge.target;

    setSelectedNodeId(`${sourceTitle} -> ${targetTitle}`);
    setPanelData({
      title: edge.type || 'trace link',
      file_path: `${sourceTitle} -> ${targetTitle}`,
      edge_context: `Connection code: ${edge.type || 'flows_to'}. This link connects ${sourceTitle} to ${targetTitle}.`,
      edge_code_snippet: JSON.stringify(
        {
          relation: edge.type || 'flows_to',
          source: {
            id: sourceNode?.id || edge.source,
            type: sourceNode?.type,
            stage: sourceNode?.stage,
            file_path: sourceNode?.meta?.file_path || null,
          },
          target: {
            id: targetNode?.id || edge.target,
            type: targetNode?.type,
            stage: targetNode?.stage,
            file_path: targetNode?.meta?.file_path || null,
          },
        },
        null,
        2,
      ),
      note_summary: `Trace link selected from query session "${activeQuerySession?.query || query}".`,
      query_structure: {
        relation: edge.type || 'flows_to',
        source: sourceNode?.id || edge.source,
        target: targetNode?.id || edge.target,
      },
      edge: {
        source: sourceNode?.id || edge.source,
        target: targetNode?.id || edge.target,
        edge_type: edge.type || 'flows_to',
      },
      from: {
        file_path: sourceNode?.meta?.file_path || sourceTitle,
        symbol_id: sourceNode?.id,
        code: JSON.stringify(sourceNode?.meta || {}, null, 2),
      },
      to: {
        file_path: targetNode?.meta?.file_path || targetTitle,
        symbol_id: targetNode?.id,
        code: JSON.stringify(targetNode?.meta || {}, null, 2),
      },
      key_points: [
        `Initial document/node: ${sourceTitle}`,
        `Final document/node: ${targetTitle}`,
        `Connection code: ${edge.type || 'flows_to'}`,
      ],
    });
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
            setQuerySessions([]);
            setActiveQuerySessionId(null);
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

        <button
          className="nav-button"
          onClick={() => loadGraph()}
          title="Reload graph for selected repository"
        >
          Refresh Graph
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

      {!repoError && (
        <div style={{ padding: '6px 16px', color: 'var(--text-muted)', borderBottom: '1px solid var(--border-color)', fontSize: 12 }}>
          repo: {activeRepo} | nodes: {graphData.nodes.length} | edges: {graphData.edges.length} | mode: {mode}
        </div>
      )}

      <Toolbar 
        mode={mode} 
        setMode={(nextMode) => {
          setMode(nextMode);
          setAnswerData(null);
          setActiveQuerySessionId(null);
        }}
        query={query} 
        setQuery={setQuery} 
        role={role}
        setRole={setRole}
        onSearch={handleSearch} 
      />
      {answerData && (
        <div className="query-response-strip">
          <div className="query-response-head">
            <div className="query-response-title">AI Response ({answerData.intent})</div>
            <div className="query-response-meta">
              confidence: {Number(answerData.confidence || 0).toFixed(2)} | citations: {Array.isArray(answerData.citations) ? answerData.citations.length : 0}
            </div>
          </div>
          <div className="query-response-body">{answerData.note_summary || answerData.answer}</div>
          <details className="query-response-details">
            <summary>View full answer text</summary>
            <div className="query-response-full">{markdownToPlainText(answerData.answer || '')}</div>
          </details>
          <details className="query-response-details">
            <summary>View query structure</summary>
            <pre className="code-block" style={{ marginTop: 8 }}><code>{JSON.stringify(answerData.query_structure || {}, null, 2)}</code></pre>
          </details>
          <div className="query-response-meta">
            confidence: {Number(answerData.confidence || 0).toFixed(2)} | citations: {Array.isArray(answerData.citations) ? answerData.citations.length : 0}
          </div>
        </div>
      )}
      <div className="workspace">
        <div className="graph-canvas">
          {activeQuerySession ? (
            <div className="query-trace-layout">
              <aside className="query-trace-sidebar">
                <div className="query-trace-sidebar-label">Recent Query Sessions</div>
                {querySessions.map((session) => (
                  <button
                    key={session.id}
                    type="button"
                    className={`query-trace-session-tab ${session.id === activeQuerySession.id ? 'active' : ''}`}
                    onClick={() => {
                      setActiveQuerySessionId(session.id);
                      setAnswerData(session.answer);
                    }}
                  >
                    <div className="query-trace-session-title">{session.query}</div>
                    <div className="query-trace-session-meta">
                      confidence {Number(session.answer?.confidence || 0).toFixed(2)}
                    </div>
                  </button>
                ))}
              </aside>

              <QueryTraceBoard
                trace={activeQuerySession.trace}
                query={activeQuerySession.query}
                answer={activeQuerySession.answer?.answer || ''}
                onNodeSelect={buildTraceNodePanel}
                onEdgeSelect={buildTraceEdgePanel}
              />
            </div>
          ) : (
            <GraphCanvas 
              data={graphData} 
              onNodeClick={handleNodeClick}
              onEdgeClick={handleEdgeClick}
              loading={loading}
            />
          )}
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
