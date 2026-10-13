import { IApiRequest } from 'types/services/services';

// Images in the explorer arrive in Phase 5 (sequences). Until then the request fails when called.
const unsupported = (): IApiRequest<any> => ({
  call: () => Promise.reject(new Error('Images are not supported yet.')),
  abort: () => undefined,
});

const endpoints = {
  GET_IMAGES: 'v1/explorer/images/search',
  GET_IMAGES_BY_URIS: 'v1/explorer/images/get-batch',
};

function getImagesExploreData(params: {}): IApiRequest<any> {
  return unsupported();
}

function getImagesByURIs(body: string[]): IApiRequest<any> {
  return unsupported();
}

const imagesExploreService = {
  endpoints,
  getImagesExploreData,
  getImagesByURIs,
};

export default imagesExploreService;
