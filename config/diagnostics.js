import { Trend } from 'k6/metrics';

// One sample for the final response returned to the script, after redirects.
const responseBodyBytes = new Trend('response_body_bytes');

export const diagnosticOptions = {
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};

export function recordResponseSize(response, endpoint, method = 'GET', tags = {}) {
  if (response.body && typeof response.body.byteLength === 'number') {
    responseBodyBytes.add(response.body.byteLength, {
      ...tags,
      endpoint: endpoint.split('?')[0],
      method,
    });
  }
}
