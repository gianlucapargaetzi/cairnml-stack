import { getAPIHost } from 'config/config';

export const CONTENT_TYPE = {
  JSON: 'application/json',
  FORM_DATA: 'application/x-www-form-urlencoded',
};

// The session lives in an httpOnly cookie set by the server. The CSRF token is kept in memory
// and sent with every write; it is read from /api/v1/me when the app starts.
let csrfToken = '';

export function setCsrfToken(token: string) {
  csrfToken = token;
}

// Sends the browser to sign in and back to the page it was on.
export function redirectToSignIn() {
  const next = encodeURIComponent(
    `${window.location.pathname}${window.location.search}`,
  );
  window.location.assign(`/ui/auth/login?next=${next}`);
}

function createAPIRequestWrapper<ResponseDataType>(
  url: string,
  options: RequestInit = {},
  stream: boolean = false,
  apiHost: string = getAPIHost(),
) {
  const controller = new AbortController();
  const signal = controller.signal;

  return {
    call: (exceptionHandler?: (error: ResponseDataType) => any) =>
      new Promise((resolve: (data: ResponseDataType) => void, reject) => {
        fetch(`${apiHost}/${url}`, { ...options, signal })
          .then(async (response) => {
            try {
              if (response.status >= 400) {
                if (response.status === 401) {
                  redirectToSignIn();
                }
                // The body is read once here; the error goes to the caller and the request fails.
                const body = await response.json().catch(() => ({}));
                if (typeof exceptionHandler === 'function') {
                  exceptionHandler(body);
                }
                reject(
                  new Error(
                    String(body.detail ?? body.message ?? response.statusText),
                  ),
                );
                return;
              }
              const data = stream ? response.body : await response.json();

              resolve(data);
            } catch (err: Error | any) {
              if (typeof exceptionHandler === 'function') {
                exceptionHandler(err);
              }
              reject(err);
            }
          })
          .catch((err: Error | any) => {
            if (err.name === 'AbortError') {
              // Fetch aborted
            } else {
              if (typeof exceptionHandler === 'function') {
                exceptionHandler(err);
              }
              reject(err);
            }
          });
      }),
    abort: () => controller.abort(),
  };
}

function getStream<ResponseDataType>(
  url: string,
  params?: {},
  options?: RequestInit,
  apiHost: string = getAPIHost(),
) {
  return createAPIRequestWrapper<ResponseDataType>(
    `${url}${
      options?.method === 'POST'
        ? ''
        : params
        ? '?' + new URLSearchParams(params).toString()
        : ''
    }`,
    {
      method: 'GET',
      ...options,
      headers: getRequestHeaders(),
      ...(options?.method === 'POST' && {
        body: JSON.stringify(params),
      }),
    },
    true,
    apiHost,
  );
}

function getStream1<ResponseDataType>(
  url: string,
  params?: {},
  options?: RequestInit,
  apiHost: string = getAPIHost(),
) {
  return createAPIRequestWrapper<ResponseDataType>(
    `${url}${
      options?.method === 'POST' && params
        ? '?' + new URLSearchParams(params).toString()
        : ''
    }`,
    {
      method: 'GET',
      ...options,
      headers: getRequestHeaders(),
      ...(options?.method === 'POST' && {
        body: JSON.stringify(options.body),
      }),
    },
    true,
    apiHost,
  );
}

function get<ResponseDataType>(
  url: string,
  params?: {},
  options?: RequestInit,
  apiHost: string = getAPIHost(),
) {
  return createAPIRequestWrapper<ResponseDataType>(
    `${url}${params ? '?' + new URLSearchParams(params).toString() : ''}`,
    {
      method: 'GET',
      ...options,
      headers: getRequestHeaders(),
    },
    false,
    apiHost,
  );
}

function post<ResponseDataType>(
  url: string,
  data: object,
  options?: RequestInit,
  apiHost: string = getAPIHost(),
) {
  return createAPIRequestWrapper<ResponseDataType>(
    url,
    {
      method: 'POST',
      ...options,
      headers: getWriteHeaders(),
      body: JSON.stringify(data),
    },
    false,
    apiHost,
  );
}

function put<ResponseDataType>(
  url: string,
  data: object,
  options?: RequestInit,
  apiHost: string = getAPIHost(),
) {
  return createAPIRequestWrapper<ResponseDataType>(
    url,
    {
      method: 'PUT',
      ...options,
      headers: getWriteHeaders(),
      body: JSON.stringify(data),
    },
    false,
    apiHost,
  );
}

function patch<ResponseDataType>(
  url: string,
  data: object,
  options?: RequestInit,
  apiHost: string = getAPIHost(),
) {
  return createAPIRequestWrapper<ResponseDataType>(
    url,
    {
      method: 'PATCH',
      ...options,
      headers: getWriteHeaders(),
      body: JSON.stringify(data),
    },
    false,
    apiHost,
  );
}

function remove<ResponseDataType>(
  url: string,
  options?: RequestInit,
  apiHost: string = getAPIHost(),
) {
  return createAPIRequestWrapper<ResponseDataType>(
    url,
    {
      method: 'DELETE',
      ...options,
      headers: getWriteHeaders(),
    },
    false,
    apiHost,
  );
}

/**
 * getTimezoneOffset is a function that returns the timezone offset
 * @returns string
 * @example
 * const timezoneOffset = getTimezoneOffset();
 */
function getTimezoneOffset(): string {
  return `${new Date().getTimezoneOffset()}`;
}

/**
 * getRequestHeaders is a function that returns the request headers
 * @returns object
 * @example
 * const requestHeaders = getRequestHeaders();
 * const response = await fetch(`${API_ROOT}${endpoint}`, {
 *  method: "POST",
 *  headers: requestHeaders,
 *  body: JSON.stringify(data),
 * });
 */
function getRequestHeaders(headers = {}) {
  return {
    'X-Timezone-Offset': getTimezoneOffset(),
    'Content-Type': CONTENT_TYPE.JSON,
    ...headers,
  };
}

export function getCsrfToken() {
  return csrfToken;
}

function getWriteHeaders() {
  return getRequestHeaders({ 'X-CSRF-Token': csrfToken });
}

/**
 * parseResponse is a generic function that parses the response body
 * @param response is the response object
 * @returns <T>
 * @throws Error
 * @example
 * const response = await fetch(`${API_ROOT}${endpoint}`);
 * return parseResponse<T>(response);
 */

const API = {
  get,
  getStream,
  getStream1,
  post,
  put,
  patch,
  delete: remove,
};

export default API;
