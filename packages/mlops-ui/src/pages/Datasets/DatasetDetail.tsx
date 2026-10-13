import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';

import datasetsService, {
  IDatasetDetail,
} from 'services/api/datasets/datasetsService';

import { formatBytes } from 'utils/datasets/datasets';

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
        <p>
          <Link to='/datasets'>← all datasets</Link>
        </p>
        <p className='Datasets__error' role='alert'>
          {error}
        </p>
      </>
    );
  }
  if (!detail) {
    return <p className='Datasets__muted'>Loading…</p>;
  }

  const card = detail.card;
  return (
    <>
      <p>
        <Link to='/datasets'>← all datasets</Link>
      </p>
      {card ? (
        <>
          <h1>
            {card.title || path}{' '}
            <span className='Datasets__type'>{card.type}</span>
          </h1>
          <p className='Datasets__muted'>
            {[
              repo,
              path,
              `license ${card.license || '–'}`,
              card.version ? `version ${card.version}` : null,
              card.owners.length ? `owners ${card.owners.join(', ')}` : null,
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
          {card.tags.length > 0 && (
            <p>
              {card.tags.map((tag) => (
                <span key={tag} className='Datasets__type'>
                  {tag}{' '}
                </span>
              ))}
            </p>
          )}
          {card.source && <p>Source: {card.source}</p>}
          {card.error && (
            <p className='Datasets__error'>Card problem: {card.error}</p>
          )}
          {card.warnings.map((warning) => (
            <p key={warning} className='Datasets__muted'>
              Note: {warning}
            </p>
          ))}
        </>
      ) : (
        <>
          <h1>{path}</h1>
          <p className='Datasets__muted'>{repo}</p>
          <div className='Datasets__hint'>
            <p>
              This dataset has no card yet. Cards live in Git next to the .dvc
              file. Create one with:
            </p>
            <pre>mlops dataset card init {path}</pre>
            <p className='Datasets__muted'>Then edit it, commit and push.</p>
          </div>
        </>
      )}
      {card && card.body && (
        <section className='Datasets__card'>
          <ReactMarkdown>{card.body}</ReactMarkdown>
        </section>
      )}
      {card && card.columns.length > 0 && (
        <>
          <h2>Schema</h2>
          <table className='Datasets__table'>
            <thead>
              <tr>
                <th>Column</th>
                <th>Type</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {card.columns.map((column) => (
                <tr key={column.name}>
                  <td className='Datasets__mono'>{column.name}</td>
                  <td>{column.type ?? '–'}</td>
                  <td>{column.description ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {card && Object.keys(card.splits).length > 0 && (
        <>
          <h2>Splits</h2>
          <table className='Datasets__table'>
            <thead>
              <tr>
                <th>Split</th>
                <th>Rows</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(card.splits).map(([split, rows]) => (
                <tr key={split}>
                  <td>{split}</td>
                  <td>{rows}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      <h2>Contents</h2>
      <dl className='Datasets__facts'>
        <dt>DVC hash</dt>
        <dd className='Datasets__mono'>{detail.dvc.dvc_hash ?? '–'}</dd>
        <dt>Size</dt>
        <dd>{formatBytes(detail.dvc.size_bytes ?? card?.size_bytes)}</dd>
        <dt>Files</dt>
        <dd>{detail.dvc.nfiles ?? '–'}</dd>
        <dt>Rows</dt>
        <dd>{card && card.rows !== null ? card.rows : '–'}</dd>
      </dl>
      <h2>Versions</h2>
      <table className='Datasets__table'>
        <thead>
          <tr>
            <th>Commit</th>
            <th>Date</th>
            <th>Change</th>
            <th>DVC hash</th>
          </tr>
        </thead>
        <tbody>
          {detail.versions.map((version, index) => (
            <tr key={`${version.commit}-${index}`}>
              <td className='Datasets__mono'>
                {(version.commit ?? '').slice(0, 8) || '–'}
              </td>
              <td>
                {version.date ? new Date(version.date).toLocaleString() : '–'}
              </td>
              <td>{version.message}</td>
              <td className='Datasets__mono'>
                {version.dvc_hash && version.dvc_hash === detail.dvc.dvc_hash
                  ? `${version.dvc_hash} (current)`
                  : version.dvc_hash || '–'}
              </td>
            </tr>
          ))}
          {detail.versions.length === 0 && (
            <tr>
              <td colSpan={4} className='Datasets__muted'>
                No history found.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <h2>Used by {detail.used_by.count} run(s)</h2>
      <table className='Datasets__table'>
        <thead>
          <tr>
            <th>Run</th>
            <th>Experiment</th>
            <th>Status</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {detail.used_by.runs.map((run) => (
            <tr key={run.id}>
              <td>
                <Link to={`/runs/${encodeURIComponent(run.id)}`}>
                  {run.name}
                </Link>
              </td>
              <td>{run.experiment}</td>
              <td>{run.status}</td>
              <td>{new Date(run.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

export default DatasetDetail;
