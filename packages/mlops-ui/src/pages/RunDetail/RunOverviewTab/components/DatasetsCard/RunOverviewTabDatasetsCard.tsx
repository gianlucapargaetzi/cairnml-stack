import React from 'react';

import { Card, Table, Text } from 'components/kit';

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
    <Card
      title={`Datasets (${datasets.length})`}
      className='RunOverviewTab__cardBox'
    >
      <Table
        columns={[
          { key: 'path', label: 'Path' },
          { key: 'repo', label: 'Repository' },
          { key: 'version', label: 'Version (DVC hash)' },
        ]}
        rows={datasets.map((dataset, index) => ({
          id: `${dataset.repo ?? ''}-${dataset.path}-${index}`,
          path: dataset.path,
          repo: dataset.repo ?? '–',
          version: (
            <Text size={12} className='RunOverviewTab__mono'>
              {dataset.dvc_hash ?? 'unversioned'}
            </Text>
          ),
        }))}
        rowKey='id'
        emptyText='No datasets were used by this run.'
      />
    </Card>
  );
}

export default React.memo(RunOverviewTabDatasetsCard);
