// MLOps Flow sends no analytics. The exports stay so the call sites compile; every call is a
// no-op and nothing leaves the browser. (The Aim original sent events to Segment.)
export function isDev() {
  return process.env.NODE_ENV === 'development';
}

export const init = () => {};

export const pageView = (pageName: string, pageCat: string | null = null) => {};

export const trackEvent = (eventName: string, properties: object = {}) => {};
