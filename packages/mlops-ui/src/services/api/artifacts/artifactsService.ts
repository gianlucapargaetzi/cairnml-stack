import API from '../api';

// Artifacts of a run. The download is a presigned URL, valid for an hour, that the browser opens.
export interface IRunArtifact {
  id: string;
  run_id: string;
  name: string;
  kind: string;
  size: number;
}

function getDownloadUrl(runId: string, artifactId: string) {
  return API.get<{ url: string }>(
    `v1/runs/${runId}/artifacts/${artifactId}/download`,
  );
}

const artifactsService = { getDownloadUrl };

export default artifactsService;
