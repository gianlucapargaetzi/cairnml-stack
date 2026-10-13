import React from 'react';

export interface IRunDatasetRef {
  path: string;
  repo?: string | null;
  dvc_hash?: string | null;
  commit?: string | null;
}

// The datasets the run was started with: each DVC path, its repository and the hash of the
// version used. The hash is what makes the run's data reproducible.
function RunOverviewTabDatasetsCard({
  datasets,
}: {
  datasets: IRunDatasetRef[];
}) {
  return (
    <section className='RunOverviewTab__cardBox'>
      <h3>Datasets ({datasets.length})</h3>
      {datasets.length === 0 ? (
        <p>No datasets were used by this run.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Path</th>
              <th>Repository</th>
              <th>Version (DVC hash)</th>
            </tr>
          </thead>
          <tbody>
            {datasets.map((dataset, index) => (
              <tr key={`${dataset.repo ?? ''}-${dataset.path}-${index}`}>
                <td>{dataset.path}</td>
                <td>{dataset.repo ?? '–'}</td>
                <td>
                  <code>{dataset.dvc_hash ?? 'unversioned'}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export default React.memo(RunOverviewTabDatasetsCard);
