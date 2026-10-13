// Helpers for the projects pages: the tree of project slugs, number text, and the best result of an
// experiment.

export interface IProjectRef {
  id: string;
  slug: string;
  name: string;
}

export interface IProjectTreeNode {
  name: string;
  project: IProjectRef | null;
  children: IProjectTreeNode[];
}

// Projects nest by the parts of their slug ("vision/seg" sits under "vision"). Groups with
// children come first, then alphabetical.
export function buildProjectTree(projects: IProjectRef[]): IProjectTreeNode[] {
  type Mutable = {
    name: string;
    project: IProjectRef | null;
    children: Map<string, Mutable>;
  };
  const root: Mutable = { name: '', project: null, children: new Map() };
  for (const project of projects) {
    let node = root;
    const parts = project.slug.split('/');
    parts.forEach((part, index) => {
      if (!node.children.has(part)) {
        node.children.set(part, {
          name: part,
          project: null,
          children: new Map(),
        });
      }
      node = node.children.get(part) as Mutable;
      if (index === parts.length - 1) {
        node.project = project;
      }
    });
  }
  const convert = (node: Mutable): IProjectTreeNode[] =>
    [...node.children.values()]
      .map((child) => ({
        name: child.name,
        project: child.project,
        children: convert(child),
      }))
      .sort(
        (a, b) =>
          Number(b.children.length > 0) - Number(a.children.length > 0) ||
          a.name.localeCompare(b.name),
      );
  return convert(root);
}

export function fmtNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '–';
  }
  if (Math.abs(value) >= 1000 || (Math.abs(value) < 0.001 && value !== 0)) {
    return value.toExponential(3);
  }
  return String(Math.round(value * 10000) / 10000);
}

export interface IExperimentBest {
  best: { run_id: string; value: number } | null;
  primary_metric: string | null;
}

export function bestLabel(experiment: IExperimentBest): {
  text: string;
  runId: string | null;
} {
  if (!experiment.best) {
    return { text: '–', runId: null };
  }
  return {
    text: `${fmtNumber(experiment.best.value)} (${experiment.primary_metric})`,
    runId: experiment.best.run_id,
  };
}
