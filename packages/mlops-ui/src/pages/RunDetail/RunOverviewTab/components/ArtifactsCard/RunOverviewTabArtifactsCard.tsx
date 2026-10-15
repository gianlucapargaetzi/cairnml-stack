import React, { useState } from 'react';

import { Button, Card, Table, Text } from 'components/kit';
import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';
import BusyLoaderWrapper from 'components/BusyLoaderWrapper/BusyLoaderWrapper';

import artifactsService from 'services/api/artifacts/artifactsService';

import { formatBytes } from 'utils/datasets/datasets';

import { IRunOverviewTabArtifactsCardProps } from './RunOverviewTabArtifactsCard.d';

// The artifacts of the run, each with a download. A download asks the server for a presigned URL
// and opens it in a new tab; the bytes are read from storage, not through the server.
function RunOverviewTabArtifactsCard({
  artifacts,
  isRunInfoLoading,
}: IRunOverviewTabArtifactsCardProps) {
  const [error, setError] = useState<string | null>(null);

  function download(artifact: IRunArtifactRef) {
    setError(null);
    artifactsService
      .getDownloadUrl(artifact.run_id, artifact.id)
      .call()
      .then(({ url }) => window.open(url, '_blank', 'noopener'))
      .catch((requestError) =>
        setError(`${artifact.name}: ${requestError.message}`),
      );
  }

  return (
    <ErrorBoundary>
      <BusyLoaderWrapper isLoading={isRunInfoLoading} height='100%'>
        <Card
          title={`Run artifacts (${artifacts.length})`}
          className='RunOverviewTab__cardBox'
        >
          {error && (
            <Text size={12} color='error' role='alert'>
              {error}
            </Text>
          )}
          <Table
            columns={[
              { key: 'name', label: 'Name' },
              { key: 'kind', label: 'Kind' },
              { key: 'size', label: 'Size' },
              { key: 'download', label: '' },
            ]}
            rows={artifacts.map((artifact) => ({
              id: artifact.id,
              name: artifact.name,
              kind: artifact.kind,
              size: formatBytes(artifact.size),
              download: (
                <Button
                  variant='outlined'
                  size='small'
                  onClick={() => download(artifact)}
                >
                  Download
                </Button>
              ),
            }))}
            rowKey='id'
            emptyText='No artifacts were uploaded for this run.'
          />
        </Card>
      </BusyLoaderWrapper>
    </ErrorBoundary>
  );
}

type IRunArtifactRef = IRunOverviewTabArtifactsCardProps['artifacts'][number];

RunOverviewTabArtifactsCard.displayName = 'RunOverviewTabArtifactsCard';

export default React.memo<IRunOverviewTabArtifactsCardProps>(
  RunOverviewTabArtifactsCard,
);
