import React, { useEffect, useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';

import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';

import datasetsService from 'services/api/datasets/datasetsService';

import {
  IDatasetRow,
  datasetLink,
  filterDatasets,
  formatBytes,
} from 'utils/datasets/datasets';

import DatasetDetail from './DatasetDetail';

import './Datasets.scss';

function DatasetList({
  rows,
  initialProject,
}: {
  rows: IDatasetRow[];
  initialProject: string;
}) {
  const [project, setProject] = useState(initialProject);
  const [type, setType] = useState('');
  const [query, setQuery] = useState('');
  const projects = useMemo(
    () => [...new Set(rows.map((row) => row.project))].sort(),
    [rows],
  );
  const types = useMemo(
    () =>
      [
        ...new Set(rows.map((row) => row.type).filter(Boolean) as string[]),
      ].sort(),
    [rows],
  );
  const shown = filterDatasets(rows, { project, type, query });

  return (
    <>
      <h1>Datasets</h1>
      <p className='Datasets__muted'>
        Datasets are tracked with DVC in Git. A card is a Markdown file next to
        the .dvc file.
      </p>
      <div className='Datasets__toolbar'>
        <label>
          Project
          <select
            value={project}
            onChange={(event) => setProject(event.target.value)}
          >
            <option value=''>all</option>
            {projects.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Type
          <select
            value={type}
            onChange={(event) => setType(event.target.value)}
          >
            <option value=''>any</option>
            {types.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Search
          <input
            type='search'
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
      </div>
      <table className='Datasets__table'>
        <thead>
          <tr>
            <th>Dataset</th>
            <th>Project</th>
            <th>Repository</th>
            <th>Type</th>
            <th>License</th>
            <th>Size</th>
            <th>Files</th>
            <th>Card</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((row) => (
            <tr key={`${row.project}/${row.repo}/${row.path}`}>
              <td>
                <Link to={datasetLink(row)}>
                  {row.title ? `${row.path} (${row.title})` : row.path}
                </Link>
              </td>
              <td>{row.project}</td>
              <td>{row.repo}</td>
              <td>{row.type ?? '–'}</td>
              <td>{row.license ?? '–'}</td>
              <td>{formatBytes(row.size_bytes)}</td>
              <td>{row.nfiles ?? '–'}</td>
              <td>{row.has_card ? 'yes' : 'missing'}</td>
            </tr>
          ))}
          {shown.length === 0 && (
            <tr>
              <td colSpan={8} className='Datasets__muted'>
                No datasets found. Link a data repository with{' '}
                <code>mlops repo link --role data</code> and add .dvc files.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  );
}

// The list, or the detail of one dataset when the query names it (project, repo and path).
function Datasets(): React.FunctionComponentElement<React.ReactNode> {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const selection = params.get('path')
    ? {
        project: params.get('project') ?? '',
        repo: params.get('repo') ?? '',
        path: params.get('path') ?? '',
      }
    : null;
  const [rows, setRows] = useState<IDatasetRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (selection) {
      return undefined;
    }
    const request = datasetsService.getDatasets();
    request
      .call()
      .then((data) => setRows(data))
      .catch((requestError) => {
        if (requestError?.name !== 'AbortError') {
          setError(`Datasets could not be loaded: ${requestError.message}`);
        }
      });
    return () => request.abort();
    // The selection is read from the query; the list loads once per visit to this page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selection?.path]);

  return (
    <ErrorBoundary>
      <section className='Datasets'>
        {error && (
          <p className='Datasets__error' role='alert'>
            {error}
          </p>
        )}
        {selection ? (
          <DatasetDetail {...selection} />
        ) : rows ? (
          <DatasetList
            rows={rows}
            initialProject={params.get('project') ?? ''}
          />
        ) : (
          !error && <p className='Datasets__muted'>Loading…</p>
        )}
      </section>
    </ErrorBoundary>
  );
}

export default Datasets;
