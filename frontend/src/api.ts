export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8081';

export async function fetchGraphOverview(repoId: string, branch: string = 'main', mode: 'full' | 'focused' = 'full', query?: string) {
  const url = new URL(`${API_BASE}/graph/overview`);
  url.searchParams.append('repo_id', repoId);
  url.searchParams.append('branch', branch);
  url.searchParams.append('mode', mode);
  if (query && mode === 'focused') {
    url.searchParams.append('q', query);
  }
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error('Failed to fetch overview');
  return res.json();
}

export async function fetchNodeDetails(nodeId: string, repoId: string, type: 'file' | 'symbol', branch: string = 'main') {
  const url = new URL(`${API_BASE}/graph/node/${encodeURIComponent(nodeId)}`);
  url.searchParams.append('repo_id', repoId);
  url.searchParams.append('branch', branch);
  url.searchParams.append('node_type', type);
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error('Failed to fetch node details');
  return res.json();
}

export async function fetchEdgeContext(fromSymbolId: string, toSymbolId: string, repoId: string, branch: string = 'main') {
  const url = new URL(`${API_BASE}/graph/edge-context`);
  url.searchParams.append('repo_id', repoId);
  url.searchParams.append('branch', branch);
  url.searchParams.append('from_symbol_id', fromSymbolId);
  url.searchParams.append('to_symbol_id', toSymbolId);
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error('Failed to fetch edge context');
  return res.json();
}

export async function askQuestion(repoId: string, query: string, sessionId: string = 'default', userRole: string = 'backend') {
  const res = await fetch(`${API_BASE}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      project_id: repoId,
      session_id: sessionId,
      query,
      user_role: userRole
    })
  });
  if (!res.ok) throw new Error('Failed to ask question');
  return res.json();
}
