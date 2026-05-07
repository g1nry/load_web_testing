import http from 'k6/http';
import { check, sleep } from 'k6';
import { defaultEndpoints, getTargetUrl, buildUrl } from '../config/endpoints.js';
import { buildSummary } from '../config/report.js';
import { discoveryThresholds } from '../config/thresholds.js';

const targetUrl = getTargetUrl();
const requestTimeout = __ENV.REQUEST_TIMEOUT || '5s';
const sleepSeconds = Number(__ENV.SLEEP_SECONDS || '1');

export const options = {
  vus: Number(__ENV.DISCOVERY_VUS || '1'),
  duration: __ENV.DISCOVERY_DURATION || '10s',
  thresholds: discoveryThresholds,
};

export default function () {
  for (const endpoint of defaultEndpoints) {
    const url = buildUrl(targetUrl, endpoint);

    const response = http.get(url, {
      timeout: requestTimeout,
      tags: {
        endpoint,
      },
    });

    check(response, {
      [`${endpoint} responded`]: (res) => res.status > 0,
      [`${endpoint} is not server error`]: (res) => res.status < 500,
    });

    console.log(`${endpoint} -> HTTP ${response.status}`);
    sleep(sleepSeconds);
  }
}

export function handleSummary(data) {
  return buildSummary(data);
}
