# nis-sieve

Проект команды 12 по НИС «Распределённые системы 2». Пишем свои SIEVE, LRU и ARC в общем симуляторе кэша и сравниваем их по доле промахов и служебным операциям на открытых трейсах.

[Задание P05](https://distsys.ru/osukhoroslov/nis2/src/branch/main/project-tasks/p05-sieve.md)

Участники: Смирнов Глеб, Смирнягин Артём, Хмура Иван.

## Что где лежит

- [nis/project.md](nis/project.md): что делаем и какие приняли упрощения
- [nis/experiment-plan.md](nis/experiment-plan.md): план эксперимента
- [nis/checkpoints/01.md](nis/checkpoints/01.md): отчёт по КТ1
- [nis/checkpoints/01-results](nis/checkpoints/01-results): сохранённые результаты проверок
- [prototypes/arc](prototypes/arc): прототип ARC и его тесты
- [tests](tests): сценарии проверок и маленькие входы

Симулятора и своих SIEVE и LRU пока нет.

## Запуск

Нужен Docker, при первой сборке ещё сеть. Команды запускаются из корня репозитория.

```sh
docker build -t nis-sieve:dev .
```

В образе GCC 16.2.0, Meson 1.12.1, Ninja, CMake, Python 3 и `cachesim` из артефакта статьи (коммит `0861f8261c37b8286a70449a1defb5a4749c72d2`). В `cachesim` мы добавили только вывод целых счётчиков запросов и промахов (строка `EXACT`), политики не меняли. Штатно он показывает долю с четырьмя знаками после запятой, для точной сверки этого мало.

Шелл для работы с кодом:

```sh
docker run --rm -it --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=/workspace" nis-sieve:dev
```

## Проверки

### Быстрая

Сеть не нужна. В конце печатает `ALL CHECKS PASSED`.

```sh
docker run --rm --network none --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=/workspace,readonly" \
  nis-sieve:dev python3 tests/check_environment.py
```

Проверяет версии и сборку через Meson, запускает `cachesim` на входах с известным ответом, собирает и тестирует прототип ARC, проверяет отказ на плохих входах и загрузку начала трейса.

### Настоящий трейс

Скачивает `meta_reag` (334 МБ), берёт первые 5 млн запросов и сравнивает прототип ARC с версией ARC из `cachesim`. При расхождении падает. Нужно около 1,5 ГБ на диске и 1 ГБ памяти.

```sh
docker run --rm --memory 1g --memory-swap 1g --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=/workspace" \
  nis-sieve:dev bash tests/check_real_trace.sh
```

### Три больших трейса

Первые 10 млн запросов `meta_reag`, `cluster10` и `wiki_2019t`, шесть размеров кэша: от 0,1% до 30% числа разных объектов в трейсе. Запускаем наш ARC и FIFO, LRU, SIEVE, ARC из `cachesim`: 90 запусков и 18 точных сверок ARC. Прогрева нет, основную серию это не заменяет.

При первом запуске нужна сеть. Скачивается только начало архивов, длина и SHA-256 проверяются. Входы лежат в `data/` и в git не попадают, это примерно 1 ГБ. Потом можно запускать с `--network none`. В конце печатает `ALL LARGE TRACE CHECKS PASSED: 18 exact ARC comparisons`.

```sh
docker run --rm --cpus 2 --memory 3g --memory-swap 3g --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=/workspace" \
  nis-sieve:dev python3 tests/check_large_traces.py
```

Результаты пишутся в [large-traces](nis/checkpoints/01-results/large-traces).

### Выбор KV-трейса

Основные KV-трейсы у нас `cluster50` и `cluster53`. Сначала был `cluster10`, но на нём почти все промахи это первые обращения к объектам, а их не избежать ни при какой политике, поэтому сравнивать там нечего. `cluster50` и `cluster53` это два самых маленьких архива, где политики различаются на всех проверенных размерах кэша. Сценарий сравнивает эти и другие KV-трейсы. Нужна сеть, файлы удаляются после анализа. Результаты пишутся в [kv-survey](nis/checkpoints/01-results/kv-survey).

```sh
docker run --rm --cpus 2 --memory 900m --memory-swap 900m --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=/workspace" \
  nis-sieve:dev python3 -u tests/survey_kv_traces.py
```

### Замеры основных трейсов

Читает начало четырёх основных трейсов и считает размеры объектов, записи с размером 0 и момент заполнения кэша. Нужна сеть, файлы не сохраняются. Результаты пишутся в [trace-stats](nis/checkpoints/01-results/trace-stats).

```sh
docker run --rm --cpus 2 --memory 1g --memory-swap 1g --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=/workspace" \
  nis-sieve:dev python3 -u tests/trace_stats.py
```

### Синтетические сценарии

Сеть не нужна. 12 профилей с фиксированным seed (сканирование, циклы, смена горячего набора и так далее) и 9 размеров кэша, всего 108 точных сверок ARC под ASan и UBSan. Результаты пишутся в [scenarios](nis/checkpoints/01-results/scenarios).

```sh
docker run --rm --network none --cpus 2 --memory 2g --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=/workspace" \
  nis-sieve:dev python3 tests/check_scenarios.py
```
