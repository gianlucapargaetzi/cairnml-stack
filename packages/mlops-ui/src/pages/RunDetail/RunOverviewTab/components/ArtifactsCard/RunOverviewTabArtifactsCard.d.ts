import { IRunArtifact } from 'services/api/artifacts/artifactsService';

export interface IRunOverviewTabArtifactsCardProps {
  artifacts: IRunArtifact[];
  isRunInfoLoading: boolean;
}
