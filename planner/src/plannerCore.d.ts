export type NodeType = 'concept' | 'decision' | 'question' | 'step' | 'search-result';
export type ToolId = 'extract' | 'link' | 'search' | 'cluster' | 'promote';
export type WorkspaceAction = 'stay' | 'split';
export type EdgeKind = 'related' | 'anchor' | 'imported' | 'feeds' | 'calls' | 'checks' | 'groups' | 'transforms' | 'supports';
export interface PlannerNode {
    id: string;
    title: string;
    detail: string;
    type: NodeType;
    x: number;
    y: number;
    width: number;
    source: string;
    sourceTurnId: string;
    tools: ToolId[];
    linkedFrom?: string | null;
    imported?: boolean;
    pinned?: boolean;
}
export interface PlannerEdge {
    id: string;
    from: string;
    to: string;
    kind: EdgeKind;
}
export interface Workspace {
    id: string;
    label: string;
    topic: string;
    drift: number;
    nodes: PlannerNode[];
    edges: PlannerEdge[];
    importedFrom?: string;
}
export interface PlanResult {
    action: WorkspaceAction;
    workspaceLabel: string;
    drift: number;
    tools: ToolId[];
    nodes: PlannerNode[];
    searchNodes: PlannerNode[];
    edges: PlannerEdge[];
    summary: string;
    importedNodeIds: string[];
    driftReason: string;
}
export declare const seedWorkspaces: () => Workspace[];
export declare const nodeTypePalette: Record<NodeType, {
    label: string;
    accent: string;
    tone: string;
}>;
export declare const toolInfo: Record<ToolId, string>;
export declare function uid(prefix: string): string;
export declare function normalize(text: string): string[];
export declare function extractSegments(input: string): string[];
export declare function detectNodeType(text: string): NodeType;
export declare function chooseTools(text: string, type: NodeType): ToolId[];
export declare function topicLabel(input: string): string;
export declare function workspaceCentroid(workspace: Workspace): string;
export declare function scoreDrift(activeTopic: string, input: string): number;
export declare function classifyEditIntent(input: string): 'add' | 'delete' | 'replace' | 'neutral';
export declare function searchKnowledge(input: string): Array<Pick<PlannerNode, 'title' | 'detail' | 'type' | 'source'>>;
export declare function createNodePlacement(index: number, sourceNode?: PlannerNode | null, isolated?: boolean, footprint?: {
    width: number;
    height: number;
}): {
    x: number;
    y: number;
};
export declare function createEdge(from: string, to: string, kind?: PlannerEdge['kind']): PlannerEdge;
export declare function planTurn(params: {
    input: string;
    workspace: Workspace;
    allowNodes: boolean;
    allowLinks: boolean;
}): PlanResult;
export declare function edgePath(from: PlannerNode, to: PlannerNode): string;
export declare function edgeLabelPosition(from: PlannerNode, to: PlannerNode): {
    x: number;
    y: number;
};
