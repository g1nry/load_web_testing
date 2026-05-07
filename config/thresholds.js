export const smokeThresholds = {
  http_req_failed: ['rate<0.05'],
  http_req_duration: ['p(95)<1000'],
};

export const discoveryThresholds = {
  http_req_duration: ['p(95)<3000'],
};

export const throughputThresholds = {
  http_req_failed: ['rate<0.10'],
  http_req_duration: ['p(95)<2000'],
};

export const cpuThresholds = {
  http_req_failed: ['rate<0.20'],
  http_req_duration: ['p(95)<3000'],
};

export const memoryThresholds = {
  http_req_failed: ['rate<0.20'],
  http_req_duration: ['p(95)<5000'],
};

export const networkThresholds = {
  http_req_failed: ['rate<0.20'],
  http_req_duration: ['p(95)<5000'],
};

export const capacityThresholds = {
  http_req_failed: ['rate<0.30'],
  http_req_duration: ['p(95)<5000'],
};
