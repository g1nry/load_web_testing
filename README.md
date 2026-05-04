# Web Load Tests

`k6`-репозиторий для авторизованных black-box HTTP load tests веб-сервера команды.

Проект не требует знания backend/framework, не лезет в контейнеры и не зависит от Ansible. Все тесты работают только через внешний HTTP target, который задается локально перед запуском.

## Главное

- реальный `TARGET_URL` не хранится в репозитории;
- все параметры запуска задаются через `.env` или переменные окружения;
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

`LOAD_ENDPOINTS` поддерживает несколько путей через запятую:

```bash
LOAD_ENDPOINTS=/,/ping,/version
```

Перед добавлением endpoint'ов в нагрузочные профили сначала запусти discovery и оставь только реально доступные пути.

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

1. Запустить `smoke`.
2. Запустить `discovery`.
3. Обновить `LOAD_ENDPOINTS` в `.env`.
4. Запустить `baseline`.
5. Запустить `load`.
6. По согласованию запустить `stress`, `spike`, `endurance`.

## Результаты

Скрипты сохраняют `k6` summary в `results/`.

Примеры:

```text
results/smoke-20260503-153000.json
results/baseline-20260503-154500.json
results/stress-20260503-160000.json
```

Папка `results/` не коммитится.

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

docs/
  PROJECT_BRIEF.md
  AGENTS.md
  TESTING_SCOPE.md
  LOAD_TEST_PLAN.md

results/
.env.example
.gitignore
README.md
```

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
