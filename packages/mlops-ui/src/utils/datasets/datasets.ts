// Helpers for the datasets pages: sizes, filters and links to the detail view.

export interface IDatasetRow {
  project: string;
  repo: string;
  ref: string;
  path: string;
  title: string | null;
  type: string | null;
  license: string | null;
  size_bytes: number | null;
  nfiles: number | null;
  has_card: boolean;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) {
    return '–';
  }
  if (bytes >= 1e9) {
    return `${(bytes / 1e9).toFixed(1)} GB`;
  }
  if (bytes >= 1e6) {
    return `${(bytes / 1e6).toFixed(1)} MB`;
  }
  if (bytes >= 1e3) {
    return `${(bytes / 1e3).toFixed(1)} kB`;
  }
  return `${bytes} B`;
}

export function filterDatasets(
  rows: IDatasetRow[],
  filter: { project: string; type: string; query: string },
): IDatasetRow[] {
  const query = filter.query.toLowerCase();
  return rows.filter(
    (row) =>
      (!filter.project || row.project === filter.project) &&
      (!filter.type || row.type === filter.type) &&
      (!query ||
        row.path.toLowerCase().includes(query) ||
        (row.title ?? '').toLowerCase().includes(query)),
  );
}

export function datasetLink(
  row: Pick<IDatasetRow, 'project' | 'repo' | 'path'>,
): string {
  const params = new URLSearchParams({
    project: row.project,
    repo: row.repo,
    path: row.path,
  });
  return `/datasets?${params.toString()}`;
}
