import projectPagesService from 'services/api/projectPages/projectPagesService';

import API from '../api';

// Tags belong to a project. A run carries tags of its project, attached through the explorer.
export interface ITagRow {
  id: string;
  project_id: string;
  name: string;
  color: string | null;
  description: string | null;
}

export interface ITagBody {
  name?: string;
  color?: string | null;
  description?: string | null;
}

function getProjectTags(projectId: string) {
  return API.get<ITagRow[]>(`v1/explorer/projects/${projectId}/tags`);
}

function createTag(projectId: string, body: ITagBody) {
  return API.post<ITagRow>(`v1/explorer/projects/${projectId}/tags`, body);
}

function updateTag(tagId: string, body: ITagBody) {
  return API.patch<ITagRow>(`v1/explorer/tags/${tagId}`, body);
}

function deleteTag(tagId: string) {
  return API.delete(`v1/explorer/tags/${tagId}`);
}

function attachTag(runId: string, tagId: string) {
  return API.post(`v1/explorer/runs/${runId}/tags/${tagId}`, {});
}

// Attaches a tag by name, as the run page does. The run's project decides which tag the name
// means; the tag is created when the project has none of that name.
function attachTagByName(runId: string, name: string) {
  let current: { abort: () => void } | null = null;
  return {
    call: async (): Promise<ITagRow> => {
      const info = await API.get<{ props: { project: string } }>(
        `v1/explorer/runs/${runId}/info`,
      ).call();
      const projects = await projectPagesService.getProjects().call();
      const project = projects.find((p) => p.slug === info.props.project);
      if (!project) {
        throw new Error('the run’s project is not one you can read');
      }
      const tags = await getProjectTags(project.id).call();
      const tag =
        tags.find((t) => t.name === name) ??
        (await createTag(project.id, { name }).call());
      await attachTag(runId, tag.id).call();
      return tag;
    },
    abort: () => current?.abort(),
  };
}

const tagPagesService = {
  getProjectTags,
  createTag,
  updateTag,
  deleteTag,
  attachTag,
  attachTagByName,
};

export default tagPagesService;
