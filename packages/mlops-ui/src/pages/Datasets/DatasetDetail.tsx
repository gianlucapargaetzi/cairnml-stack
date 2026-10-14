import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';

import { Badge, Card, DefinitionList, Table, Text } from 'components/kit';

import { STATUS_COLORS } from 'config/colors/colors';

import datasetsService, {
  IDatasetDetail,
} from 'services/api/datasets/datasetsService';

import { formatBytes } from 'utils/datasets/datasets';

import './DatasetDetail.scss';

interface IProps {
  project: string;
  repo: string;
  path: string;
}

function DatasetDetail({ project, repo, path }: IProps) {
  const [detail, setDetail] = useState<IDatasetDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDetail(null);
    setError(null);
    const request = datasetsService.getDatasetDetail(project, repo, path);
    request
      .call()
      .then((data) => setDetail(data))
      .catch((requestError) => {
        if (requestError?.name !== 'AbortError') {
          setError(`The dataset could not be loaded: ${requestError.message}`);
        }
      });
    return () => request.abort();
  }, [project, repo, path]);

  if (error) {
    return (
      <>
        <Link className='Datasets__link' to='/datasets'>
          ← All datasets
        </Link>
        <Text size={12} color='error' role='alert'>
          {error}
        </Text>
      </>
    );
  }
  if (!detail) {
    return (
      <Text size={12} tint={50}>
        Loading
      </Text>
    );
  }

  const card = detail.card;
  return (
    <section className='DatasetDetail'>
      <Link className='Datasets__link' to='/datasets'>
        ← All datasets
      </Link>

      <header className='DatasetDetail__header'>
        <div className='DatasetDetail__title'>
          <Text component='h1' size={18} weight={600} tint={100}>
            {card?.title || path}
          </Text>
          {card && card.type && (
            <Badge
              label={card.type}
              size='small'
              color={STATUS_COLORS.primary}
            />
          )}
        </div>
        <Text size={12} tint={50}>
          {[
            repo,
            path,
            card ? `license ${card.license || '–'}` : null,
            card?.version ? `version ${card.version}` : null,
            card?.owners.length ? `owners ${card.owners.join(', ')}` : null,
          ]
            .filter(Boolean)
            .join(' · ')}
        </Text>
      </header>

      {card ? (
        <Card
          title='About'
          subtitle={card.source ? `Source: ${card.source}` : undefined}
        >
          {card.tags.length > 0 && (
            <div className='DatasetDetail__tags'>
              {card.tags.map((tag) => (
                <Badge
                  key={tag}
                  label={tag}
                  size='small'
                  color={STATUS_COLORS.neutral}
                />
              ))}
            </div>
          )}
          {card.error && (
            <Text size={12} color='error'>
              Card problem: {card.error}
            </Text>
          )}
          {card.warnings.map((warning) => (
            <Text key={warning} size={12} tint={50}>
              Note: {warning}
            </Text>
          ))}
          {card.body && (
            <div className='DatasetDetail__body'>
              <ReactMarkdown>{card.body}</ReactMarkdown>
            </div>
          )}
        </Card>
      ) : (
        <Card
          title='No card yet'
          subtitle='Cards live in Git next to the .dvc file.'
        >
          <Text size={12}>Create one with:</Text>
          <Text size={12} component='span' className='DatasetDetail__code'>
            {`mlops dataset card init ${path}`}
          </Text>
          <Text size={12} tint={50}>
            Then edit it, commit and push.
          </Text>
        </Card>
      )}

      {card && card.columns.length > 0 && (
        <Card title='Schema'>
          <Table
            columns={[
              { key: 'name', label: 'Column' },
              { key: 'type', label: 'Type' },
              { key: 'description', label: 'Description' },
            ]}
            rows={card.columns.map((column) => ({
              id: column.name,
              name: <span className='DatasetDetail__mono'>{column.name}</span>,
              type: column.type ?? '–',
              description: column.description ?? '',
            }))}
            rowKey='id'
          />
        </Card>
      )}

      {card && Object.keys(card.splits).length > 0 && (
        <Card title='Splits'>
          <Table
            columns={[
              { key: 'split', label: 'Split' },
              { key: 'rows', label: 'Rows' },
            ]}
            rows={Object.entries(card.splits).map(([split, rows]) => ({
              id: split,
              split,
              rows,
            }))}
            rowKey='id'
          />
        </Card>
      )}

      <Card title='Contents'>
        <DefinitionList
          items={[
            {
              label: 'DVC hash',
              value: detail.dvc.dvc_hash ?? '–',
              mono: true,
            },
            {
              label: 'Size',
              value: formatBytes(detail.dvc.size_bytes ?? card?.size_bytes),
            },
            { label: 'Files', value: detail.dvc.nfiles ?? '–' },
            {
              label: 'Rows',
              value: card && card.rows !== null ? card.rows : '–',
            },
          ]}
        />
      </Card>

      <Card title='Versions' subtitle='Commits that changed the dataset.'>
        <Table
          columns={[
            { key: 'commit', label: 'Commit' },
            { key: 'date', label: 'Date' },
            { key: 'change', label: 'Change' },
            { key: 'hash', label: 'DVC hash' },
          ]}
          rows={detail.versions.map((version, index) => ({
            id: `${version.commit}-${index}`,
            commit: (
              <span className='DatasetDetail__mono'>
                {(version.commit ?? '').slice(0, 8) || '–'}
              </span>
            ),
            date: version.date ? new Date(version.date).toLocaleString() : '–',
            change: version.message,
            hash: (
              <span className='DatasetDetail__mono'>
                {version.dvc_hash && version.dvc_hash === detail.dvc.dvc_hash
                  ? `${version.dvc_hash} (current)`
                  : version.dvc_hash || '–'}
              </span>
            ),
          }))}
          rowKey='id'
          emptyText='No history found.'
        />
      </Card>

      <Card title={`Used by ${detail.used_by.count} run(s)`}>
        <Table
          columns={[
            { key: 'run', label: 'Run' },
            { key: 'experiment', label: 'Experiment' },
            { key: 'status', label: 'Status' },
            { key: 'created', label: 'Created' },
          ]}
          rows={detail.used_by.runs.map((run) => ({
            id: run.id,
            run: (
              <Link
                className='DatasetDetail__link'
                to={`/runs/${encodeURIComponent(run.id)}`}
              >
                {run.name}
              </Link>
            ),
            experiment: run.experiment,
            status: run.status,
            created: new Date(run.created_at).toLocaleString(),
          }))}
          rowKey='id'
          emptyText='No runs used this dataset yet.'
        />
      </Card>
    </section>
  );
}

export default DatasetDetail;
