import { IApiRequest } from 'types/services/services';

import API from '../api';

const endpoints = {
  PROJECTS: 'v1/projects',
  PROJECT_TAGS: (projectId: string) => `v1/explorer/projects/${projectId}/tags`,
};

// The tags of every project the user can read, in one list. Each tag keeps its project id.
// Creating, renaming, archiving and deleting tags arrive with the project pages (Phase 6).
function getTags(): IApiRequest<any[]> {
  const requests: IApiRequest<any>[] = [];
  return {
    call: async (detail?: any) => {
      const list = API.get<any[]>(endpoints.PROJECTS);
      requests.push(list);
      const projects = await list.call(detail);
      const lists = await Promise.all(
        projects.map((project) => {
          const request = API.get<any[]>(endpoints.PROJECT_TAGS(project.id));
          requests.push(request);
          return request.call(detail);
        }),
      );
      return lists
        .flat()
        .map((tag) => ({ ...tag, run_count: 0, archived: false }));
    },
    abort: () => requests.forEach((request) => request.abort()),
  };
}

function unsupported(what: string): IApiRequest<never> {
  return {
    call: () => Promise.reject(new Error(`${what} is not supported yet.`)),
    abort: () => undefined,
  };
}

function getTagRuns(id: string) {
  return unsupported(`Listing the runs of tag ${id}`);
}

function createTag(body: object) {
  return unsupported('Creating tags');
}

function updateTag(body: object, id: string) {
  return unsupported(`Changing tag ${id}`);
}

function getTagById(id: string) {
  return unsupported(`Reading tag ${id}`);
}

function hideTag(id: string, archived: boolean) {
  return unsupported(`Archiving tag ${id}`);
}

function deleteTag(id: string) {
  return unsupported(`Deleting tag ${id}`);
}

const tagsService = {
  endpoints,
  getTags,
  createTag,
  updateTag,
  getTagById,
  getTagRuns,
  hideTag,
  deleteTag,
};

export default tagsService;
