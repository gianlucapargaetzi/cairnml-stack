import React, { useEffect, useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';

import { Card, Dropdown, Table, Text, InputWrapper } from 'components/kit';
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
  const [openMenu, setOpenMenu] = useState<'project' | 'type' | null>(null);
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
      <header className='Datasets__header'>
        <Text component='h1' size={18} weight={600} tint={100}>
          Datasets
        </Text>
        <Text size={12} tint={50}>
          Datasets are tracked with DVC in Git. A card is a Markdown file next
          to the .dvc file.
        </Text>
      </header>
      <Card
        title='All datasets'
        subtitle={`${shown.length} of ${rows.length} shown.`}
      >
        <div className='Datasets__toolbar'>
          <Dropdown
            label='Project'
            size='medium'
            placeholder='All projects'
            value={project || null}
            options={[
              { value: '', label: 'All projects' },
              ...projects.map((name) => ({ value: name, label: name })),
            ]}
            onChange={(option) => setProject(option?.value ?? '')}
            onMenuOpen={() => setOpenMenu('project')}
            onMenuClose={() => setOpenMenu(null)}
            open={openMenu === 'project'}
            withPortal
          />
          <Dropdown
            label='Type'
            size='medium'
            placeholder='Any type'
            value={type || null}
            options={[
              { value: '', label: 'Any type' },
              ...types.map((name) => ({ value: name, label: name })),
            ]}
            onChange={(option) => setType(option?.value ?? '')}
            onMenuOpen={() => setOpenMenu('type')}
            onMenuClose={() => setOpenMenu(null)}
            open={openMenu === 'type'}
            withPortal
          />
          <InputWrapper
            labelAppearance='top-labeled'
            label='Search'
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <Table
          columns={[
            { key: 'dataset', label: 'Dataset' },
            { key: 'project', label: 'Project' },
            { key: 'repo', label: 'Repository' },
            { key: 'type', label: 'Type' },
            { key: 'license', label: 'License' },
            { key: 'size', label: 'Size' },
            { key: 'files', label: 'Files' },
            { key: 'card', label: 'Card' },
          ]}
          rows={shown.map((row) => ({
            id: `${row.project}/${row.repo}/${row.path}`,
            dataset: (
              <Link className='Datasets__link' to={datasetLink(row)}>
                {row.title ? `${row.path} (${row.title})` : row.path}
              </Link>
            ),
            project: row.project,
            repo: row.repo,
            type: row.type ?? '–',
            license: row.license ?? '–',
            size: formatBytes(row.size_bytes),
            files: row.nfiles ?? '–',
            card: row.has_card ? 'Yes' : 'Missing',
          }))}
          rowKey='id'
          emptyText='No datasets found. Link a data repository with mlops repo link --role data, and add .dvc files.'
        />
      </Card>
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
          <Text size={12} color='error' role='alert'>
            {error}
          </Text>
        )}
        {selection ? (
          <DatasetDetail {...selection} />
        ) : rows ? (
          <DatasetList
            rows={rows}
            initialProject={params.get('project') ?? ''}
          />
        ) : (
          !error && (
            <Text size={12} tint={50}>
              Loading
            </Text>
          )
        )}
      </section>
    </ErrorBoundary>
  );
}

export default Datasets;
