# nis-sieve

Проект команды 12 НИС «Распределённые системы 2»: независимые реализации
SIEVE, LRU и ARC в общем симуляторе кэша, сравнение доли промахов и
служебных операций на открытых трассах.

- [Назначенное задание P05](https://distsys.ru/osukhoroslov/nis2/src/branch/main/project-tasks/p05-sieve.md).
- Участники: Смирнов Глеб, Смирнягин Артём, Хмура Иван.
- ARC — третья политика; окончательное распределение следующих задач команда
  подтверждает перед сдачей.

## Окружение и проверка КТ1

Нужны Docker Engine и доступ к сети при первой сборке. Из корня репозитория:

```sh
docker build -t nis-sieve:dev .
docker run --rm --network none \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=/workspace,readonly" \
  nis-sieve:dev python3 tests/check_environment.py
```

Ожидаемый итог: `ALL CHECKS PASSED`. Проверка компилирует маленькую программу
через Meson, запускает авторский эталон на известных входах, собирает и
тестирует прототип ARC, проверяет чтение CSV и согласованность аналитического
журнала служебных операций. Она работает
без сети, создаёт промежуточные файлы только во временном каталоге контейнера.

В образе: GCC 16.2.0, Meson 1.12.1, Ninja, Python 3, CMake и зависимости
libCacheSim. Авторский артефакт закреплён на
`0861f8261c37b8286a70449a1defb5a4749c72d2` и находится в `/opt/sieve-reference`.
Команда `cachesim` доступна в `PATH`. Из собственных политик пока есть только
[прототип ARC](prototypes/arc).

Для работы с будущим кодом и записью файлов в репозиторий:

```sh
docker run --rm -it --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=/workspace" nis-sieve:dev
```

Проверка на настоящем трейсе скачивает `meta_reag` (334 МБ, нужна сеть), берёт
первые 5 млн запросов и сравнивает прототип ARC с эталоном. Нужно около 1,5 ГБ
на диске и 1 ГБ памяти:

```sh
docker run --rm --memory 1g --memory-swap 1g --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=/workspace" \
  nis-sieve:dev bash tests/check_real_trace.sh
```

## Материалы

- [Описание проекта](nis/project.md).
- [План эксперимента](nis/experiment-plan.md).
- [Отчёт КТ1, риски и ответственность участников](nis/checkpoints/01.md).
- [Прототип ARC и его тест](prototypes/arc).
- [Проверочный сценарий](tests/check_environment.py), [проверка настоящего трейса](tests/check_real_trace.sh)
  и [маленькие входы](tests/data).
- [Сохранённые результаты проверок](nis/checkpoints/01-results).
