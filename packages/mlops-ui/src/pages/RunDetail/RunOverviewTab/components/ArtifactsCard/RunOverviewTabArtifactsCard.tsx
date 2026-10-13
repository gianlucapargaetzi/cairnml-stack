import React, { useState } from 'react';

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
        <section className='RunOverviewTab__cardBox'>
          <h3>Run Artifacts ({artifacts.length})</h3>
          {error && <p role='alert'>{error}</p>}
          {artifacts.length === 0 ? (
            <p>No artifacts were uploaded for this run.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Kind</th>
                  <th>Size</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {artifacts.map((artifact) => (
                  <tr key={artifact.id}>
                    <td>{artifact.name}</td>
                    <td>{artifact.kind}</td>
                    <td>{formatBytes(artifact.size)}</td>
                    <td>
                      <button type='button' onClick={() => download(artifact)}>
                        Download
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </BusyLoaderWrapper>
    </ErrorBoundary>
  );
}

type IRunArtifactRef = IRunOverviewTabArtifactsCardProps['artifacts'][number];

RunOverviewTabArtifactsCard.displayName = 'RunOverviewTabArtifactsCard';

export default React.memo<IRunOverviewTabArtifactsCardProps>(
  RunOverviewTabArtifactsCard,
);
