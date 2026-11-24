МИНИМАЛЬНЫЙ ПРОТОТИП: КОЛЛЕКТИВНЫЕ ПРЕДПОЧТЕНИЯ / CONCORDIA

Отчёт: reports/experiment_report.pdf и reports/experiment_report.html.
Результаты без LLM: artifacts/runs/offline_v1/summary.csv.
Каждый JSON запуска содержит конфигурацию, профили, сеть, наблюдения,
точные промпты, ответы, время вызовов, траектории и состояния агентов.
Заглушка следует численному правилу. Это технические эксперименты,
а не результаты моделирования поведения людей с помощью LLM.

УСТАНОВКА НА ДРУГОМ КОМПЬЮТЕРЕ
Нужен Python 3.12+. В PowerShell, из корня проекта:
  python -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -r requirements.txt
Полный снимок окружения: artifacts/setup/requirements-lock.txt.
Для точного повторения окружения можно установить этот lock-файл.

ПОВТОРЕНИЕ БЕЗ КЛЮЧА
  .\.venv\Scripts\python.exe -m unittest discover -s tests -v
  .\.venv\Scripts\python.exe -m src.experiment smoke --output artifacts/runs/new_smoke.json
  .\.venv\Scripts\python.exe -m src.experiment suite --output artifacts/runs/offline_v2
Пути вывода должны быть новыми: прежние результаты не перезаписываются.
  .\.venv\Scripts\python.exe scripts/build_report.py
Команда отчёта использует результаты первой сохранённой серии offline_v1.

ПОДКЛЮЧЕНИЕ LLM ПОЗЖЕ
1. Скопировать .env.example в .env в корне проекта:
     Copy-Item .env.example .env
2. Открыть .env локально и заполнить:
     LLM_API_KEY=реальный_ключ
     LLM_BASE_URL=https://адрес_провайдера/v1
     LLM_MODEL=точное_имя_модели_у_провайдера
   Ключ не вставлять в отчёт или чат. .env исключён из Git.
3. Запустить один раунд (шесть запросов):
     .\.venv\Scripts\python.exe -m src.experiment smoke --backend live --max-calls 6 --output artifacts/runs/live_smoke_01.json
4. После успешного smoke: четыре раунда, до 24 запросов:
     .\.venv\Scripts\python.exe -m src.experiment run --backend live --condition combined --max-calls 24 --output artifacts/runs/live_combined_11.json
5. Для контрольных условий заменить combined на control, news_only,
   peers_only; --seed 11/22/33/44/55. Для проверки памяти: combined_memory4.
   Каждый раз выбирать отдельный файл результатов.

Адаптер ожидает OpenAI-совместимый POST /chat/completions.
Если провайдер требует max_completion_tokens, поменять LLM_TOKEN_FIELD.
Если temperature не поддерживается, поставить LLM_SEND_TEMPERATURE=false.
Responses API, OAuth Codex и потоковая генерация не реализованы.
При ошибке запуск останавливается и сохраняет частичный журнал; автоматических
повторов нет. Лимит числа запросов не является лимитом денежной стоимости.
Число реальных токенов сохраняется только если его вернёт провайдер.
При сетевой блокировке запускать из своего терминала с разрешённым доступом.

src/experiment.py — среда, агенты, память, расписание, серии, CLI.
src/models.py — заглушка и адаптер LLM, загрузка .env, журналы вызовов.
src/policy.py — численный контроль, валидация ответа и метрики.
tests/ — содержательные проверки изоляции, состояния и контракта.
scripts/probe.py — уже выполненные измерения роста контекста.
artifacts/setup/ — журнал проверок, версии и замечания об установке.

Статус на 21.11.2026: LLM-ключ по просьбе пользователя не использовался.
GPT-Luna через Codex не испытывалась. Успех реального API не заявляется.
