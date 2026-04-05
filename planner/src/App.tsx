import { Fragment, FormEvent, MouseEvent, PointerEvent, ReactNode, useEffect, useMemo, useRef, useState } from 'react';
import {
  createEdge,
  edgePath,
  nodeTypePalette,
  seedWorkspaces,
  toolInfo,
  uid,
  type PlannerEdge,
  type PlannerNode,
  type ToolId,
  type Workspace,
} from './plannerCore';
import { streamPlannerTurn, type ChatMessagePayload, type StreamResultEvent } from './api';

interface ChatTurn {
  id: string;
  role: 'user' | 'agent' | 'tool';
  text: string;
  workspaceId: string;
  tools?: ToolId[];
  streaming?: boolean;
}

interface NodeMenuState {
  nodeId: string;
  x: number;
  y: number;
}

function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g).filter(Boolean);
  return parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('*') && part.endsWith('*')) {
      return <em key={`${part}-${index}`}>{part.slice(1, -1)}</em>;
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={`${part}-${index}`}>{part.slice(1, -1)}</code>;
    }
    return <Fragment key={`${part}-${index}`}>{part}</Fragment>;
  });
}

function renderMarkdown(text: string) {
  const lines = text.split('\n');
  const blocks: ReactNode[] = [];
  let listItems: string[] = [];

  const flushList = () => {
    if (!listItems.length) return;
    blocks.push(
      <ul key={`list-${blocks.length}`} className="turn-list">
        {listItems.map((item, index) => (
          <li key={`${item}-${index}`}>{renderInline(item)}</li>
        ))}
      </ul>,
    );
    listItems = [];
  };

  lines.forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      flushList();
      return;
    }
    if (/^[-*]\s+/.test(line)) {
      listItems.push(line.replace(/^[-*]\s+/, ''));
      return;
    }
    flushList();
    if (/^#{1,3}\s+/.test(line)) {
      blocks.push(
        <p key={`heading-${blocks.length}`} className="turn-heading">
          {renderInline(line.replace(/^#{1,3}\s+/, ''))}
        </p>,
      );
      return;
    }
    blocks.push(
      <p key={`paragraph-${blocks.length}`} className="turn-paragraph">
        {renderInline(line)}
      </p>,
    );
  });

  flushList();
  return blocks;
}

export default function App() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>(seedWorkspaces);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState(workspaces[0].id);
  const [turns, setTurns] = useState<ChatTurn[]>([
    {
      id: uid('turn'),
      role: 'agent',
      text: 'I will pull durable points from the conversation, decide whether they belong in this workspace, and link them only when the relation matters.',
      workspaceId: workspaces[0].id,
      tools: ['extract', 'cluster'],
    },
  ]);
  const [input, setInput] = useState(
    'I want the agent to remember the main idea, create nodes when the point matters, and leave a node unconnected when it is just a note.',
  );
  const [selectedNodeId, setSelectedNodeId] = useState<string>(workspaces[0].nodes[0]?.id ?? '');
  const [allowNodes, setAllowNodes] = useState(true);
  const [allowLinks, setAllowLinks] = useState(true);
  const [autoSplit, setAutoSplit] = useState(true);
  const [busy, setBusy] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [announcement, setAnnouncement] = useState('The agent is ready to place workflow nodes, connect stages, or preserve them for the next workspace.');
  const [dragState, setDragState] = useState<{
    workspaceId: string;
    nodeId: string;
    offsetX: number;
    offsetY: number;
  } | null>(null);
  const [nodeMenu, setNodeMenu] = useState<NodeMenuState | null>(null);
  const [inspectorHidden, setInspectorHidden] = useState(false);
  const timersRef = useRef<number[]>([]);
  const chatFeedRef = useRef<HTMLDivElement | null>(null);
  const activeWorkspaceIdRef = useRef(activeWorkspaceId);
  const workspacesRef = useRef(workspaces);
  const turnsRef = useRef(turns);

  useEffect(() => {
    activeWorkspaceIdRef.current = activeWorkspaceId;
  }, [activeWorkspaceId]);

  useEffect(() => {
    workspacesRef.current = workspaces;
  }, [workspaces]);

  useEffect(() => {
    turnsRef.current = turns;
  }, [turns]);

  useEffect(() => {
    const dismissMenu = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setNodeMenu(null);
    };
    window.addEventListener('keydown', dismissMenu);
    return () => {
      window.removeEventListener('keydown', dismissMenu);
    };
  }, []);

  useEffect(() => {
    return () => {
      timersRef.current.forEach((timer) => window.clearTimeout(timer));
      timersRef.current = [];
    };
  }, []);

  useEffect(() => {
    const element = chatFeedRef.current;
    if (!element) return;
    element.scrollTop = element.scrollHeight;
  }, [turns, streamingText, activeWorkspaceId]);

  const activeWorkspace = useMemo(
    () => workspaces.find((workspace) => workspace.id === activeWorkspaceId) ?? workspaces[0],
    [workspaces, activeWorkspaceId],
  );

  const selectedNode = useMemo(
    () => activeWorkspace.nodes.find((node) => node.id === selectedNodeId) ?? activeWorkspace.nodes[0] ?? null,
    [activeWorkspace, selectedNodeId],
  );

  const sourceTurn = useMemo(
    () => turns.find((turn) => turn.id === selectedNode?.sourceTurnId) ?? null,
    [turns, selectedNode?.sourceTurnId],
  );

  const menuNode = useMemo(
    () => activeWorkspace.nodes.find((node) => node.id === nodeMenu?.nodeId) ?? null,
    [activeWorkspace, nodeMenu?.nodeId],
  );

  const agentHistory = useMemo(
    () => turns.filter((turn) => turn.workspaceId === activeWorkspace.id).slice(-8),
    [turns, activeWorkspace.id],
  );

  function updateWorkspace(nextWorkspace: Workspace) {
    setWorkspaces((current) => current.map((workspace) => (workspace.id === nextWorkspace.id ? nextWorkspace : workspace)));
  }

  function addWorkspace(workspace: Workspace) {
    setWorkspaces((current) => [...current, workspace]);
    setActiveWorkspaceId(workspace.id);
    setSelectedNodeId(workspace.nodes[0]?.id ?? '');
  }

  function clearTimers() {
    timersRef.current.forEach((timer) => window.clearTimeout(timer));
    timersRef.current = [];
  }

  function stampNodesWithSource(nodes: PlannerNode[], sourceTurnId: string): PlannerNode[] {
    return nodes.map((node) => ({
      ...node,
      sourceTurnId,
    }));
  }

  function applyNodeMutation(workspaceId: string, mutate: (workspace: Workspace) => Workspace) {
    setWorkspaces((current) => current.map((workspace) => (workspace.id === workspaceId ? mutate(workspace) : workspace)));
  }

  function deleteNode(workspaceId: string, nodeId: string) {
    applyNodeMutation(workspaceId, (workspace) => ({
      ...workspace,
      nodes: workspace.nodes.filter((node) => node.id !== nodeId),
      edges: workspace.edges.filter((edge) => edge.from !== nodeId && edge.to !== nodeId),
    }));
    if (selectedNodeId === nodeId) {
      setSelectedNodeId('');
    }
    setNodeMenu(null);
  }

  function togglePin(workspaceId: string, nodeId: string) {
    applyNodeMutation(workspaceId, (workspace) => ({
      ...workspace,
      nodes: workspace.nodes.map((node) =>
        node.id === nodeId ? { ...node, pinned: !node.pinned } : node,
      ),
    }));
    setNodeMenu(null);
  }

  function renameNode(workspaceId: string, nodeId: string) {
    const workspace = workspacesRef.current.find((entry) => entry.id === workspaceId);
    const node = workspace?.nodes.find((entry) => entry.id === nodeId);
    if (!node) return;
    const nextName = window.prompt('Rename node', node.title)?.trim();
    if (!nextName) return;
    applyNodeMutation(workspaceId, (current) => ({
      ...current,
      nodes: current.nodes.map((entry) =>
        entry.id === nodeId ? { ...entry, title: nextName } : entry,
      ),
    }));
    setNodeMenu(null);
  }

  function connectNodes(workspaceId: string, fromId: string, toId: string, kind: PlannerEdge['kind'] = 'related') {
    applyNodeMutation(workspaceId, (workspace) => {
      const exists = workspace.edges.some(
        (edge) => edge.from === fromId && edge.to === toId && edge.kind === kind,
      );
      if (exists) return workspace;
      return {
        ...workspace,
        edges: [...workspace.edges, createEdge(fromId, toId, kind)],
      };
    });
    setNodeMenu(null);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!input.trim() || busy) return;

    clearTimers();
    setNodeMenu(null);

    const submittedText = input.trim();
    const userTurn: ChatTurn = {
      id: uid('turn'),
      role: 'user',
      text: submittedText,
      workspaceId: activeWorkspaceIdRef.current,
    };
    const assistantTurnId = uid('turn');
    setTurns((current) => [
      ...current,
      userTurn,
      {
        id: assistantTurnId,
        role: 'agent',
        text: '',
        workspaceId: activeWorkspaceIdRef.current,
        streaming: true,
      },
    ]);
    setBusy(true);
    setStreamingText('Opening backend stream.');

    const workspaceSnapshot =
      workspacesRef.current.find((workspace) => workspace.id === activeWorkspaceIdRef.current) ??
      workspacesRef.current[0];
    const recentMessages: ChatMessagePayload[] = [...turnsRef.current, userTurn]
      .slice(-8)
      .map((turn) => ({
        id: turn.id,
        role: turn.role,
        text: turn.text,
        workspaceId: turn.workspaceId,
        tools: turn.tools,
      }));

    void streamPlannerTurn(
      {
        prompt: submittedText,
        workspace: workspaceSnapshot,
        messages: recentMessages,
        allowNodes,
        allowLinks,
      },
      (eventPayload) => {
        if (eventPayload.type === 'status') {
          setStreamingText(eventPayload.message);
          return;
        }

        if (eventPayload.type === 'tool') {
          setStreamingText(eventPayload.message);
          setTurns((current) =>
            current.map((turn) =>
              turn.id === assistantTurnId
                ? { ...turn, role: 'tool', text: 'Planning graph cards and layout...' }
                : turn,
            ),
          );
          return;
        }

        if (eventPayload.type === 'assistant_delta') {
          setTurns((current) =>
            current.map((turn) =>
              turn.id === assistantTurnId
                ? { ...turn, role: 'agent', text: `${turn.text}${eventPayload.delta}` }
                : turn,
            ),
          );
          return;
        }

        applyStreamResult({
          resultEvent: eventPayload,
          sourceTurnId: userTurn.id,
          assistantTurnId,
          workspaceSnapshot,
        });
      },
    ).catch((error: Error) => {
      setStreamingText('');
      setBusy(false);
      setTurns((current) =>
        current.map((turn) =>
          turn.id === assistantTurnId
            ? { ...turn, role: 'agent', text: `Backend error: ${error.message}`, streaming: false }
            : turn,
        ),
      );
      setAnnouncement(`Planner backend request failed. ${error.message}`);
    });
  }

  function applyStreamResult(params: {
    resultEvent: StreamResultEvent;
    sourceTurnId: string;
    assistantTurnId: string;
    workspaceSnapshot: Workspace;
  }) {
    const { resultEvent, sourceTurnId, assistantTurnId, workspaceSnapshot } = params;
    const plan = resultEvent.plan;
    const stampedNodes = stampNodesWithSource([...plan.nodes, ...plan.searchNodes], sourceTurnId);

    if (plan.action === 'split' && autoSplit) {
      const imported = stampedNodes
        .filter((node) => node.imported)
        .map((node) => ({ ...node, pinned: true }));
      const freshNodes = stampedNodes.filter((node) => !node.imported);
      const nextWorkspace: Workspace = {
        id: uid('workspace'),
        label: plan.workspaceLabel,
        topic: plan.workspaceLabel.toLowerCase(),
        drift: plan.drift,
        nodes: [...imported, ...freshNodes],
        edges: [...plan.edges],
        importedFrom: workspaceSnapshot.id,
      };
      addWorkspace(nextWorkspace);
      setAnnouncement(
        `Drift detected (${Math.round(plan.drift * 100)}%). Opening "${plan.workspaceLabel}" and preserving ${imported.length} imported node${imported.length === 1 ? '' : 's'}. ${plan.driftReason}`,
      );
      setSelectedNodeId(nextWorkspace.nodes[0]?.id ?? '');
    } else {
      const seededOnly =
        workspaceSnapshot.nodes.length === 1 &&
        workspaceSnapshot.nodes[0]?.source === 'seed' &&
        workspaceSnapshot.edges.length === 0;
      const nextWorkspace: Workspace = {
        ...workspaceSnapshot,
        label: plan.workspaceLabel,
        topic: plan.workspaceLabel.toLowerCase(),
        drift: plan.drift,
        nodes: seededOnly ? stampedNodes : [...workspaceSnapshot.nodes, ...stampedNodes],
        edges: [...workspaceSnapshot.edges, ...plan.edges],
      };
      updateWorkspace(nextWorkspace);

      if (stampedNodes.length > 0) {
        setSelectedNodeId(stampedNodes[stampedNodes.length - 1].id);
      }

      setAnnouncement(`${plan.summary} ${plan.driftReason}`);
    }

    setTurns((current) =>
      current.map((turn) =>
        turn.id === assistantTurnId
          ? {
              ...turn,
              role: 'agent',
              text: resultEvent.plan.summary,
              tools: plan.tools,
              streaming: false,
            }
          : turn,
      ),
    );
    setStreamingText('');
    setInput('');
    setBusy(false);
  }

  function createWorkspaceManually() {
    const nextWorkspace: Workspace = {
      id: uid('workspace'),
      label: `Workspace ${workspaces.length + 1}`,
      topic: 'fresh memory lane',
      drift: 0,
      nodes: [],
      edges: [],
      importedFrom: activeWorkspace.id,
    };
    addWorkspace(nextWorkspace);
    setAnnouncement('A fresh workspace is open. The canvas is empty and ready for a new chain of thought.');
  }

  function selectNode(nodeId: string) {
    setSelectedNodeId(nodeId);
  }

  function handleNodePointerDown(event: PointerEvent<HTMLButtonElement>, node: PlannerNode) {
    event.currentTarget.setPointerCapture(event.pointerId);
    setSelectedNodeId(node.id);
    setDragState({
      workspaceId: activeWorkspace.id,
      nodeId: node.id,
      offsetX: event.clientX - node.x,
      offsetY: event.clientY - node.y,
    });
  }

  function handleNodeContextMenu(event: MouseEvent<HTMLButtonElement>, node: PlannerNode) {
    event.preventDefault();
    event.stopPropagation();
    setSelectedNodeId(node.id);
    setNodeMenu({
      nodeId: node.id,
      x: event.clientX,
      y: event.clientY,
    });
  }

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    if (!dragState || dragState.workspaceId !== activeWorkspace.id) return;
    setWorkspaces((current) =>
      current.map((workspace) => {
        if (workspace.id !== dragState.workspaceId) return workspace;
        return {
          ...workspace,
          nodes: workspace.nodes.map((node) =>
            node.id === dragState.nodeId
              ? {
                  ...node,
                  x: Math.max(16, event.clientX - dragState.offsetX),
                  y: Math.max(16, event.clientY - dragState.offsetY),
                }
              : node,
          ),
        };
      }),
    );
  }

  function stopDragging() {
    setDragState(null);
  }

  const activeToolSet = useMemo(() => {
    const lastAgent = [...turns].reverse().find((turn) => turn.role === 'agent' && turn.workspaceId === activeWorkspace.id);
    return lastAgent?.tools ?? (['extract', 'cluster'] as ToolId[]);
  }, [turns, activeWorkspace.id]);

  const importedNodes = activeWorkspace.nodes.filter((node) => node.imported);
  const structuredNodeCount = activeWorkspace.nodes.filter((node) => node.type !== 'concept').length;
  const orderedNodes = [...activeWorkspace.nodes].sort((left, right) => left.y - right.y || left.x - right.x);
  const groupedRegions = useMemo(() => {
    const adjacency = new Map<string, Set<string>>();
    const nodeMap = new Map(activeWorkspace.nodes.map((node) => [node.id, node]));

    activeWorkspace.nodes.forEach((node) => adjacency.set(node.id, new Set()));
    activeWorkspace.edges.forEach((edge) => {
      adjacency.get(edge.from)?.add(edge.to);
      adjacency.get(edge.to)?.add(edge.from);
    });

    for (let index = 0; index < orderedNodes.length; index += 1) {
      for (let next = index + 1; next < orderedNodes.length; next += 1) {
        const left = orderedNodes[index];
        const right = orderedNodes[next];
        const closeX = Math.abs(left.x - right.x) < 280;
        const closeY = Math.abs(left.y - right.y) < 180;
        const sameType = left.type === right.type;
        if (closeX && closeY && sameType) {
          adjacency.get(left.id)?.add(right.id);
          adjacency.get(right.id)?.add(left.id);
        }
      }
    }

    const visited = new Set<string>();
    const regions: Array<{ id: string; label: string; x: number; y: number; width: number; height: number }> = [];

    for (const node of orderedNodes) {
      if (visited.has(node.id)) continue;
      const queue = [node.id];
      const group: PlannerNode[] = [];
      visited.add(node.id);

      while (queue.length > 0) {
        const currentId = queue.shift();
        if (!currentId) continue;
        const current = nodeMap.get(currentId);
        if (!current) continue;
        group.push(current);
        adjacency.get(currentId)?.forEach((neighbor) => {
          if (!visited.has(neighbor)) {
            visited.add(neighbor);
            queue.push(neighbor);
          }
        });
      }

      if (group.length < 2) continue;
      const minX = Math.min(...group.map((entry) => entry.x)) - 26;
      const minY = Math.min(...group.map((entry) => entry.y)) - 26;
      const maxX = Math.max(...group.map((entry) => entry.x + entry.width)) + 26;
      const maxY = Math.max(...group.map((entry) => entry.y + 96)) + 26;
      const label = group.length === 2 ? 'Linked notes' : `${group.length} related notes`;
      regions.push({
        id: `region-${node.id}`,
        label,
        x: minX,
        y: minY,
        width: maxX - minX,
        height: maxY - minY,
      });
    }

    return regions;
  }, [activeWorkspace.edges, activeWorkspace.nodes, orderedNodes]);

  return (
    <div className="planner-shell">
      <div className="planner-radar" />
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">M</span>
          <div>
            <p className="eyebrow">Memory workspace</p>
            <h1>Planner</h1>
          </div>
        </div>

        <div className="workspace-strip">
          {workspaces.map((workspace) => (
              <button
                key={workspace.id}
                type="button"
              className={`workspace-pill ${workspace.id === activeWorkspace.id ? 'is-active' : ''}`}
              onClick={() => {
                setActiveWorkspaceId(workspace.id);
                setSelectedNodeId(workspace.nodes[0]?.id ?? '');
              }}
            >
              <span>{workspace.label}</span>
              <small>{workspace.nodes.length} nodes</small>
            </button>
          ))}
          <button type="button" className="workspace-pill is-ghost" onClick={createWorkspaceManually}>
            + New space
          </button>
        </div>
      </header>

      <main className={`workspace-layout ${inspectorHidden ? 'inspector-hidden' : ''}`}>
        <section className="panel chat-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Conversation</p>
              <h2>Talk through the idea, then shape the rough plan</h2>
              {streamingText ? <p className="live-status">{streamingText}</p> : null}
            </div>
            <div className="signal-box">
              <span className={`dot ${busy ? 'busy' : ''}`} />
              <span>{busy ? 'Planning turn' : 'Idle'}</span>
            </div>
          </div>

          <div className="chat-feed" ref={chatFeedRef}>
            {turns.map((turn) => (
              <article key={turn.id} className={`turn turn-${turn.role}`}>
                <p className="turn-role">{turn.role}</p>
                <div className="turn-text">{renderMarkdown(turn.text)}</div>
                {turn.tools?.length ? (
                  <div className="turn-tools">
                    {turn.tools.map((tool) => (
                      <span key={tool}>{tool}</span>
                    ))}
                  </div>
                ) : null}
                {turn.streaming ? <div className="streaming-bar" /> : null}
              </article>
            ))}
          </div>

          <div className="selected-node-panel">
            <p className="selected-node-label">Selected node</p>
            {selectedNode ? (
              <>
                <div className="selected-node-header">
                  <span className="selected-node-type">{nodeTypePalette[selectedNode.type].label}</span>
                  <strong>{selectedNode.title}</strong>
                </div>
                <p className="selected-node-summary">{selectedNode.detail}</p>
                <p className="selected-node-source">{sourceTurn ? sourceTurn.text : selectedNode.source}</p>
              </>
            ) : (
              <p className="selected-node-summary">Select a node to inspect it here.</p>
            )}
          </div>

          <form className="composer" onSubmit={handleSubmit}>
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Describe the rough plan, note a dependency, or explain what should change..."
              rows={5}
            />
            <div className="composer-footer">
              <div className="toggle-row">
                <label>
                  <input
                    type="checkbox"
                    checked={allowNodes}
                    onChange={(event) => setAllowNodes(event.target.checked)}
                  />
                  Allow node creation
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={allowLinks}
                    onChange={(event) => setAllowLinks(event.target.checked)}
                  />
                  Allow linking
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={autoSplit}
                    onChange={(event) => setAutoSplit(event.target.checked)}
                  />
                  Auto-split on drift
                </label>
              </div>
              <button type="submit" className="submit-btn" disabled={busy || !input.trim()}>
                {busy ? 'Thinking…' : 'Send to planner'}
              </button>
            </div>
          </form>
        </section>

        <section
          className="panel canvas-panel"
          onPointerMove={handlePointerMove}
          onPointerUp={stopDragging}
          onPointerLeave={stopDragging}
        >
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Plan canvas</p>
              <h2>{activeWorkspace.label}</h2>
            </div>
            <div className="metric-row">
              <span>Drift {Math.round(activeWorkspace.drift * 100)}%</span>
              <span>{activeWorkspace.nodes.length} nodes</span>
              <span>{activeWorkspace.edges.length} links</span>
              <span>{structuredNodeCount} structured</span>
            </div>
          </div>

          <div className="announcement">{announcement}</div>

          <div className="canvas-viewport">
            <div className="canvas-stage">
              {groupedRegions.map((region) => (
                <div
                  key={region.id}
                  className="canvas-group"
                  style={{
                    transform: `translate(${region.x}px, ${region.y}px)`,
                    width: region.width,
                    height: region.height,
                  }}
                >
                  <span className="canvas-group-label">{region.label}</span>
                </div>
              ))}
              <svg className="edge-layer" viewBox="0 0 2400 1600" preserveAspectRatio="none">
              {activeWorkspace.edges.map((edge) => {
                const from = activeWorkspace.nodes.find((node) => node.id === edge.from);
                const to = activeWorkspace.nodes.find((node) => node.id === edge.to);
                if (!from || !to) return null;
                return (
                  <g key={edge.id}>
                    <path d={edgePath(from, to)} className={`edge edge-${edge.kind}`} />
                  </g>
                );
              })}
              </svg>

              {orderedNodes.map((node) => {
                const palette = nodeTypePalette[node.type];
                const isSelected = node.id === selectedNode?.id;
                return (
                  <button
                    key={node.id}
                    type="button"
                    className={`node-card node-${node.type} ${isSelected ? 'is-selected' : ''} ${node.imported ? 'is-imported' : ''}`}
                    style={{
                      transform: `translate(${node.x}px, ${node.y}px)`,
                      width: node.width,
                      borderColor: palette.accent,
                      ['--node-accent' as string]: palette.accent,
                      ['--node-tone' as string]: palette.tone,
                    }}
                    onClick={() => selectNode(node.id)}
                    onPointerDown={(event) => handleNodePointerDown(event, node)}
                    onContextMenu={(event) => handleNodeContextMenu(event, node)}
                  >
                    <span className="node-type">{palette.label}</span>
                    <strong>{node.title}</strong>
                    <div className="node-footer">
                      {node.pinned ? <em>pinned</em> : node.imported ? <em>imported</em> : null}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </section>

        <aside className={`panel insight-panel ${inspectorHidden ? 'is-collapsed' : ''}`}>
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Inspector</p>
              <h2>{inspectorHidden ? 'Hidden sidebar' : 'Why the agent placed each node'}</h2>
            </div>
            <button
              type="button"
              className="sidebar-toggle"
              onClick={() => setInspectorHidden((current) => !current)}
            >
              {inspectorHidden ? 'Show sidebar' : 'Hide sidebar'}
            </button>
          </div>

          {!inspectorHidden ? (
            <>
          <div className="insight-card">
            <p className="insight-title">Canvas access</p>
            <p className="muted-copy">
              The canvas stays loose by default. Related notes cluster together automatically when they share links or sit close together. Click a card to read the full description on the left, and use right-click for pin, rename, delete, or manual linking.
            </p>
          </div>

          <div className="insight-card">
            <p className="insight-title">Tool belt</p>
            <div className="chip-row">
              {activeToolSet.map((tool) => (
                <span key={tool} className="tool-chip" title={toolInfo[tool]}>
                  {tool}
                </span>
              ))}
            </div>
          </div>

          <div className="insight-card">
            <p className="insight-title">Workspace anchors</p>
            {importedNodes.length > 0 ? (
              <ul className="anchor-list">
                {importedNodes.map((node) => (
                  <li key={node.id}>{node.title}</li>
                ))}
              </ul>
            ) : (
              <p className="muted-copy">No imported anchors yet. A drift event will carry them into a new workspace.</p>
            )}
          </div>

          <div className="insight-card">
            <p className="insight-title">Agent trail</p>
            <div className="trail-list">
              {agentHistory.map((turn) => (
                <article key={turn.id} className="trail-item">
                  <span>{turn.tools?.join(' · ') ?? 'observe'}</span>
                  <p>{turn.text}</p>
                </article>
              ))}
            </div>
          </div>
            </>
          ) : (
            <div className="collapsed-sidebar-note">
              <button
                type="button"
                className="sidebar-toggle sidebar-toggle-inline"
                onClick={() => setInspectorHidden(false)}
              >
                Reopen inspector
              </button>
            </div>
          )}
        </aside>
      </main>

      {nodeMenu ? <button type="button" className="menu-backdrop" aria-label="Close menu" onClick={() => setNodeMenu(null)} /> : null}

      {nodeMenu && menuNode ? (
        <div
          className="node-menu"
          style={{ left: nodeMenu.x, top: nodeMenu.y }}
          onPointerDown={(event) => event.stopPropagation()}
        >
          <div className="node-menu-header">
            <strong>{menuNode.title}</strong>
            <span>{nodeTypePalette[menuNode.type].label}</span>
          </div>
          <button type="button" onClick={() => togglePin(activeWorkspace.id, menuNode.id)}>
            {menuNode.pinned ? 'Unpin' : 'Pin'}
          </button>
          <button type="button" onClick={() => renameNode(activeWorkspace.id, menuNode.id)}>
            Rename
          </button>
          <button type="button" onClick={() => deleteNode(activeWorkspace.id, menuNode.id)}>
            Delete
          </button>
          {selectedNode && selectedNode.id !== menuNode.id ? (
            <button type="button" onClick={() => connectNodes(activeWorkspace.id, menuNode.id, selectedNode.id, 'related')}>
              Link to selected
            </button>
          ) : null}
          <button type="button" onClick={() => setNodeMenu(null)}>
            Close
          </button>
        </div>
      ) : null}
    </div>
  );
}
