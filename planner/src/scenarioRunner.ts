import { planTurn, seedWorkspaces, type Workspace } from './plannerCore.js';

interface Scenario {
  name: string;
  prompt: string;
  allowNodes?: boolean;
  allowLinks?: boolean;
}

const scenarios: Scenario[] = [
  {
    name: 'Memory capture',
    prompt: 'Remember that I want to use the docs API for structured research and keep that idea visible.',
  },
  {
    name: 'Search enrichment',
    prompt: 'Search the API docs and source references, then attach that evidence near the remembered node.',
  },
  {
    name: 'Unlinked note',
    prompt: 'This is just a small note for later and it should not connect to the rest right now.',
    allowLinks: false,
  },
  {
    name: 'Workspace drift',
    prompt: 'Actually, forget that and let us talk about interview prep questions for backend design.',
  },
];

function applyPlan(workspace: Workspace, scenario: Scenario): Workspace {
  const plan = planTurn({
    input: scenario.prompt,
    workspace,
    allowNodes: scenario.allowNodes ?? true,
    allowLinks: scenario.allowLinks ?? true,
  });

  const nodes = [...plan.nodes, ...plan.searchNodes];
  if (plan.action === 'split') {
    return {
      id: `${workspace.id}-split`,
      label: plan.workspaceLabel,
      topic: plan.workspaceLabel.toLowerCase(),
      drift: plan.drift,
      nodes,
      edges: [...plan.edges],
      importedFrom: workspace.id,
    };
  }

  return {
    ...workspace,
    label: plan.workspaceLabel,
    topic: plan.workspaceLabel.toLowerCase(),
    drift: plan.drift,
    nodes: [...workspace.nodes, ...nodes],
    edges: [...workspace.edges, ...plan.edges],
  };
}

function printScenario(index: number, workspace: Workspace, scenario: Scenario) {
  const plan = planTurn({
    input: scenario.prompt,
    workspace,
    allowNodes: scenario.allowNodes ?? true,
    allowLinks: scenario.allowLinks ?? true,
  });

  const createdNodes = [...plan.nodes, ...plan.searchNodes].map((node) => ({
    title: node.title,
    type: node.type,
    position: { x: node.x, y: node.y },
    linkedFrom: node.linkedFrom ?? null,
    imported: node.imported ?? false,
  }));

  console.log(JSON.stringify({
    step: index + 1,
    name: scenario.name,
    prompt: scenario.prompt,
    action: plan.action,
    drift: Number(plan.drift.toFixed(2)),
    driftReason: plan.driftReason,
    tools: plan.tools,
    createdNodes,
    edgeCount: plan.edges.length,
    summary: plan.summary,
  }, null, 2));

  return applyPlan(workspace, scenario);
}

let workspace = seedWorkspaces()[0];
console.log(JSON.stringify({
  startWorkspace: workspace.label,
  startNodes: workspace.nodes.map((node) => node.title),
}, null, 2));

scenarios.forEach((scenario, index) => {
  workspace = printScenario(index, workspace, scenario);
});

console.log(JSON.stringify({
  finalWorkspace: workspace.label,
  totalNodes: workspace.nodes.length,
  totalEdges: workspace.edges.length,
  nodeTitles: workspace.nodes.map((node) => node.title),
}, null, 2));
