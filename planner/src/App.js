import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { createEdge, edgePath, nodeTypePalette, seedWorkspaces, toolInfo, uid, } from './plannerCore';
import { streamPlannerTurn } from './api';
function renderInline(text) {
    const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g).filter(Boolean);
    return parts.map((part, index) => {
        if (part.startsWith('**') && part.endsWith('**')) {
            return _jsx("strong", { children: part.slice(2, -2) }, `${part}-${index}`);
        }
        if (part.startsWith('*') && part.endsWith('*')) {
            return _jsx("em", { children: part.slice(1, -1) }, `${part}-${index}`);
        }
        if (part.startsWith('`') && part.endsWith('`')) {
            return _jsx("code", { children: part.slice(1, -1) }, `${part}-${index}`);
        }
        return _jsx(Fragment, { children: part }, `${part}-${index}`);
    });
}
function renderMarkdown(text) {
    const lines = text.split('\n');
    const blocks = [];
    let listItems = [];
    const flushList = () => {
        if (!listItems.length)
            return;
        blocks.push(_jsx("ul", { className: "turn-list", children: listItems.map((item, index) => (_jsx("li", { children: renderInline(item) }, `${item}-${index}`))) }, `list-${blocks.length}`));
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
            blocks.push(_jsx("p", { className: "turn-heading", children: renderInline(line.replace(/^#{1,3}\s+/, '')) }, `heading-${blocks.length}`));
            return;
        }
        blocks.push(_jsx("p", { className: "turn-paragraph", children: renderInline(line) }, `paragraph-${blocks.length}`));
    });
    flushList();
    return blocks;
}
export default function App() {
    const [workspaces, setWorkspaces] = useState(seedWorkspaces);
    const [activeWorkspaceId, setActiveWorkspaceId] = useState(workspaces[0].id);
    const [turns, setTurns] = useState([
        {
            id: uid('turn'),
            role: 'agent',
            text: 'I will pull durable points from the conversation, decide whether they belong in this workspace, and link them only when the relation matters.',
            workspaceId: workspaces[0].id,
            tools: ['extract', 'cluster'],
        },
    ]);
    const [input, setInput] = useState('I want the agent to remember the main idea, create nodes when the point matters, and leave a node unconnected when it is just a note.');
    const [selectedNodeId, setSelectedNodeId] = useState(workspaces[0].nodes[0]?.id ?? '');
    const [allowNodes, setAllowNodes] = useState(true);
    const [allowLinks, setAllowLinks] = useState(true);
    const [autoSplit, setAutoSplit] = useState(true);
    const [busy, setBusy] = useState(false);
    const [streamingText, setStreamingText] = useState('');
    const [announcement, setAnnouncement] = useState('The agent is ready to place workflow nodes, connect stages, or preserve them for the next workspace.');
    const [dragState, setDragState] = useState(null);
    const [nodeMenu, setNodeMenu] = useState(null);
    const [inspectorHidden, setInspectorHidden] = useState(false);
    const timersRef = useRef([]);
    const chatFeedRef = useRef(null);
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
        const dismissMenu = (event) => {
            if (event.key === 'Escape')
                setNodeMenu(null);
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
        if (!element)
            return;
        element.scrollTop = element.scrollHeight;
    }, [turns, streamingText, activeWorkspaceId]);
    const activeWorkspace = useMemo(() => workspaces.find((workspace) => workspace.id === activeWorkspaceId) ?? workspaces[0], [workspaces, activeWorkspaceId]);
    const selectedNode = useMemo(() => activeWorkspace.nodes.find((node) => node.id === selectedNodeId) ?? activeWorkspace.nodes[0] ?? null, [activeWorkspace, selectedNodeId]);
    const sourceTurn = useMemo(() => turns.find((turn) => turn.id === selectedNode?.sourceTurnId) ?? null, [turns, selectedNode?.sourceTurnId]);
    const menuNode = useMemo(() => activeWorkspace.nodes.find((node) => node.id === nodeMenu?.nodeId) ?? null, [activeWorkspace, nodeMenu?.nodeId]);
    const agentHistory = useMemo(() => turns.filter((turn) => turn.workspaceId === activeWorkspace.id).slice(-8), [turns, activeWorkspace.id]);
    function updateWorkspace(nextWorkspace) {
        setWorkspaces((current) => current.map((workspace) => (workspace.id === nextWorkspace.id ? nextWorkspace : workspace)));
    }
    function addWorkspace(workspace) {
        setWorkspaces((current) => [...current, workspace]);
        setActiveWorkspaceId(workspace.id);
        setSelectedNodeId(workspace.nodes[0]?.id ?? '');
    }
    function clearTimers() {
        timersRef.current.forEach((timer) => window.clearTimeout(timer));
        timersRef.current = [];
    }
    function stampNodesWithSource(nodes, sourceTurnId) {
        return nodes.map((node) => ({
            ...node,
            sourceTurnId,
        }));
    }
    function applyNodeMutation(workspaceId, mutate) {
        setWorkspaces((current) => current.map((workspace) => (workspace.id === workspaceId ? mutate(workspace) : workspace)));
    }
    function deleteNode(workspaceId, nodeId) {
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
    function togglePin(workspaceId, nodeId) {
        applyNodeMutation(workspaceId, (workspace) => ({
            ...workspace,
            nodes: workspace.nodes.map((node) => node.id === nodeId ? { ...node, pinned: !node.pinned } : node),
        }));
        setNodeMenu(null);
    }
    function renameNode(workspaceId, nodeId) {
        const workspace = workspacesRef.current.find((entry) => entry.id === workspaceId);
        const node = workspace?.nodes.find((entry) => entry.id === nodeId);
        if (!node)
            return;
        const nextName = window.prompt('Rename node', node.title)?.trim();
        if (!nextName)
            return;
        applyNodeMutation(workspaceId, (current) => ({
            ...current,
            nodes: current.nodes.map((entry) => entry.id === nodeId ? { ...entry, title: nextName } : entry),
        }));
        setNodeMenu(null);
    }
    function connectNodes(workspaceId, fromId, toId, kind = 'related') {
        applyNodeMutation(workspaceId, (workspace) => {
            const exists = workspace.edges.some((edge) => edge.from === fromId && edge.to === toId && edge.kind === kind);
            if (exists)
                return workspace;
            return {
                ...workspace,
                edges: [...workspace.edges, createEdge(fromId, toId, kind)],
            };
        });
        setNodeMenu(null);
    }
    function handleSubmit(event) {
        event.preventDefault();
        if (!input.trim() || busy)
            return;
        clearTimers();
        setNodeMenu(null);
        const submittedText = input.trim();
        const userTurn = {
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
        const workspaceSnapshot = workspacesRef.current.find((workspace) => workspace.id === activeWorkspaceIdRef.current) ??
            workspacesRef.current[0];
        const recentMessages = [...turnsRef.current, userTurn]
            .slice(-8)
            .map((turn) => ({
            id: turn.id,
            role: turn.role,
            text: turn.text,
            workspaceId: turn.workspaceId,
            tools: turn.tools,
        }));
        void streamPlannerTurn({
            prompt: submittedText,
            workspace: workspaceSnapshot,
            messages: recentMessages,
            allowNodes,
            allowLinks,
        }, (eventPayload) => {
            if (eventPayload.type === 'status') {
                setStreamingText(eventPayload.message);
                return;
            }
            if (eventPayload.type === 'tool') {
                setStreamingText(eventPayload.message);
                setTurns((current) => current.map((turn) => turn.id === assistantTurnId
                    ? { ...turn, role: 'tool', text: 'Planning graph cards and layout...' }
                    : turn));
                return;
            }
            if (eventPayload.type === 'assistant_delta') {
                setTurns((current) => current.map((turn) => turn.id === assistantTurnId
                    ? { ...turn, role: 'agent', text: `${turn.text}${eventPayload.delta}` }
                    : turn));
                return;
            }
            applyStreamResult({
                resultEvent: eventPayload,
                sourceTurnId: userTurn.id,
                assistantTurnId,
                workspaceSnapshot,
            });
        }).catch((error) => {
            setStreamingText('');
            setBusy(false);
            setTurns((current) => current.map((turn) => turn.id === assistantTurnId
                ? { ...turn, role: 'agent', text: `Backend error: ${error.message}`, streaming: false }
                : turn));
            setAnnouncement(`Planner backend request failed. ${error.message}`);
        });
    }
    function applyStreamResult(params) {
        const { resultEvent, sourceTurnId, assistantTurnId, workspaceSnapshot } = params;
        const plan = resultEvent.plan;
        const stampedNodes = stampNodesWithSource([...plan.nodes, ...plan.searchNodes], sourceTurnId);
        if (plan.action === 'split' && autoSplit) {
            const imported = stampedNodes
                .filter((node) => node.imported)
                .map((node) => ({ ...node, pinned: true }));
            const freshNodes = stampedNodes.filter((node) => !node.imported);
            const nextWorkspace = {
                id: uid('workspace'),
                label: plan.workspaceLabel,
                topic: plan.workspaceLabel.toLowerCase(),
                drift: plan.drift,
                nodes: [...imported, ...freshNodes],
                edges: [...plan.edges],
                importedFrom: workspaceSnapshot.id,
            };
            addWorkspace(nextWorkspace);
            setAnnouncement(`Drift detected (${Math.round(plan.drift * 100)}%). Opening "${plan.workspaceLabel}" and preserving ${imported.length} imported node${imported.length === 1 ? '' : 's'}. ${plan.driftReason}`);
            setSelectedNodeId(nextWorkspace.nodes[0]?.id ?? '');
        }
        else {
            const seededOnly = workspaceSnapshot.nodes.length === 1 &&
                workspaceSnapshot.nodes[0]?.source === 'seed' &&
                workspaceSnapshot.edges.length === 0;
            const nextWorkspace = {
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
        setTurns((current) => current.map((turn) => turn.id === assistantTurnId
            ? {
                ...turn,
                role: 'agent',
                text: resultEvent.plan.summary,
                tools: plan.tools,
                streaming: false,
            }
            : turn));
        setStreamingText('');
        setInput('');
        setBusy(false);
    }
    function createWorkspaceManually() {
        const nextWorkspace = {
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
    function selectNode(nodeId) {
        setSelectedNodeId(nodeId);
    }
    function handleNodePointerDown(event, node) {
        event.currentTarget.setPointerCapture(event.pointerId);
        setSelectedNodeId(node.id);
        setDragState({
            workspaceId: activeWorkspace.id,
            nodeId: node.id,
            offsetX: event.clientX - node.x,
            offsetY: event.clientY - node.y,
        });
    }
    function handleNodeContextMenu(event, node) {
        event.preventDefault();
        event.stopPropagation();
        setSelectedNodeId(node.id);
        setNodeMenu({
            nodeId: node.id,
            x: event.clientX,
            y: event.clientY,
        });
    }
    function handlePointerMove(event) {
        if (!dragState || dragState.workspaceId !== activeWorkspace.id)
            return;
        setWorkspaces((current) => current.map((workspace) => {
            if (workspace.id !== dragState.workspaceId)
                return workspace;
            return {
                ...workspace,
                nodes: workspace.nodes.map((node) => node.id === dragState.nodeId
                    ? {
                        ...node,
                        x: Math.max(16, event.clientX - dragState.offsetX),
                        y: Math.max(16, event.clientY - dragState.offsetY),
                    }
                    : node),
            };
        }));
    }
    function stopDragging() {
        setDragState(null);
    }
    const activeToolSet = useMemo(() => {
        const lastAgent = [...turns].reverse().find((turn) => turn.role === 'agent' && turn.workspaceId === activeWorkspace.id);
        return lastAgent?.tools ?? ['extract', 'cluster'];
    }, [turns, activeWorkspace.id]);
    const importedNodes = activeWorkspace.nodes.filter((node) => node.imported);
    const structuredNodeCount = activeWorkspace.nodes.filter((node) => node.type !== 'concept').length;
    const orderedNodes = [...activeWorkspace.nodes].sort((left, right) => left.y - right.y || left.x - right.x);
    const groupedRegions = useMemo(() => {
        const adjacency = new Map();
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
        const visited = new Set();
        const regions = [];
        for (const node of orderedNodes) {
            if (visited.has(node.id))
                continue;
            const queue = [node.id];
            const group = [];
            visited.add(node.id);
            while (queue.length > 0) {
                const currentId = queue.shift();
                if (!currentId)
                    continue;
                const current = nodeMap.get(currentId);
                if (!current)
                    continue;
                group.push(current);
                adjacency.get(currentId)?.forEach((neighbor) => {
                    if (!visited.has(neighbor)) {
                        visited.add(neighbor);
                        queue.push(neighbor);
                    }
                });
            }
            if (group.length < 2)
                continue;
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
    return (_jsxs("div", { className: "planner-shell", children: [_jsx("div", { className: "planner-radar" }), _jsxs("header", { className: "topbar", children: [_jsxs("div", { className: "brand", children: [_jsx("span", { className: "brand-mark", children: "M" }), _jsxs("div", { children: [_jsx("p", { className: "eyebrow", children: "Memory workspace" }), _jsx("h1", { children: "Planner" })] })] }), _jsxs("div", { className: "workspace-strip", children: [workspaces.map((workspace) => (_jsxs("button", { type: "button", className: `workspace-pill ${workspace.id === activeWorkspace.id ? 'is-active' : ''}`, onClick: () => {
                                    setActiveWorkspaceId(workspace.id);
                                    setSelectedNodeId(workspace.nodes[0]?.id ?? '');
                                }, children: [_jsx("span", { children: workspace.label }), _jsxs("small", { children: [workspace.nodes.length, " nodes"] })] }, workspace.id))), _jsx("button", { type: "button", className: "workspace-pill is-ghost", onClick: createWorkspaceManually, children: "+ New space" })] })] }), _jsxs("main", { className: `workspace-layout ${inspectorHidden ? 'inspector-hidden' : ''}`, children: [_jsxs("section", { className: "panel chat-panel", children: [_jsxs("div", { className: "panel-heading", children: [_jsxs("div", { children: [_jsx("p", { className: "eyebrow", children: "Conversation" }), _jsx("h2", { children: "Talk through the idea, then shape the rough plan" }), streamingText ? _jsx("p", { className: "live-status", children: streamingText }) : null] }), _jsxs("div", { className: "signal-box", children: [_jsx("span", { className: `dot ${busy ? 'busy' : ''}` }), _jsx("span", { children: busy ? 'Planning turn' : 'Idle' })] })] }), _jsx("div", { className: "chat-feed", ref: chatFeedRef, children: turns.map((turn) => (_jsxs("article", { className: `turn turn-${turn.role}`, children: [_jsx("p", { className: "turn-role", children: turn.role }), _jsx("div", { className: "turn-text", children: renderMarkdown(turn.text) }), turn.tools?.length ? (_jsx("div", { className: "turn-tools", children: turn.tools.map((tool) => (_jsx("span", { children: tool }, tool))) })) : null, turn.streaming ? _jsx("div", { className: "streaming-bar" }) : null] }, turn.id))) }), _jsxs("div", { className: "selected-node-panel", children: [_jsx("p", { className: "selected-node-label", children: "Selected node" }), selectedNode ? (_jsxs(_Fragment, { children: [_jsxs("div", { className: "selected-node-header", children: [_jsx("span", { className: "selected-node-type", children: nodeTypePalette[selectedNode.type].label }), _jsx("strong", { children: selectedNode.title })] }), _jsx("p", { className: "selected-node-summary", children: selectedNode.detail }), _jsx("p", { className: "selected-node-source", children: sourceTurn ? sourceTurn.text : selectedNode.source })] })) : (_jsx("p", { className: "selected-node-summary", children: "Select a node to inspect it here." }))] }), _jsxs("form", { className: "composer", onSubmit: handleSubmit, children: [_jsx("textarea", { value: input, onChange: (event) => setInput(event.target.value), placeholder: "Describe the rough plan, note a dependency, or explain what should change...", rows: 5 }), _jsxs("div", { className: "composer-footer", children: [_jsxs("div", { className: "toggle-row", children: [_jsxs("label", { children: [_jsx("input", { type: "checkbox", checked: allowNodes, onChange: (event) => setAllowNodes(event.target.checked) }), "Allow node creation"] }), _jsxs("label", { children: [_jsx("input", { type: "checkbox", checked: allowLinks, onChange: (event) => setAllowLinks(event.target.checked) }), "Allow linking"] }), _jsxs("label", { children: [_jsx("input", { type: "checkbox", checked: autoSplit, onChange: (event) => setAutoSplit(event.target.checked) }), "Auto-split on drift"] })] }), _jsx("button", { type: "submit", className: "submit-btn", disabled: busy || !input.trim(), children: busy ? 'Thinking…' : 'Send to planner' })] })] })] }), _jsxs("section", { className: "panel canvas-panel", onPointerMove: handlePointerMove, onPointerUp: stopDragging, onPointerLeave: stopDragging, children: [_jsxs("div", { className: "panel-heading", children: [_jsxs("div", { children: [_jsx("p", { className: "eyebrow", children: "Plan canvas" }), _jsx("h2", { children: activeWorkspace.label })] }), _jsxs("div", { className: "metric-row", children: [_jsxs("span", { children: ["Drift ", Math.round(activeWorkspace.drift * 100), "%"] }), _jsxs("span", { children: [activeWorkspace.nodes.length, " nodes"] }), _jsxs("span", { children: [activeWorkspace.edges.length, " links"] }), _jsxs("span", { children: [structuredNodeCount, " structured"] })] })] }), _jsx("div", { className: "announcement", children: announcement }), _jsx("div", { className: "canvas-viewport", children: _jsxs("div", { className: "canvas-stage", children: [groupedRegions.map((region) => (_jsx("div", { className: "canvas-group", style: {
                                                transform: `translate(${region.x}px, ${region.y}px)`,
                                                width: region.width,
                                                height: region.height,
                                            }, children: _jsx("span", { className: "canvas-group-label", children: region.label }) }, region.id))), _jsx("svg", { className: "edge-layer", viewBox: "0 0 2400 1600", preserveAspectRatio: "none", children: activeWorkspace.edges.map((edge) => {
                                                const from = activeWorkspace.nodes.find((node) => node.id === edge.from);
                                                const to = activeWorkspace.nodes.find((node) => node.id === edge.to);
                                                if (!from || !to)
                                                    return null;
                                                return (_jsx("g", { children: _jsx("path", { d: edgePath(from, to), className: `edge edge-${edge.kind}` }) }, edge.id));
                                            }) }), orderedNodes.map((node) => {
                                            const palette = nodeTypePalette[node.type];
                                            const isSelected = node.id === selectedNode?.id;
                                            return (_jsxs("button", { type: "button", className: `node-card node-${node.type} ${isSelected ? 'is-selected' : ''} ${node.imported ? 'is-imported' : ''}`, style: {
                                                    transform: `translate(${node.x}px, ${node.y}px)`,
                                                    width: node.width,
                                                    borderColor: palette.accent,
                                                    ['--node-accent']: palette.accent,
                                                    ['--node-tone']: palette.tone,
                                                }, onClick: () => selectNode(node.id), onPointerDown: (event) => handleNodePointerDown(event, node), onContextMenu: (event) => handleNodeContextMenu(event, node), children: [_jsx("span", { className: "node-type", children: palette.label }), _jsx("strong", { children: node.title }), _jsx("div", { className: "node-footer", children: node.pinned ? _jsx("em", { children: "pinned" }) : node.imported ? _jsx("em", { children: "imported" }) : null })] }, node.id));
                                        })] }) })] }), _jsxs("aside", { className: `panel insight-panel ${inspectorHidden ? 'is-collapsed' : ''}`, children: [_jsxs("div", { className: "panel-heading", children: [_jsxs("div", { children: [_jsx("p", { className: "eyebrow", children: "Inspector" }), _jsx("h2", { children: inspectorHidden ? 'Hidden sidebar' : 'Why the agent placed each node' })] }), _jsx("button", { type: "button", className: "sidebar-toggle", onClick: () => setInspectorHidden((current) => !current), children: inspectorHidden ? 'Show sidebar' : 'Hide sidebar' })] }), !inspectorHidden ? (_jsxs(_Fragment, { children: [_jsxs("div", { className: "insight-card", children: [_jsx("p", { className: "insight-title", children: "Canvas access" }), _jsx("p", { className: "muted-copy", children: "The canvas stays loose by default. Related notes cluster together automatically when they share links or sit close together. Click a card to read the full description on the left, and use right-click for pin, rename, delete, or manual linking." })] }), _jsxs("div", { className: "insight-card", children: [_jsx("p", { className: "insight-title", children: "Tool belt" }), _jsx("div", { className: "chip-row", children: activeToolSet.map((tool) => (_jsx("span", { className: "tool-chip", title: toolInfo[tool], children: tool }, tool))) })] }), _jsxs("div", { className: "insight-card", children: [_jsx("p", { className: "insight-title", children: "Workspace anchors" }), importedNodes.length > 0 ? (_jsx("ul", { className: "anchor-list", children: importedNodes.map((node) => (_jsx("li", { children: node.title }, node.id))) })) : (_jsx("p", { className: "muted-copy", children: "No imported anchors yet. A drift event will carry them into a new workspace." }))] }), _jsxs("div", { className: "insight-card", children: [_jsx("p", { className: "insight-title", children: "Agent trail" }), _jsx("div", { className: "trail-list", children: agentHistory.map((turn) => (_jsxs("article", { className: "trail-item", children: [_jsx("span", { children: turn.tools?.join(' · ') ?? 'observe' }), _jsx("p", { children: turn.text })] }, turn.id))) })] })] })) : (_jsx("div", { className: "collapsed-sidebar-note", children: _jsx("button", { type: "button", className: "sidebar-toggle sidebar-toggle-inline", onClick: () => setInspectorHidden(false), children: "Reopen inspector" }) }))] })] }), nodeMenu ? _jsx("button", { type: "button", className: "menu-backdrop", "aria-label": "Close menu", onClick: () => setNodeMenu(null) }) : null, nodeMenu && menuNode ? (_jsxs("div", { className: "node-menu", style: { left: nodeMenu.x, top: nodeMenu.y }, onPointerDown: (event) => event.stopPropagation(), children: [_jsxs("div", { className: "node-menu-header", children: [_jsx("strong", { children: menuNode.title }), _jsx("span", { children: nodeTypePalette[menuNode.type].label })] }), _jsx("button", { type: "button", onClick: () => togglePin(activeWorkspace.id, menuNode.id), children: menuNode.pinned ? 'Unpin' : 'Pin' }), _jsx("button", { type: "button", onClick: () => renameNode(activeWorkspace.id, menuNode.id), children: "Rename" }), _jsx("button", { type: "button", onClick: () => deleteNode(activeWorkspace.id, menuNode.id), children: "Delete" }), selectedNode && selectedNode.id !== menuNode.id ? (_jsx("button", { type: "button", onClick: () => connectNodes(activeWorkspace.id, menuNode.id, selectedNode.id, 'related'), children: "Link to selected" })) : null, _jsx("button", { type: "button", onClick: () => setNodeMenu(null), children: "Close" })] })) : null] }));
}
