# Web Load Tests

Репозиторий содержит `k6`-сценарии для авторизованного black-box HTTP load testing веб-сервера команды.

Тесты не зависят от backend/framework приложения, контейнера или Ansible. Проект работает только с внешним HTTP-интерфейсом согласованного target.

## Target

Целевой сервер задается через переменную окружения:

```bash
TARGET_URL=http://81.26.176.68:30080
```

В `.env` лучше указывать адрес без завершающего `/`, чтобы endpoint'ы корректно склеивались в тестах.

## Scope

Разрешенные сценарии:

- smoke testing;
- endpoint discovery;
- baseline load testing;
- load testing;
- controlled stress testing;
- controlled spike testing;
- endurance testing;
- сохранение локальных результатов `k6`.

Запрещено использовать проект для неавторизованных атак, обхода rate limit, сокрытия источника трафика, эксплуатации уязвимостей или тестирования сторонних систем.

## Требования

На Linux runner должны быть доступны:

- `git`;
- `bash`;
- `k6`.

Проверка установки `k6`:

```bash
k6 version
```

## Быстрый старт

```bash
git clone <repo-url>
cd web-load-tests

cp .env.example .env
```

Проверь настройки:

```bash
TARGET_URL=http://81.26.176.68:30080
REQUEST_TIMEOUT=5s
SLEEP_SECONDS=1
LOAD_ENDPOINTS=/
```

Дай права на запуск скриптов, если нужно:

```bash
chmod +x scripts/*.sh
```

## Конфигурация

Все основные параметры задаются через `.env` или переменные окружения.

Общие параметры:

```bash
TARGET_URL=http://81.26.176.68:30080
REQUEST_TIMEOUT=5s
SLEEP_SECONDS=1
LOAD_ENDPOINTS=/
```

`LOAD_ENDPOINTS` поддерживает несколько endpoint'ов через запятую:

```bash
LOAD_ENDPOINTS=/,/ping,/version
```

Перед добавлением endpoint'ов в нагрузочные профили сначала запусти discovery и оставь только реально доступные пути.

## Профили

`smoke` проверяет базовую доступность `/` с минимальной нагрузкой.

```bash
./scripts/run-smoke.sh
```

`discovery` аккуратно проверяет типовые endpoint'ы:

```text
/
/ping
/healthz
/readyz
/version
/metrics
```

Запуск:

```bash
./scripts/run-discovery.sh
```

`baseline` создает умеренную обычную нагрузку.

```bash
./scripts/run-baseline.sh
```

`load` создает повышенную нагрузку.

```bash
./scripts/run-load.sh
```

`stress` постепенно увеличивает нагрузку для поиска предела устойчивости.

```bash
./scripts/run-stress.sh
```

`spike` проверяет реакцию сервера на резкий всплеск нагрузки.

```bash
./scripts/run-spike.sh
```

`endurance` проверяет стабильность при длительной умеренной нагрузке.

```bash
./scripts/run-endurance.sh
```

`stress`, `spike` и `endurance` запускаются только после согласования окна тестирования с командой.

## Рекомендуемый порядок запуска

1. `./scripts/run-smoke.sh`
2. `./scripts/run-discovery.sh`
3. обновить `LOAD_ENDPOINTS` в `.env`
4. `./scripts/run-baseline.sh`
5. `./scripts/run-load.sh`
6. `./scripts/run-stress.sh`
7. `./scripts/run-spike.sh`
8. `./scripts/run-endurance.sh`

## Результаты

Скрипты сохраняют `k6` summary в папку `results/`.

Примеры файлов:

```text
results/smoke-20260503-153000.json
results/baseline-20260503-154500.json
results/stress-20260503-160000.json
```

Папка `results/` не коммитится в git.

## Структура проекта

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

После запуска тестов передай:

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
