# Web Pressure Tests

`k6`-репозиторий для авторизованного black-box HTTP pressure testing веб-сервера команды.

Проект не требует доступа к backend-коду, контейнерам или Ansible. Нагрузка идет только на согласованный внешний HTTP target из локального `.env`.

## Главное

- `TARGET_URL` не хранится в git;
- основной конфиг запуска лежит в локальном `.env`;
- результаты сохраняются в `results/`;
- каждый запуск создает `.json`, `.md` и `.log`;
- Prometheus можно подключить напрямую для автоматической вставки server-side метрик в Markdown-отчет;
- heavy-профили не запускаются пакетно без `ALLOW_HIGH_IMPACT_TESTS=true`;
- перед pressure-прогоном wrapper проверяет endpoint'ы через `curl`;
- RAM/network профили требуют подходящих endpoint'ов от команды разработки.

## Scope

Разрешено:

- smoke testing;
- endpoint discovery;
- throughput / RPS pressure;
- CPU pressure;
- memory/concurrency pressure через подготовленные endpoint'ы;
- network bandwidth pressure через large-response endpoint'ы;
- controlled capacity / failure-threshold search;
- сбор k6-отчетов и Prometheus-метрик.

Запрещено использовать проект для неавторизованных атак, обхода rate limit, сокрытия источника трафика, эксплуатации уязвимостей или тестирования сторонних систем.

## Требования

На runner должны быть установлены:

- `git`;
- `bash`;
- `curl`;
- `jq`;
- `k6`.

Проверка:

```bash
k6 version
curl --version
jq --version
```

### Установка k6 на Debian/Ubuntu

```bash
sudo rm -f /usr/share/keyrings/k6-archive-keyring.gpg
sudo rm -f /etc/apt/sources.list.d/k6.list

sudo apt-get update
sudo apt-get install -y ca-certificates gnupg2 curl jq

sudo install -d -m 0755 /etc/apt/keyrings

curl -fsSL https://dl.k6.io/key.gpg \
  | sudo gpg --batch --yes --dearmor \
  -o /etc/apt/keyrings/k6-archive-keyring.gpg

sudo chmod 0644 /etc/apt/keyrings/k6-archive-keyring.gpg

echo "deb [signed-by=/etc/apt/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
  | sudo tee /etc/apt/sources.list.d/k6.list

sudo apt-get update
sudo apt-get install -y k6
```

## Быстрый старт

```bash
git clone https://github.com/g1nry/load_web_testing.git
cd load_web_testing

cp .env.example .env
chmod +x scripts/*.sh
```

В `.env` укажи согласованный target:

```bash
TARGET_URL=https://example.internal
```

`TARGET_URL` лучше указывать без завершающего `/`.

## Основная конфигурация

Минимальный безопасный старт:

```bash
TARGET_URL=https://example.internal
REQUEST_TIMEOUT=5s
LOAD_ENDPOINTS=/
ENABLE_CACHE_BUSTER=false

TEST_PROFILES=smoke,discovery
ALLOW_HIGH_IMPACT_TESTS=false
```

`LOAD_ENDPOINTS` — fallback endpoint'ы для профилей, где не задан специальный список.

```bash
LOAD_ENDPOINTS=/
```

Перед pressure-тестами сначала запусти discovery и оставь только реально доступные пути с `2xx/3xx`. Endpoint'ы с `404`, `401`, `403` или редиректами в login лучше не добавлять в pressure-профили: k6 будет считать их failed requests.

`ENABLE_CACHE_BUSTER=true` добавляет уникальный query parameter к запросам. Включай это только если нужно специально обходить cache: уникальные URL резко увеличивают cardinality метрик k6 и могут нагрузить runner.

## Prometheus / Grafana

Если Prometheus доступен напрямую, добавь в `.env`:

```bash
PROMETHEUS_URL=http://IP:9090
PROMETHEUS_INSTANCE=
PROMETHEUS_NET_DEVICE=
PROMETHEUS_QUERY_STEP=30s
PROMETHEUS_QUERY_TIMEOUT=10
PROMETHEUS_APP_JOB=
PROMETHEUS_APP_INSTANCE=
PROMETHEUS_KUBE_NAMESPACE=
PROMETHEUS_KUBE_POD=
PROMETHEUS_KUBE_CONTAINER=
```

Если `PROMETHEUS_URL` задан, wrapper после k6-прогона запросит Prometheus за time range теста и допишет в Markdown-отчет:

- CPU usage avg/max;
- Memory usage avg/max;
- Network RX avg/max;
- Network TX avg/max;
- container restarts;
- OOMKilled / cAdvisor OOM events;
- pods in Failed/Unknown phase.

`PROMETHEUS_INSTANCE` можно оставить пустым, если нужно брать все instance. `PROMETHEUS_NET_DEVICE` можно оставить пустым, тогда будут использованы non-loopback network devices.

`PROMETHEUS_APP_JOB` и `PROMETHEUS_APP_INSTANCE` нужны для проверки scrape health самого приложения через `up{...}`. Для текущего Prometheus это, например:

```bash
PROMETHEUS_APP_JOB=podinfo
PROMETHEUS_APP_INSTANCE=10.103.120.187:9898
```

`PROMETHEUS_KUBE_NAMESPACE`, `PROMETHEUS_KUBE_POD`, `PROMETHEUS_KUBE_CONTAINER` нужны, если в Prometheus есть kube-state-metrics/cAdvisor и нужно сузить рестарты/OOM до конкретного сервиса. `PROMETHEUS_KUBE_POD` и `PROMETHEUS_KUBE_CONTAINER` работают как regex.

Ссылку на Grafana dashboard можно добавить отдельно:

```bash
GRAFANA_DASHBOARD_URL=http://81.26.176.68:3000/d/rYdddlPWk/node-exporter-full?orgId=1
```

Она попадет в Markdown-отчет как быстрый переход к визуализации.

## Профили

`smoke` — минимальная проверка `/`.

`discovery` — аккуратная проверка типовых endpoint'ов:

```text
/
/ping
/healthz
/readyz
/version
/metrics
```

`throughput` — RPS-oriented профиль на `ramping-arrival-rate`. Нужен, чтобы понять, сколько запросов в секунду выдерживает сервис.

`cpu` — CPU pressure через высокий RPS и опциональное отключение connection reuse. Нужен endpoint, который реально заставляет backend выполнять работу. Для текущего сервиса можно использовать `/metrics`, если команда подтвердила, что его сбор заметно грузит CPU.

`memory` — memory/concurrency pressure. Для текущего сервиса можно использовать `/delay/{n}`: много одновременных долгих запросов держат соединения и обработчики открытыми. Если `MEMORY_ENDPOINTS` не задан, тест выведет предупреждение.

`network` — bandwidth pressure. Для текущего сервиса можно использовать `/api/echo` с POST payload, если endpoint возвращает тело запроса обратно. Не используй `/metrics`, `/ping`, `/healthz`, `/readyz`, `/version` для network.

`capacity` — controlled поиск failure threshold по отдельным RPS-ступеням. Задача: автоматически выделить диапазон между последней стабильной нагрузкой и первой проблемной нагрузкой.

Все pressure-профили считаются high-impact:

```text
throughput
cpu
memory
network
capacity
```

Пакетно они запускаются только при:

```bash
ALLOW_HIGH_IMPACT_TESTS=true
```

## Переменные профилей

### Throughput

```bash
THROUGHPUT_ENDPOINTS=/
THROUGHPUT_RATE_STEPS=50,100,200,400
THROUGHPUT_RAMP_DURATION=30s
THROUGHPUT_HOLD_DURATION=1m
THROUGHPUT_RAMP_DOWN_DURATION=30s
THROUGHPUT_PRE_ALLOCATED_VUS=50
THROUGHPUT_MAX_VUS=500
```

### CPU

```bash
CPU_ENDPOINTS=/metrics
CPU_RATE_STEPS=25,50,100,200
CPU_RAMP_DURATION=30s
CPU_HOLD_DURATION=1m
CPU_RAMP_DOWN_DURATION=30s
CPU_PRE_ALLOCATED_VUS=100
CPU_MAX_VUS=1000
CPU_NO_CONNECTION_REUSE=false
```

Если `/metrics` действительно тяжелый для приложения, его можно использовать как CPU-pressure endpoint. Если он легкий или отдается не приложением, результат нужно читать как HTTP/RPS pressure, а не как полноценный CPU pressure.

`CPU_NO_CONNECTION_REUSE=true` делает тест гораздо жестче по TCP/NAT и может положить сеть runner'а раньше, чем будет найден CPU-предел сервиса. Включай это только отдельным согласованным прогоном.

### Memory

```bash
MEMORY_ENDPOINTS=/delay/30
MEMORY_VUS=300
MEMORY_DURATION=10m
MEMORY_REQUEST_TIMEOUT=45s
MEMORY_SLEEP_SECONDS=0
MEMORY_MIN_RESPONSE_BYTES=0
```

Для `/delay/{n}` выставляй `MEMORY_REQUEST_TIMEOUT` больше `n`, иначе runner сам оборвет запросы. `MEMORY_MIN_RESPONSE_BYTES=0` отключает проверку размера ответа, потому для delay важна не величина payload, а количество одновременно открытых запросов.

### Network

```bash
NETWORK_ENDPOINTS=/api/echo
NETWORK_METHOD=POST
NETWORK_PAYLOAD_BYTES=65536
NETWORK_CONTENT_TYPE=text/plain
NETWORK_RATE=200
NETWORK_DURATION=5m
NETWORK_PRE_ALLOCATED_VUS=100
NETWORK_MAX_VUS=1000
NETWORK_REQUEST_TIMEOUT=15s
NETWORK_MIN_RESPONSE_BYTES=10240
```

Для network pressure нужен endpoint, который отдает достаточно большой payload. Если `/api/echo` возвращает отправленное тело, размер нагрузки регулируется через `NETWORK_PAYLOAD_BYTES`.

### Capacity

```bash
CAPACITY_ENDPOINTS=/
CAPACITY_RATE_STEPS=50,100,200,400,800
CAPACITY_STEP_DURATION=1m
CAPACITY_GRACEFUL_STOP=30s
CAPACITY_FAILURE_RATE_LIMIT=0.05
CAPACITY_P95_LIMIT_MS=1000
CAPACITY_PRE_ALLOCATED_VUS=100
CAPACITY_MAX_VUS=2000
```

Capacity запускает каждую ступень как отдельный k6 scenario: `capacity_1_50_rps`, `capacity_2_100_rps` и так далее. Markdown-отчет строит таблицу по ступеням и выводит:

- last stable load;
- first failing load;
- failure rate;
- p95 latency;
- dropped iterations.

Если все ступени stable, значит окно нестабильности не найдено: нужно расширить `CAPACITY_RATE_STEPS`, увеличить длительность ступени или использовать более тяжелые endpoint'ы.

## Запуск

Один профиль:

```bash
./scripts/run-profile.sh smoke
./scripts/run-profile.sh discovery
./scripts/run-profile.sh throughput
./scripts/run-profile.sh cpu
./scripts/run-profile.sh memory
./scripts/run-profile.sh network
./scripts/run-profile.sh capacity
```

Или напрямую:

```bash
./scripts/run-smoke.sh
./scripts/run-discovery.sh
./scripts/run-throughput.sh
./scripts/run-cpu.sh
./scripts/run-memory.sh
./scripts/run-network.sh
./scripts/run-capacity.sh
```

Пакетный запуск читает `TEST_PROFILES`:

```bash
TEST_PROFILES=smoke,discovery
./scripts/run-suite.sh
```

Pressure suite:

```bash
TEST_PROFILES=smoke,discovery,throughput,cpu,memory,network,capacity
ALLOW_HIGH_IMPACT_TESTS=true
./scripts/run-suite.sh
```

`run-suite.sh` не останавливается на первом failed profile. Он проходит все разрешенные профили, а в конце выводит список упавших.

## Вывод во время запуска

Wrapper показывает:

1. Проектный баннер.
2. Метаданные запуска: profile, script, summary, report.
3. Endpoint audit для pressure-профилей.
4. Progressbar по расчетной длительности профиля.
5. Итоговый k6 summary.

k6 запускается в quiet-режиме. Raw stdout/stderr k6 сохраняется в `.log`, потом печатается после progressbar.

Endpoint audit перед pressure-тестами печатает `status`, размер ответа и время ответа. Для `throughput`, `cpu`, `memory`, `network`, `capacity` запуск остановится, если endpoint возвращает не `2xx/3xx`. Для `network` запуск также остановится, если endpoint похож на control endpoint или возвращает меньше `NETWORK_MIN_RESPONSE_BYTES`.

## Результаты

На каждый запуск создаются:

```text
results/<profile>-<timestamp>.json
results/<profile>-<timestamp>.md
results/<profile>-<timestamp>.log
```

Markdown-отчет содержит:

- параметры запуска;
- RPS;
- latency;
- checks;
- failure rate;
- data sent / received;
- среднюю сетевую нагрузку runner'а;
- thresholds;
- capacity window по RPS-ступеням для `capacity`;
- Prometheus server-side метрики, если `PROMETHEUS_URL` задан;
- поля для выводов по capacity/failure threshold.

## Как читать отчет

k6 показывает client-side сторону:

- сколько запросов отправили;
- какой RPS был достигнут;
- сколько было ошибок;
- какая latency;
- сколько данных ушло и пришло со стороны runner'а.

Prometheus/Grafana показывают server-side сторону:

- CPU;
- RAM;
- Network RX/TX;
- рестарты;
- OOM;
- 5xx/timeouts в инфраструктурных метриках.

Итог по устойчивости делается только при сопоставлении обоих слоев за один time range.

## Рекомендуемый порядок

1. Настроить `.env`.
2. Запустить `smoke`.
3. Запустить `discovery`.
4. Настроить endpoint'ы для pressure-профилей.
5. Запустить `throughput`.
6. Запустить `cpu`.
7. Если есть подходящие endpoint'ы, запустить `memory` и `network`.
8. Запустить `capacity` в согласованное окно.
9. Сопоставить Markdown-отчеты с Grafana/Prometheus.

## Проверка репозитория

Проверить shell:

```bash
find scripts -type f -exec bash -n {} \;
```

Проверить k6-сценарии без нагрузки:

```bash
for f in tests/*.js; do k6 inspect -e TARGET_URL=https://example.invalid "$f" >/dev/null || exit 1; done
```

## Частые проблемы

`TARGET_URL is required` — в `.env` нет `TARGET_URL` или запуск идет не из корня репозитория.

`memory` предупреждает про `MEMORY_ENDPOINTS` — профиль запущен без endpoint'а, который реально грузит память. Результат не стоит использовать как RAM pressure evidence.

`network` предупреждает про `NETWORK_ENDPOINTS` — профиль запущен без endpoint'а с большим ответом. Результат не стоит использовать как bandwidth pressure evidence.

`http_req_failed` красный, но checks зеленые — часто в endpoint'ы попали 4xx ответы. Для pressure-профилей оставляй только endpoint'ы, которые дают 2xx/3xx.

CPU почти не растет в Grafana — скорее всего профиль бьет по легким endpoint'ам (`/`, `/ping`, `/healthz`, `/version`). Для текущего сервиса попробуй `CPU_ENDPOINTS=/metrics`, если именно приложение генерирует этот ответ и это согласовано с командой.

Network поднимает system load, но bandwidth маленький — проверь, что в `NETWORK_ENDPOINTS` нет `/metrics` и других служебных endpoint'ов. `/metrics` может грузить сбор метрик и kernel/system time, но это плохой источник сетевой нагрузки.

Capacity не находит окно нестабильности — это нормально для простого или недогруженного сервиса. Значит все заданные RPS-ступени прошли по критериям `CAPACITY_FAILURE_RATE_LIMIT`, `CAPACITY_P95_LIMIT_MS` и dropped iterations. Подними верхние ступени, увеличь `CAPACITY_STEP_DURATION` или используй endpoint, который реально проходит через бизнес-логику сервиса.

High-cardinality warning от k6 — проверь, что `ENABLE_CACHE_BUSTER=false`. Уникальные query params создают слишком много time series.

Pressure-профиль пропущен в suite — включи `ALLOW_HIGH_IMPACT_TESTS=true`.

Prometheus-метрики не попали в отчет — проверь `PROMETHEUS_URL`, `PROMETHEUS_INSTANCE`, `PROMETHEUS_NET_DEVICE`, доступность `/api/v1/query`, `curl` и `jq`.

OOM/restart в отчете `n/a` — в Prometheus может не быть kube-state-metrics/cAdvisor или не настроены `PROMETHEUS_KUBE_NAMESPACE`, `PROMETHEUS_KUBE_POD`, `PROMETHEUS_KUBE_CONTAINER`.

## Структура

```text
tests/
  smoke.js
  discovery.js
  throughput.js
  cpu.js
  memory.js
  network.js
  capacity.js

config/
  endpoints.js
  thresholds.js
  report.js

scripts/
  run-smoke.sh
  run-discovery.sh
  run-throughput.sh
  run-cpu.sh
  run-memory.sh
  run-network.sh
  run-capacity.sh
  run-profile.sh
  run-suite.sh
  lib.sh
  fetch-prometheus-metrics.sh

results/
.env.example
.gitignore
README.md
```

`docs/` может существовать локально как рабочая зона для заметок и передачи teammate'у, но для запуска тестов он не требуется.
