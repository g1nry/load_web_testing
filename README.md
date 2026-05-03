# Web Load Tests

Репозиторий для авторизованных нагрузочных автотестов веб-сервера команды.

Target по умолчанию:

```text
http://81.26.176.68:30080/
```

## Назначение

Проект используется для black-box HTTP load testing:

- smoke test;
- endpoint discovery;
- baseline load;
- stress test;
- spike test;
- endurance test.

## Требования

- Linux host
- SSH access
- k6
- git

## Быстрый старт

```bash
git clone <repo-url>
cd web-load-tests
cp .env.example .env
```

Проверить `.env`:

```bash
TARGET_URL=http://81.26.176.68:30080
```

Запуск smoke test:

```bash
./scripts/run-smoke.sh
```

Запуск discovery:

```bash
./scripts/run-discovery.sh
```

Запуск baseline:

```bash
./scripts/run-baseline.sh
```

## Профили

### Smoke

Минимальная проверка доступности.

### Discovery

Проверка типовых endpoint'ов.

### Baseline

Умеренная нагрузка.

### Load

Повышенная нагрузка.

### Stress

Постепенное повышение нагрузки для поиска предела устойчивости.

### Spike

Резкий всплеск нагрузки.

### Endurance

Длительная умеренная нагрузка.

## Важно

Проект предназначен только для авторизованного тестирования согласованного веб-сервера команды.

Не использовать против сторонних систем.
