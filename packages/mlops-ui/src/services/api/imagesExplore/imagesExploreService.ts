import API from 'services/api/api';

import { IApiRequest } from 'types/services/services';

import { toExplorerSequenceQuery } from 'utils/explorer/sequenceJson';

const endpoints = {
  GET_IMAGES: 'v1/explorer/runs/search/images',
};

// Runs with images that match the query, each with its sampled items. The items carry blob_uri,
// a presigned GET for the image bytes.
function getImagesExploreData(params: {}): IApiRequest<any> {
  return API.get<any>(endpoints.GET_IMAGES, toExplorerSequenceQuery(params));
}

// The image bytes are read from their presigned URLs in the browser, not through the server.
// Resolves to [uri, bytes] pairs in the order of `uris`.
function getImagesByURIs(uris: string[]): IApiRequest<[string, ArrayBuffer][]> {
  const controller = new AbortController();
  return {
    call: () =>
      Promise.all(
        uris.map(async (uri): Promise<[string, ArrayBuffer]> => {
          const response = await fetch(uri, { signal: controller.signal });
          if (!response.ok) {
            throw new Error(
              `image request failed with HTTP ${response.status}`,
            );
          }
          return [uri, await response.arrayBuffer()];
        }),
      ),
    abort: () => controller.abort(),
  };
}

const imagesExploreService = {
  endpoints,
  getImagesExploreData,
  getImagesByURIs,
};

export default imagesExploreService;
