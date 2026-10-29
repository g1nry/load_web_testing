# Web Pressure Tests

`k6`-репозиторий для авторизованного black-box HTTP pressure testing веб-сервера команды.

Проект не требует доступа к backend-коду, контейнерам или Ansible. Нагрузка идет только на согласованный внешний HTTP target из локального `.env`.

## Главное

- `TARGET_URL` не хранится в git;
- основной конфиг запуска лежит в локальном `.env`;
- результаты сохраняются в `results/`;
- результаты разделены по профилям и форматам: `results/<profile>/{json,jsonl,csv,md,log}`;
- каждый запуск имеет общий идентификатор в именах summary, отчета, логов и диагностических файлов;
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

Для отчета по временным интервалам нужен Python 3.9 или новее (`python3` либо `python`). Сторонние Python-пакеты не требуются.

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
ENDPOINT_AUDIT_RETRIES=1

TEST_PROFILES=smoke,discovery
ALLOW_HIGH_IMPACT_TESTS=false
```

`LOAD_ENDPOINTS` — fallback endpoint'ы для профилей, где не задан специальный список.

```bash
LOAD_ENDPOINTS=/
```

Перед pressure-тестами сначала запусти discovery и оставь только реально доступные пути с `2xx/3xx`. Endpoint'ы с `404`, `401`, `403` или редиректами в login лучше не добавлять в pressure-профили: k6 будет считать их failed requests.

`ENABLE_CACHE_BUSTER=true` добавляет уникальный query parameter к запросам. Включай это только если нужно специально обходить cache: уникальные URL резко увеличивают cardinality метрик k6 и могут нагрузить runner.

`ENDPOINT_AUDIT_RETRIES` задает количество попыток preflight-проверки endpoint'ов перед pressure-тестом. Для `memory` wrapper по умолчанию делает 3 попытки, потому delay endpoint'ы могут отвечать медленно или нестабильно.

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

`benchmark` — продолжительный тест локальной сборки: прогрев, плавные переходы между RPS-ступенями, полки, выдержка на последней ступени и плавное снижение. Принимает loopback и адреса частной сети. Описание и настройки приведены ниже.

Все pressure-профили считаются high-impact:

```text
throughput
cpu
memory
network
capacity
benchmark
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

## Benchmark локальной сборки

Этот профиль предназначен для стенда на собственном оборудовании. Он использует отдельный `BENCHMARK_TARGET_URL`, поэтому прежний `TARGET_URL` не влияет на его цель. Допустимы `localhost`, IPv4 loopback, RFC1918 (`10/8`, `172.16/12`, `192.168/16`), IPv6 `::1` и ULA (`fc00::/7`). Для LAN-стенда укажи IP явно. Публичные адреса и DNS-алиасы отклоняются до preflight; ни k6, ни preflight не следуют за редиректами этого профиля. Настрой URL и ручки так, чтобы они сразу отвечали `2xx`.

Пример `.env` для отдельного сервера в LAN:

```bash
BENCHMARK_TARGET_URL=http://192.168.1.50:8080
BENCHMARK_ENDPOINTS=/,/shop,/tournaments
BENCHMARK_RUN_LABEL=cpu4_mem8_workers4
BENCHMARK_SERVER_CPU=4
BENCHMARK_SERVER_MEMORY=8GiB
BENCHMARK_SERVER_CONFIG=workers4_cacheon
BENCHMARK_GENERATOR_LOCATION=separate-host
```

Названия ручек должны соответствовать локальной сборке. Смесь запросов повторяется по кругу. Чтобы дать пути больший вес, повтори его: `/,/,/tournaments` дает примерно две трети запросов к `/`. Каждая итерация делает ровно один GET; тела ответов читаются целиком. Профиль сохраняет обычное переиспользование соединений и не добавляет cache-buster.

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| `BENCHMARK_TARGET_URL` | `http://127.0.0.1:8080` | Локальная сборка или IP стенда |
| `BENCHMARK_ENDPOINTS` | `/` | Упорядоченная смесь путей |
| `BENCHMARK_START_RATE` | `10` | RPS прогрева |
| `BENCHMARK_RATE_STEPS` | `50,100,200,400,600` | Возрастающие целевые RPS |
| `BENCHMARK_WARMUP_DURATION` | `20s` | Прогрев на стартовой скорости |
| `BENCHMARK_RAMP_DURATION` | `20s` | Переход к каждой следующей ступени |
| `BENCHMARK_HOLD_DURATION` | `2m` | Полка на каждой ступени |
| `BENCHMARK_SOAK_DURATION` | `5m` | Дополнительная выдержка на последней ступени; `0s` отключает |
| `BENCHMARK_RAMP_DOWN_DURATION` | `30s` | Снижение целевого RPS до нуля |
| `BENCHMARK_PRE_ALLOCATED_VUS` | `50` | Заранее подготовленные VU |
| `BENCHMARK_MAX_VUS` | `500` | Максимум VU генератора |
| `BENCHMARK_REQUEST_TIMEOUT` | `5s` | Таймаут запроса |
| `BENCHMARK_GRACEFUL_STOP` | `30s` | Ожидание начатых запросов после завершения расписания |

По умолчанию нагрузка идет 17 минут 30 секунд, затем возможны graceful stop и наблюдение доступности. Для запуска:

```bash
bash scripts/run-benchmark.sh
# либо
bash scripts/run-profile.sh benchmark
```

Профиль использует один сценарий `ramping-arrival-rate`: [k6 задает частоту запуска итераций](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/ramping-arrival-rate/) независимо от времени ответа. Число VU ограничивает возможность генератора поддерживать расписание; dropped iterations означают, что часть запросов не была запущена. Пороги `STOP_FAILURE_RATE`, `STOP_P95_MS` и `STOP_DELAY` продолжают действовать. Рост задержек и ошибок приводит к досрочному завершению, а не к переходу к остальным ступеням любой ценой.

В `results/benchmark/` сохраняются обычные артефакты и два дополнительных файла: `json/<run-id>.config.json` с полным планом/метками стенда и `csv/<run-id>.phases.csv` с результатами прогрева, переходов, полок и выдержки. Не достигнутые после остановки фазы остаются в таблице без измерений. Запрос относится к фазе, в которой был начат; он может завершиться уже на следующей фазе. Целевой RPS из плана не подменяет фактически измеренный RPS из интервалов.

### Сравнение настроек оборудования

Для каждого набора ресурсов задавай новый `BENCHMARK_RUN_LABEL` и записывай CPU, RAM и настройки приложения в `BENCHMARK_SERVER_CPU`, `BENCHMARK_SERVER_MEMORY`, `BENCHMARK_SERVER_CONFIG`. Это пользовательские метки: скрипт не меняет лимиты контейнеров или сервера. Ресурсы меняются на стороне стенда; план нагрузки, смесь ручек, данные и состояние кеша следует сохранять одинаковыми для сопоставимых прогонов. По возможности запускай генератор с отдельной машины; запуск рядом с приложением делит с ним CPU/RAM и искажает предел сервера.

После нескольких прогонов собери общую таблицу:

```bash
python3 scripts/compare-benchmarks.py results/benchmark/json \
  --output results/benchmark/csv/comparison.csv
```

Она содержит метки CPU/RAM, настройки приложения, средний и пиковый RPS, p95/p99, ошибки, таймауты, трафик, первый проблемный интервал и наблюдение доступности после нагрузки. Сравнивай строки с одинаковым `workload_id`: он учитывает план, смесь запросов, параметры генератора, критерии ошибок/задержек и ширину интервалов. Метки ресурсов и адрес стенда в этот идентификатор не входят. Незавершенные или неполные результаты отмечаются отдельно; один прогон не является точной оценкой предельной мощности сервера.

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
./scripts/run-profile.sh benchmark
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
./scripts/run-benchmark.sh
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

Например, файлы CPU-профиля сохраняются так:

```text
results/cpu/
  json/
    <run-id>.summary.json
    <run-id>.diagnostics.json
    <run-id>.run.json
  jsonl/
    <run-id>.points.jsonl
    <run-id>.runner.jsonl
    <run-id>.probes.jsonl
  csv/
    <run-id>.intervals.csv
    <run-id>.endpoints.csv
    <run-id>.endpoint-intervals.csv
  md/
    <run-id>.md
  log/
    <run-id>.log
```

`run-id` имеет вид `cpu-20261029T170000Z-12345`: профиль, время UTC и PID оболочки. Остальные профили получают такие же подпапки. Прежние результаты в корне `results/` сохраняются. Если preflight завершился ошибкой, остается лог проверки; остальные файлы появляются по мере выполнения.

`summary.json` содержит агрегаты k6; `diagnostics.json` — клиентскую диагностику, интервалы, ручки и результаты наблюдения; `run.json` — время начала/окончания нагрузки и код завершения k6. Сырые потоки имеют формат JSON Lines, поэтому для них выделена папка `jsonl`.

Markdown-отчет содержит:

- параметры запуска;
- RPS;
- latency;
- checks;
- failure rate;
- data sent / received;
- среднюю сетевую нагрузку runner'а;
- пиковый RPS за интервал и первый интервал с превышением порогов, если анализатор отработал;
- thresholds;
- capacity window по RPS-ступеням для `capacity`;
- Prometheus server-side метрики, если `PROMETHEUS_URL` задан;
- HTTP-статусы, коды ошибок k6, количество неуспешных checks;
- задержки по HTTP-фазам и по ручкам, p95/p99, размеры тел ответов;
- наблюдения CPU/RAM и сети генератора;
- результаты независимой проверки доступности и наблюдения после нагрузки.

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

По клиентским данным можно оценить доступность, задержки и пропускную способность в условиях конкретного прогона. Для определения причины деградации нужны серверные метрики. Названия `cpu`, `memory` и `network` описывают способ нагрузки, но сами по себе не подтверждают, какой ресурс оказался ограничением.

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
find scripts -name '*.sh' -type f -exec bash -n {} \;
```

Проверить k6-сценарии без нагрузки:

```bash
for f in tests/*.js; do k6 inspect -e TARGET_URL=https://example.invalid "$f" >/dev/null || exit 1; done
```

Проверить анализатор на локальных данных:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Если `K6_BINARY` указывает на установленный k6, эти же тесты также проверяют реальные запросы на локальный сервер, gzip-ответы и остановку по ошибкам. Без этой переменной две проверки k6 пропускаются. Полный Bash-wrapper проверяется отдельно; локальный `.env` в этих проверках не читается:

```bash
K6_BINARY="$(command -v k6)" python3 -m unittest discover -s tests -p 'test_*.py' -v
bash tests/test-wrapper.sh "$(command -v k6)"
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
  benchmark.js

config/
  endpoints.js
  thresholds.js
  report.js
  diagnostics.js
  benchmark.js

scripts/
  run-smoke.sh
  run-discovery.sh
  run-throughput.sh
  run-cpu.sh
  run-memory.sh
  run-network.sh
  run-capacity.sh
  run-benchmark.sh
  run-profile.sh
  run-suite.sh
  lib.sh
  fetch-prometheus-metrics.sh
  analyze-metrics.py
  observe-run.py
  compare-benchmarks.py

results/
.env.example
.gitignore
README.md
```

`docs/` может существовать локально как рабочая зона для заметок и передачи teammate'у, но для запуска тестов он не требуется.


## Временной ряд и пороги остановки

Для pressure-профилей добавлены пороги досрочной остановки. Они дополняют исходные пороги успешности профиля:

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| `STOP_FAILURE_RATE` | `0.10` | Остановить тест при доле HTTP-ошибок от 10% |
| `STOP_P95_MS` | `2000` | Остановить тест при p95 от 2000 мс |
| `STOP_DELAY` | `30s` | Задержка перед началом проверки остановки |
| `REPORT_INTERVAL_SECONDS` | `10` | Ширина интервала в CSV, в секундах |

k6 проверяет пороги по накопленным данным с начала прогона. Это не проверка последних 10 секунд и не мгновенная остановка. Задержка `STOP_DELAY` позволяет собрать первые измерения. Отдельные интервалы в отчете анализируются после прогона; превышение в CSV может не совпадать с решением k6 об остановке.

Wrapper записывает точки k6 в `.points.jsonl`, затем запускает Python-анализатор. Он создает три CSV и `diagnostics.json`, обновляет раздел диагностики в Markdown. `intervals.csv` содержит завершенные HTTP-запросы, общий и успешный RPS, долю ошибок, p95/p99, переданные и полученные байты и скорости, dropped iterations, VU, HTTP-статусы, коды ошибок k6 и HTTP-фазы. `endpoints.csv` содержит итоги по паре метод/путь, а `endpoint-intervals.csv` — измерения каждой пары по интервалам с трафиком. Query-параметры при группировке удаляются.

Интервалы выровнены по UTC. Пустые интервалы между измерениями сохраняются. Первый и последний интервалы могут быть неполными; RPS делится на полную ширину интервала. Запросы учитываются по завершению, включая редиректы. Отсутствующее измерение задержки или доли ошибок остается пустым. Байты — счетчики передачи k6, а не размер распакованного тела страницы и не счетчики сетевого интерфейса сервера.

Markdown показывает пиковый RPS за интервал и первый интервал с превышением заданной доли ошибок или p95. Общий средний RPS берется из summary k6. Эти измерения описывают клиентскую сторону. Сырые файлы могут занимать много места; точные квантили хранят измерения задержки в памяти анализатора.

Фазы `blocked`, `connecting`, `tls_handshaking`, `sending`, `waiting` (TTFB) и `receiving` помогают увидеть, на какой части запроса выросло время. `http_req_duration` не включает установление соединения. Определения приведены в [справочнике метрик k6](https://grafana.com/docs/k6/latest/using-k6/metrics/reference/). Высокий TTFB сам по себе не доказывает нехватку CPU или проблему БД.

Отчет отдельно считает таймауты запросов (`1050`), таймауты соединения (`1211`), отказ соединения (`1212`), сбросы (`1220`), DNS- и TLS-ошибки по [кодам ошибок k6](https://grafana.com/docs/k6/latest/javascript-api/). Он также показывает время первой и последней ошибки HTTP. Если число запросов в сыром потоке расходится с summary, результаты помечаются как неполные.

Профили принимают тела ответов как `ArrayBuffer` и записывают `response_body_bytes`. Это размер декодированного тела последнего ответа после редиректов; счетчики `data_sent`/`data_received` относятся к другому объему и включают HTTP-трафик. В CSV отдельно указано количество измерений размера тела. Если данных нет, поле остается пустым. Для `network` и `memory` проверки минимального размера теперь сравнивают байты, а не длину строки.

### Генератор и независимая проверка доступности

Python-наблюдатель работает отдельным процессом рядом с k6. На Linux он примерно раз в секунду собирает RSS и CPU процесса k6, доступную память и занятость CPU хоста, счетчики сети хоста без loopback. CPU процесса выражается в процентах одного логического ядра и может превышать 100%. Сетевая статистика хоста включает другой трафик и может учитывать виртуальные интерфейсы; это не точная оценка трафика теста. На других ОС эти показатели остаются недоступными. Пробы HTTP и анализ результатов продолжают работать.

Во время нагрузки и после нее наблюдатель отправляет отдельный редкий GET-запрос. Он измеряет время до получения заголовков, не загружает тело и не следует за редиректами. Это проверка доступности выбранного пути, не проверка содержимого страницы. Дополнительные запросы не входят в RPS k6.

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| `ENABLE_DIAGNOSTIC_PROBE` | `true` | Включить независимые HTTP-пробы; `false` оставляет только сбор ресурсов |
| `DIAGNOSTIC_PROBE_ENDPOINT` | `/` | Путь на том же сайте; лучше выбрать легкую публичную ручку |
| `DIAGNOSTIC_PROBE_INTERVAL_SECONDS` | `5` | Пауза после завершения пробы; минимум 5 секунд, пробы не перекрываются |
| `DIAGNOSTIC_PROBE_TIMEOUT_SECONDS` | `3` | Таймаут пробы; максимум 10 секунд |
| `DIAGNOSTIC_PROBE_LIMIT_MS` | `2000` | Допустимое время получения заголовков |
| `RECOVERY_OBSERVATION_SECONDS` | `60` | Окно наблюдения после нагрузки; максимум 600 секунд |
| `RECOVERY_HEALTHY_SAMPLES` | `3` | Сколько последовательных успешных проб нужно для подтверждения доступности |

Успешная проба — HTTP `2xx/3xx` с временем заголовков ниже лимита. Отчет показывает ошибки проб во время нагрузки и время до подтвержденной последовательности после нее. Это время подтверждения с точностью до интервала, а не точный момент восстановления; окно должно позволять собрать нужное число проб. Если подтверждение не получено, отчет так и пишет. Таймаут уже начатой пробы может немного продлить окно наблюдения. Wrapper дожидается завершения наблюдателя перед анализом и сохраняет исходный код завершения k6.

Если Python недоступен при запуске, сырые точки остаются для последующего анализа:

```bash
python3 scripts/analyze-metrics.py \
  results/cpu/jsonl/RUN.points.jsonl \
  results/cpu/csv/RUN.intervals.csv \
  results/cpu/md/RUN.md 10 \
  --endpoints-csv results/cpu/csv/RUN.endpoints.csv \
  --endpoint-intervals-csv results/cpu/csv/RUN.endpoint-intervals.csv \
  --diagnostics-json results/cpu/json/RUN.diagnostics.json \
  --runner-samples results/cpu/jsonl/RUN.runner.jsonl \
  --probe-samples results/cpu/jsonl/RUN.probes.jsonl \
  --run-metadata results/cpu/json/RUN.run.json \
  --summary-json results/cpu/json/RUN.summary.json
```

Повторный анализ обновляет свой раздел отчета. Оборванная последняя строка JSONL пропускается с предупреждением; повреждение в середине файла считается ошибкой.
