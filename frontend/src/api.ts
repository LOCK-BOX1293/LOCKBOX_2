export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8081';

let resolvedApiBase: string | null = null;

function apiBaseCandidates(): string[] {
  const list = [
    API_BASE,
    'http://localhost:8081',
    'http://127.0.0.1:8081',
    'http://localhost:8000',
  ];
  return [...new Set(list.filter(Boolean))];
}

async function requestJson(path: string, init?: RequestInit): Promise<any> {
  const bases = resolvedApiBase ? [resolvedApiBase, ...apiBaseCandidates()] : apiBaseCandidates();

  let lastError: unknown = null;
  for (const base of [...new Set(bases)]) {
    try {
      const res = await fetch(`${base}${path}`, init);
      if (!res.ok) {
        lastError = new Error(`HTTP ${res.status} for ${base}${path}`);
        continue;
      }
      resolvedApiBase = base;
      return res.json();
    } catch (e) {
      lastError = e;
    }
  }

  throw lastError || new Error(`Failed request for ${path}`);
}

export function getResolvedApiBase() {
  return resolvedApiBase || API_BASE;
}

export async function fetchRepos() {
  return requestJson('/repos');
}

export async function runFullIndex(repoPath: string, repoId: string, branch: string = 'main') {
  return requestJson('/index/full', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      repo_path: repoPath,
      repo_id: repoId,
      branch,
    }),
  });
}

export async function fetchGraphOverview(repoId: string, branch: string = 'main', mode: 'full' | 'focused' = 'full', query?: string) {
  const base = getResolvedApiBase();
  const url = new URL(`${base}/graph/overview`);
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
  const base = getResolvedApiBase();
  const url = new URL(`${base}/graph/node/${encodeURIComponent(nodeId)}`);
  url.searchParams.append('repo_id', repoId);
  url.searchParams.append('branch', branch);
  url.searchParams.append('node_type', type);
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error('Failed to fetch node details');
  return res.json();
}

export async function fetchEdgeContext(fromSymbolId: string, toSymbolId: string, repoId: string, branch: string = 'main') {
  const base = getResolvedApiBase();
  const url = new URL(`${base}/graph/edge-context`);
  url.searchParams.append('repo_id', repoId);
  url.searchParams.append('branch', branch);
  url.searchParams.append('from_symbol_id', fromSymbolId);
  url.searchParams.append('to_symbol_id', toSymbolId);
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error('Failed to fetch edge context');
  return res.json();
}

export async function askQuestion(repoId: string, query: string, sessionId: string = 'default', userRole: string = 'backend') {
  const payload = await requestJson('/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      project_id: repoId,
      session_id: sessionId,
      query,
      user_role: userRole
    })
  });
  return payload;
}
