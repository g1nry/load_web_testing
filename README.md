# Web Load Tests

`k6`-репозиторий для авторизованных black-box HTTP load tests веб-сервера команды.

Проект не требует знания backend/framework, не лезет в контейнеры и не зависит от Ansible. Все тесты работают только через внешний HTTP target, который задается локально перед запуском.

## Главное

- реальный `TARGET_URL` не хранится в репозитории;
- основной способ настройки wrapper-скриптов — локальный `.env`;
- сами `k6`-сценарии читают параметры из переменных окружения;
- публичный пример настроек лежит в `.env.example`;
- результаты сохраняются в `results/`;
- `.env` и `results/` не коммитятся;
- тяжелые профили не запускаются пакетно без явного флага.

## Scope

Разрешено:

- smoke testing;
- endpoint discovery;
- baseline load testing;
- load testing;
- controlled stress testing;
- controlled spike testing;
- endurance testing;
- сохранение локальных `k6` summary.

Запрещено использовать этот проект для неавторизованных атак, обхода rate limit, сокрытия источника трафика, эксплуатации уязвимостей или тестирования сторонних систем.

## Требования

На Linux runner должны быть установлены:

- `git`;
- `bash`;
- `k6`.

Проверка:

```bash
k6 version
```

### Установка k6 на Debian/Ubuntu

`k6` обычно не ставится из стандартных `apt`-репозиториев. Нужно подключить репозиторий `dl.k6.io`.

```bash
sudo rm -f /usr/share/keyrings/k6-archive-keyring.gpg
sudo rm -f /etc/apt/sources.list.d/k6.list

sudo apt-get update
sudo apt-get install -y ca-certificates gnupg2 curl

sudo install -d -m 0755 /etc/apt/keyrings

curl -fsSL https://dl.k6.io/key.gpg \
  | sudo gpg --batch --yes --dearmor \
  -o /etc/apt/keyrings/k6-archive-keyring.gpg

sudo chmod 0644 /etc/apt/keyrings/k6-archive-keyring.gpg

echo "deb [signed-by=/etc/apt/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
  | sudo tee /etc/apt/sources.list.d/k6.list

sudo apt-get update
sudo apt-get install -y k6

k6 version
```

## Быстрый старт

```bash
git clone https://github.com/g1nry/load_web_testing.git
cd load_web_testing

cp .env.example .env
chmod +x scripts/*.sh
```

Открой `.env` и замени плейсхолдер на согласованный target:

```bash
TARGET_URL=https://example.internal
```

Реальный адрес стенда не нужно добавлять в git.

Перед первым запуском убедись, что `TARGET_URL` задан:

```bash
grep '^TARGET_URL=' .env
```

## Основная конфигурация

Минимальный безопасный старт:

```bash
TARGET_URL=https://example.internal
REQUEST_TIMEOUT=5s
SLEEP_SECONDS=1
LOAD_ENDPOINTS=/

TEST_PROFILES=smoke,discovery,baseline
ALLOW_HIGH_IMPACT_TESTS=false
```

`TARGET_URL` лучше указывать без завершающего `/`.

Wrapper-скрипты из `scripts/` перед запуском читают `.env`. Для разовых override'ов проще временно изменить `.env` или запускать `k6 run tests/<profile>.js` напрямую с нужными переменными окружения.

`LOAD_ENDPOINTS` поддерживает несколько путей через запятую:

```bash
LOAD_ENDPOINTS=/,/ping,/version
```

Перед добавлением endpoint'ов в нагрузочные профили сначала запусти discovery и оставь только реально доступные пути.

## Переменные профилей

Общие переменные:

| Переменная | Назначение |
| --- | --- |
| `TARGET_URL` | Согласованный HTTP target без завершающего `/` |
| `REQUEST_TIMEOUT` | Таймаут одного HTTP-запроса |
| `SLEEP_SECONDS` | Пауза между итерациями виртуального пользователя |
| `LOAD_ENDPOINTS` | Список endpoint'ов для нагрузочных профилей через запятую |
| `TEST_PROFILES` | Список профилей для `run-suite.sh` через запятую |
| `ALLOW_HIGH_IMPACT_TESTS` | Разрешает пакетный запуск `stress`, `spike`, `endurance` |

Профильные переменные:

| Профиль | Переменные |
| --- | --- |
| `smoke` | `SMOKE_VUS`, `SMOKE_DURATION` |
| `discovery` | `DISCOVERY_VUS`, `DISCOVERY_DURATION` |
| `baseline` | `BASELINE_VUS`, `BASELINE_DURATION` |
| `load` | `LOAD_VUS`, `LOAD_DURATION` |
| `stress` | `STRESS_STAGE_1_VUS`, `STRESS_STAGE_1_DURATION`, `STRESS_STAGE_2_VUS`, `STRESS_STAGE_2_DURATION`, `STRESS_STAGE_3_VUS`, `STRESS_STAGE_3_DURATION`, `STRESS_RAMP_DOWN_DURATION` |
| `spike` | `SPIKE_LOW_VUS`, `SPIKE_HIGH_VUS`, `SPIKE_LOW_DURATION`, `SPIKE_HIGH_DURATION`, `SPIKE_RECOVERY_DURATION` |
| `endurance` | `ENDURANCE_VUS`, `ENDURANCE_DURATION` |

## Пакетный запуск

Для обычного запуска используй suite-runner:

```bash
./scripts/run-suite.sh
```

Он читает список профилей из `.env`:

```bash
TEST_PROFILES=smoke,discovery,baseline
```

Профили `stress`, `spike` и `endurance` считаются high-impact. При пакетном запуске они будут пропущены, пока явно не включен флаг:

```bash
ALLOW_HIGH_IMPACT_TESTS=true
```

Пример для согласованного окна расширенного тестирования:

```bash
TEST_PROFILES=smoke,baseline,load,stress,spike,endurance
ALLOW_HIGH_IMPACT_TESTS=true
```

Suite запускает профили по порядку. Если один профиль завершился ошибкой, следующие профили все равно будут запущены, а в конце suite вернет non-zero exit code и выведет список упавших профилей.

## Запуск одного профиля

Через общий wrapper:

```bash
./scripts/run-profile.sh smoke
./scripts/run-profile.sh discovery
./scripts/run-profile.sh baseline
./scripts/run-profile.sh load
./scripts/run-profile.sh stress
./scripts/run-profile.sh spike
./scripts/run-profile.sh endurance
```

Или напрямую:

```bash
./scripts/run-smoke.sh
./scripts/run-discovery.sh
./scripts/run-baseline.sh
./scripts/run-load.sh
./scripts/run-stress.sh
./scripts/run-spike.sh
./scripts/run-endurance.sh
```

Wrapper-скрипты печатают проектный баннер и запускают `k6` в quiet-режиме, чтобы стандартный баннер Grafana k6 не перебивал вывод.

## Профили

`smoke` — минимальная проверка доступности `/`.

`discovery` — аккуратная проверка типовых endpoint'ов:

```text
/
/ping
/healthz
/readyz
/version
/metrics
```

`baseline` — умеренная обычная нагрузка.

`load` — повышенная нагрузка.

`stress` — постепенное увеличение нагрузки для поиска предела устойчивости.

`spike` — резкий всплеск нагрузки.

`endurance` — длительная умеренная нагрузка.

`stress`, `spike` и `endurance` запускаются только после согласования окна тестирования с командой.

## Рекомендуемый порядок

1. Скопировать `.env.example` в `.env`.
2. Указать согласованный `TARGET_URL`.
3. Запустить `smoke`.
4. Запустить `discovery`.
5. Обновить `LOAD_ENDPOINTS` в `.env`.
6. Запустить `baseline`.
7. Запустить `load`.
8. По согласованию запустить `stress`, `spike`, `endurance`.

Команды:

```bash
./scripts/run-profile.sh smoke
./scripts/run-profile.sh discovery

# после discovery обновить LOAD_ENDPOINTS
./scripts/run-profile.sh baseline
./scripts/run-profile.sh load
```

High-impact профили:

```bash
./scripts/run-profile.sh stress
./scripts/run-profile.sh spike
./scripts/run-profile.sh endurance
```

`ALLOW_HIGH_IMPACT_TESTS` проверяется только в `run-suite.sh`. При прямом запуске через `run-profile.sh` ответственность за согласованное окно тестирования остается на операторе.

Для пакетного high-impact запуска укажи в `.env`:

```bash
TEST_PROFILES=smoke,baseline,load,stress,spike,endurance
ALLOW_HIGH_IMPACT_TESTS=true
```

Затем запусти:

```bash
./scripts/run-suite.sh
```

## Результаты

Скрипты сохраняют `k6` summary в `results/`.

Примеры:

```text
results/smoke-20260503-153000.json
results/baseline-20260503-154500.json
results/stress-20260503-160000.json
```


## Проверка репозитория

Локально можно проверить shell-скрипты без запуска нагрузки:

```bash
find scripts -type f -exec bash -n {} \;
```

На машине с установленным `k6` можно проверить, что сценарий собирается и стартует, коротким smoke-запуском:

```bash
# в .env временно поставь SMOKE_DURATION=5s
./scripts/run-profile.sh smoke
```

Значения для wrapper-скриптов берутся из `.env`. Если `.env` уже содержит `SMOKE_DURATION`, измени его там перед короткой проверкой.

## Частые проблемы

`k6: command not found` — `k6` не установлен или не попал в `PATH`. Проверь:

```bash
k6 version
which k6
```

`TARGET_URL is required` — в `.env` нет `TARGET_URL` или скрипт запущен не из корня репозитория.

`HTTP 404` в discovery не всегда ошибка. Discovery специально проверяет типовые endpoint'ы и нужен для выбора рабочих путей в `LOAD_ENDPOINTS`.

Пакетный запуск пропускает `stress`, `spike`, `endurance` — это ожидаемо, если `ALLOW_HIGH_IMPACT_TESTS` не равен `true`.

## Структура

```text
tests/
  smoke.js
  discovery.js
  baseline.js
  load.js
  stress.js
  spike.js
  endurance.js

config/
  endpoints.js
  thresholds.js

scripts/
  run-smoke.sh
  run-discovery.sh
  run-baseline.sh
  run-load.sh
  run-stress.sh
  run-spike.sh
  run-endurance.sh
  run-profile.sh
  run-suite.sh
  lib.sh

results/
.env.example
.gitignore
README.md
```

`docs/` может существовать локально как внутренняя документация проекта, но для запуска тестов он не требуется.

## Что передать blue team

После запуска передай:

- профиль теста;
- время запуска;
- `TARGET_URL`;
- длительность;
- количество VUs;
- использованные endpoint'ы;
- summary из терминала;
- JSON-файл из `results/`;
- краткие наблюдения по доступности сервиса.

Blue team дальше сопоставляет результаты с метриками, логами и состоянием инфраструктуры.
