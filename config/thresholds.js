export const smokeThresholds = {
  http_req_failed: ['rate<0.05'],
  http_req_duration: ['p(95)<1000'],
};

export const discoveryThresholds = {
  http_req_duration: ['p(95)<3000'],
};

export const baselineThresholds = {
  http_req_failed: ['rate<0.05'],
  http_req_duration: ['p(95)<1000'],
};

export const loadThresholds = {
  http_req_failed: ['rate<0.10'],
  http_req_duration: ['p(95)<2000'],
};

export const stressThresholds = {
  http_req_failed: ['rate<0.20'],
  http_req_duration: ['p(95)<3000'],
};

export const spikeThresholds = {
  http_req_failed: ['rate<0.20'],
  http_req_duration: ['p(95)<3000'],
};

export const enduranceThresholds = {
  http_req_failed: ['rate<0.10'],
  http_req_duration: ['p(95)<2000'],
};
