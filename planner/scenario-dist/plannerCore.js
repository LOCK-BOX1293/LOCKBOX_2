export const seedWorkspaces = () => [
    {
        id: 'workspace-0',
        label: 'Idea space',
        topic: 'capture and organize thoughts',
        drift: 0,
        nodes: [
            {
                id: 'root-0',
                title: 'Start with an idea',
                detail: 'The agent captures useful points and arranges them into a live map.',
                type: 'concept',
                x: 120,
                y: 160,
                width: 240,
                source: 'seed',
                sourceTurnId: 'seed',
                tools: ['extract', 'cluster'],
            },
        ],
        edges: [],
    },
];
export const nodeTypePalette = {
    concept: { label: 'Source / Model', accent: '#f7b267', tone: '#24160d' },
    decision: { label: 'Constraint', accent: '#7dd3fc', tone: '#0a1620' },
    question: { label: 'Open item', accent: '#f9a8d4', tone: '#21101a' },
    step: { label: 'Process', accent: '#86efac', tone: '#102014' },
    'search-result': { label: 'Evidence', accent: '#fde68a', tone: '#241b06' },
};
export const toolInfo = {
    extract: 'Pull durable points from the conversation',
    link: 'Connect a new point to something already known',
    search: 'Look outward for supporting context',
    cluster: 'Group similar ideas into one workspace',
    promote: 'Turn a noisy note into a remembered node',
};
const STOP_WORDS = new Set([
    'the', 'and', 'for', 'that', 'with', 'this', 'from', 'then', 'will', 'have',
    'there', 'their', 'about', 'into', 'they', 'them', 'what', 'when', 'where',
    'your', 'you', 'are', 'was', 'were', 'can', 'could', 'should', 'would',
    'like', 'need', 'just', 'also', 'only', 'more', 'less', 'some', 'any',
    'been', 'being', 'how', 'why', 'who', 'use', 'used', 'using', 'make',
    'create', 'created', 'idea', 'ideas', 'thing', 'things', 'point', 'points',
]);
const SEARCH_INDEX = [
    {
        title: 'Workspace drift is a boundary, not a failure',
        detail: 'When the topic changes, the old context should be preserved and the new space should start cleanly.',
        source: 'local://planner/search/drift',
        keywords: ['drift', 'workspace', 'switch', 'topic', 'move'],
    },
    {
        title: 'Nodes should capture durable meaning',
        detail: 'A node should survive if it can still explain the idea later, even if the original wording changes.',
        source: 'local://planner/search/node-memory',
        keywords: ['remember', 'node', 'memory', 'capture', 'durable'],
    },
    {
        title: 'Search enriches a node rather than replacing it',
        detail: 'External evidence should attach to a thought trail, not overwrite the user’s own reasoning.',
        source: 'local://planner/search/evidence',
        keywords: ['search', 'evidence', 'source', 'reference', 'api'],
    },
    {
        title: 'Right-click actions keep the graph editable',
        detail: 'Rename, pin, delete, and connect are faster when they live directly on the node.',
        source: 'local://planner/search/editing',
        keywords: ['rename', 'delete', 'pin', 'connect', 'edit'],
    },
];
export function uid(prefix) {
    const raw = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    return `${prefix}-${raw}`;
}
export function normalize(text) {
    return text
        .toLowerCase()
        .replace(/[^a-z0-9\s-]/g, ' ')
        .split(/\s+/)
        .map((token) => token.trim())
        .filter(Boolean)
        .filter((token) => token.length > 2)
        .filter((token) => !STOP_WORDS.has(token));
}
export function extractSegments(input) {
    const rough = input
        .replace(/\n+/g, ' ')
        .split(/(?:\bthen\b|\band\b|\bbut\b|\bso\b|[.;!?])/i)
        .map((chunk) => chunk.trim())
        .filter(Boolean);
    return rough.length > 0 ? rough.slice(0, 4) : [input.trim()];
}
export function detectNodeType(text) {
    const lower = text.toLowerCase();
    if (/[?]/.test(text) || /\b(why|how|what|when|where|who)\b/.test(lower))
        return 'question';
    if (/\b(decide|choose|prefer|settle|confirm|adopt)\b/.test(lower))
        return 'decision';
    if (/\b(do|build|ship|add|create|move|wire|write|review|make|implement)\b/.test(lower))
        return 'step';
    if (/\b(search|source|evidence|paper|article|api|docs|reference|research)\b/.test(lower))
        return 'search-result';
    return 'concept';
}
export function chooseTools(text, type) {
    const lower = text.toLowerCase();
    const tools = new Set(['extract', 'promote']);
    if (/\b(search|api|docs|reference|research|evidence|article|source)\b/.test(lower))
        tools.add('search');
    if (/\b(related|link|connect|same|similar|because|therefore|instead)\b/.test(lower))
        tools.add('link');
    if (/\b(cluster|group|workspace|topic|theme)\b/.test(lower))
        tools.add('cluster');
    if (type === 'decision')
        tools.add('link');
    return Array.from(tools);
}
export function topicLabel(input) {
    const tokens = normalize(input);
    if (tokens.length === 0)
        return 'Untitled idea';
    return tokens.slice(0, 3).map((word) => word[0].toUpperCase() + word.slice(1)).join(' ');
}
export function workspaceCentroid(workspace) {
    const seed = workspace.nodes
        .filter((node) => node.type !== 'search-result')
        .slice(-6)
        .map((node) => node.title)
        .join(' ');
    return seed || workspace.topic;
}
export function scoreDrift(activeTopic, input) {
    const active = new Set(normalize(activeTopic));
    const current = normalize(input);
    if (current.length === 0)
        return 0;
    const overlap = current.filter((token) => active.has(token)).length;
    const base = 1 - overlap / Math.max(1, Math.min(active.size, current.length));
    const nudges = [
        /\b(actually|instead|separate|new topic|forget|switch|different)\b/i.test(input) ? 0.25 : 0,
        /\b(focus on|move to|talk about|another)\b/i.test(input) ? 0.12 : 0,
    ];
    return Math.min(1, Math.max(0, base + nudges.reduce((sum, nudge) => sum + nudge, 0)));
}
export function classifyEditIntent(input) {
    const lower = input.toLowerCase();
    if (/\b(replace|rewrite|rework|revise|rearrange|restructure|edit|modify|refine|update|change)\b/.test(lower)) {
        return 'replace';
    }
    if (/\b(add|append|include|insert|more|also|plus|another|extra)\b/.test(lower)) {
        return 'add';
    }
    if (/\b(delete|remove|drop|erase|discard|skip|without|trim|cut)\b/.test(lower)) {
        return 'delete';
    }
    return 'neutral';
}
export function searchKnowledge(input) {
    const tokens = new Set(normalize(input));
    return SEARCH_INDEX
        .map((entry) => {
        const hitCount = entry.keywords.filter((keyword) => tokens.has(keyword)).length;
        return { entry, hitCount };
    })
        .filter(({ hitCount }) => hitCount > 0)
        .sort((left, right) => right.hitCount - left.hitCount)
        .slice(0, 2)
        .map(({ entry }) => ({
        title: entry.title,
        detail: entry.detail,
        type: 'search-result',
        source: entry.source,
    }));
}
export function createNodePlacement(index, sourceNode, isolated = false, footprint = { width: 250, height: 92 }) {
    if (sourceNode && !isolated) {
        const offset = index % 3;
        const gapX = Math.max(84, Math.round(footprint.width * 0.42));
        const gapY = Math.max(86, Math.round(footprint.height * 0.92));
        return {
            x: sourceNode.x + sourceNode.width + gapX + offset * 26,
            y: sourceNode.y + (offset - 1) * (footprint.height + gapY),
        };
    }
    const row = Math.floor(index / 2);
    const column = index % 2;
    const gapX = Math.max(60, Math.round(footprint.width * 0.26));
    const gapY = Math.max(64, Math.round(footprint.height * 0.42));
    return {
        x: 120 + column * (footprint.width + gapX) + row * 54,
        y: 104 + row * (footprint.height + gapY) + (column % 2) * 24,
    };
}
export function createEdge(from, to, kind = 'related') {
    return {
        id: uid('edge'),
        from,
        to,
        kind,
    };
}
export function planTurn(params) {
    const { input, workspace, allowNodes, allowLinks } = params;
    const centroid = workspaceCentroid(workspace);
    const drift = scoreDrift(centroid, input);
    const driftPhrase = /\b(actually|instead|forget|switch|new workspace|new topic|different)\b/i.test(input);
    const action = drift > 0.58 || driftPhrase ? 'split' : 'stay';
    const label = topicLabel(input);
    const type = detectNodeType(input);
    const tools = chooseTools(input, type);
    const segments = extractSegments(input);
    const nodes = [];
    const searchNodes = [];
    const edges = [];
    const importedNodeIds = [];
    const anchor = workspace.nodes.at(-1) ?? workspace.nodes[0] ?? null;
    const searchHits = tools.includes('search') ? searchKnowledge(input) : [];
    if (!allowNodes) {
        return {
            action,
            workspaceLabel: action === 'split' ? label : workspace.label,
            drift,
            tools,
            nodes,
            searchNodes,
            edges,
            importedNodeIds,
            driftReason: driftPhrase
                ? 'The prompt contains a drift phrase.'
                : 'Topic overlap against the current workspace fell below the internal threshold.',
            summary: action === 'split'
                ? 'Topic drift is high, so the agent opens a fresh workspace and preserves the current anchor nodes.'
                : 'The agent held this turn in memory without materializing a new node.',
        };
    }
    const relevantSegments = segments.slice(0, action === 'split' ? 2 : 3);
    relevantSegments.forEach((segment, index) => {
        const nodeType = index === 0 ? type : detectNodeType(segment);
        const isolated = !allowLinks || (action === 'split' && index > 0);
        const placement = createNodePlacement(index, isolated ? null : anchor, isolated);
        const node = {
            id: uid('node'),
            title: segment.length > 64 ? `${segment.slice(0, 61).trim()}...` : segment,
            detail: index === 0
                ? 'Captured as a durable thought.'
                : 'A related fragment extracted from the same turn.',
            type: nodeType,
            x: placement.x,
            y: placement.y,
            width: Math.min(280, Math.max(210, segment.length * 6.4)),
            source: input,
            sourceTurnId: '',
            tools,
            linkedFrom: allowLinks && anchor ? anchor.id : null,
            imported: false,
            pinned: false,
        };
        nodes.push(node);
        if (allowLinks && anchor) {
            edges.push(createEdge(anchor.id, node.id, action === 'split' && index === 0 ? 'anchor' : 'related'));
        }
    });
    searchHits.forEach((hit, index) => {
        const placement = createNodePlacement(index + relevantSegments.length, anchor, false);
        const node = {
            id: uid('search'),
            title: hit.title,
            detail: hit.detail,
            type: 'search-result',
            x: placement.x + 62,
            y: placement.y + 42,
            width: 280,
            source: hit.source,
            sourceTurnId: '',
            tools,
            linkedFrom: anchor?.id ?? null,
            imported: false,
            pinned: true,
        };
        searchNodes.push(node);
        if (allowLinks && anchor) {
            edges.push(createEdge(anchor.id, node.id, 'related'));
        }
    });
    if (action === 'split') {
        const preserved = workspace.nodes.slice(-2);
        preserved.forEach((node, index) => {
            const copy = {
                ...node,
                id: uid('imported'),
                x: 96 + index * 214,
                y: 90 + index * 18,
                imported: true,
            };
            nodes.unshift(copy);
            importedNodeIds.push(copy.id);
            if (allowLinks && nodes[importedNodeIds.length] && nodes[importedNodeIds.length + 1]) {
                edges.push(createEdge(copy.id, nodes[nodes.length - 1].id, 'imported'));
            }
        });
    }
    return {
        action,
        workspaceLabel: action === 'split' ? label : workspace.label,
        drift,
        tools,
        nodes,
        searchNodes,
        edges,
        importedNodeIds,
        driftReason: driftPhrase
            ? 'The prompt contains a drift phrase.'
            : 'Topic overlap against the current workspace fell below the internal threshold.',
        summary: action === 'split'
            ? `The agent detected drift and opened a fresh workspace around "${label}".`
            : 'The agent kept the turn inside the current workspace and attached the key point to the existing trail.',
    };
}
export function edgePath(from, to) {
    const x1 = from.x + from.width;
    const y1 = from.y + 42;
    const x2 = to.x;
    const y2 = to.y + 42;
    const midX = x1 + Math.max(72, Math.abs(x2 - x1) * 0.28) * (x2 >= x1 ? 1 : -1);
    return `M ${x1} ${y1} L ${midX} ${y1} L ${midX} ${y2} L ${x2} ${y2}`;
}
export function edgeLabelPosition(from, to) {
    const x1 = from.x + from.width;
    const x2 = to.x;
    return {
        x: (x1 + x2) / 2,
        y: Math.min(from.y, to.y) + Math.abs(from.y - to.y) / 2 - 10,
    };
}
