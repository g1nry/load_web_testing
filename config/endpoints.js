export const defaultEndpoints = [
  '/',
  '/ping',
  '/healthz',
  '/readyz',
  '/version',
  '/metrics',
];

export function getTargetUrl() {
  const targetUrl = __ENV.TARGET_URL;

  if (!targetUrl) {
    throw new Error('TARGET_URL is required. Set it in .env or environment variables.');
  }

  return targetUrl.replace(/\/+$/, '');
}

export function buildUrl(targetUrl, endpoint) {
  const normalizedEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  return `${targetUrl}${normalizedEndpoint}`;
}

export function getLoadEndpoints() {
  const rawEndpoints = __ENV.LOAD_ENDPOINTS || '/';

  return rawEndpoints
    .split(',')
    .map((endpoint) => endpoint.trim())
    .filter(Boolean);
}

export function pickEndpoint(endpoints) {
  return endpoints[Math.floor(Math.random() * endpoints.length)];
}
