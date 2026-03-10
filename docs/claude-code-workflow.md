# Claude Code Workflow — Expense Tracker Bot

Практический гайд: как использовать Claude Code для разработки проекта от scaffold до деплоя.

---

## 1. Установка Claude Code

```bash
# Требуется Node.js ≥ 18
npm install -g @anthropic-ai/claude-code

# Проверка
claude --version

# Авторизация (используй существующий Claude Pro/Max аккаунт)
claude
# → откроется браузер для OAuth
```

Claude Code работает как CLI-агент в терминале. Он может читать/писать файлы, запускать команды, видеть ошибки и исправлять их в цикле.

---

## 2. Подготовка проекта

### 2.1 Создай репозиторий

```bash
mkdir expense-bot && cd expense-bot
git init
```

### 2.2 Положи архитектуру в проект

Скачай `expense-bot-architecture.html` из нашего чата и положи в корень. Claude Code прочитает его как контекст.

```bash
mkdir docs
mv expense-bot-architecture.html docs/
```

### 2.3 Создай CLAUDE.md

Это ключевой файл — Claude Code читает его при каждом старте сессии. Он задаёт правила, контекст и стиль работы.

```bash
cat > CLAUDE.md << 'EOF'
# Expense Tracker Telegram Bot

## Project
Multi-user Telegram bot for expense tracking.
Voice/text input → Gemini Flash (audio→JSON) → Google Sheets.
Hosting: Google Cloud Functions. Full architecture: docs/expense-bot-architecture.html

## Stack
- Python 3.12, asyncio
- python-telegram-bot (async)
- Google Gemini 2.0 Flash (google-genai SDK)
- Google Sheets API (gspread)
- Google Drive API (googleapiclient)
- Google Cloud Functions (2nd gen)
- Pydantic for data models

## Structure
expense-bot/
├── main.py              # Cloud Function entry point
├── handlers/            # Telegram message handlers
├── services/            # Business logic (gemini, sheets, user_registry, currency)
├── models/              # Pydantic models
├── tests/               # pytest
├── requirements.txt
└── .env.yaml

## Coding Rules
- Type hints on all functions
- Async: all I/O operations use async/await
- Pydantic: for all data models and validation
- Tests: pytest + pytest-asyncio, test real logic, avoid unnecessary mocks
- Docstrings: concise, in English
- Error handling: try/except with logging, graceful degradation
- Env vars: via os.environ, never hardcode values

## Currency Model
- base_currency and default_currency are per-user settings
- ISO 4217 validation on registration
- amount_base = amount converted to user's base currency
EOF
```

---

## 3. Scaffold проекта — первая сессия

Запусти Claude Code и дай ему архитектуру:

```bash
claude
```

### Промпт для scaffold:

```
Read docs/expense-bot-architecture.html — it contains the full project architecture.

Scaffold the entire project:

1. requirements.txt with all dependencies
2. models/expense.py — Pydantic models (Expense, User, UserSettings)
3. models/category.py — categories and subcategories
4. services/gemini.py — Gemini Flash client (audio→JSON, text→JSON)
5. services/sheets.py — Google Sheets client (CRUD operations)
6. services/user_registry.py — user registration, Spreadsheet creation, ISO 4217 currency validation
7. services/currency.py — ExchangeRate API client with rate caching
8. handlers/voice.py — voice message handler
9. handlers/text.py — text message handler
10. handlers/commands.py — /start, /email, /settings, /today, /week, /month, /last, /undo, /budget, /export
11. handlers/callbacks.py — inline button callback handler
12. main.py — Cloud Function entry point
13. .env.yaml.example — environment variables template

Every file must be fully functional with type hints, docstrings,
and proper error handling. Follow the rules in CLAUDE.md.
```

Claude Code прочитает архитектуру, создаст все файлы, и ты сможешь ревьюить каждый.

---

## 4. Итеративная разработка — ежедневный workflow

### 4.1 Plan Mode — для сложных задач

```bash
# Запусти в Plan Mode — Claude думает, но не пишет код
claude --permission-mode plan
```

```
I need to implement the full onboarding flow:
/start → currency selection (inline buttons) → Spreadsheet creation → registration.
Create a detailed implementation plan and list which files need to be modified.
```

Claude создаст план. Ты ревьюишь, корректируешь, затем переключаешься в обычный режим (Shift+Tab) и говоришь "execute the plan".

### 4.2 Обычный режим — для конкретных задач

```bash
claude
```

Примеры промптов для разных задач:

```
# Implementing a specific service
Implement services/gemini.py. It should:
- Accept OGG audio bytes and return an Expense model
- Use response_schema for guaranteed JSON output
- Inject user.default_currency into the system instruction
- Handle API errors gracefully
Write tests in tests/test_gemini.py and run them.

# Debugging
Run main.py locally, send a test webhook request,
show me what happens. Fix any errors.

# Refactoring
There's a lot of duplication in handlers/ when fetching user from registry.
Extract this into a decorator or middleware. Show the diff.
```

### 4.3 Полезные команды во время сессии

```
/cost          — сколько потрачено за сессию
/clear         — очистить контекст (при смене задачи)
/compact       — сжать длинный разговор, сохранив контекст
Shift+Tab      — переключение Normal → Auto-Accept → Plan Mode
Ctrl+C         — прервать текущее действие
```

---

## 5. Тестирование и дебаг

Claude Code умеет запускать код и видеть ошибки — используй это:

```
Write integration tests for user_registry:
- Creating a user with valid currencies
- Creating a user with an invalid currency (should fail)
- Fetching an existing user from cache
- Transfer ownership via /email command

Use pytest with mocks for Drive API and Sheets API.
Run the tests and fix everything that fails.
```

Claude напишет тесты, запустит `pytest`, увидит failures, исправит код, запустит снова — всё автоматически.

---

## 6. Деплой через Claude Code

```
Set up deployment to Google Cloud:
1. Create GCP project expense-tracker-bot via gcloud
2. Enable APIs: Sheets, Drive, Cloud Functions, Gemini
3. Create a Service Account with the required permissions
4. Deploy the Cloud Function from the current directory
5. Set up the Telegram webhook to point to the function URL
6. Verify the bot responds to /start
```

Claude Code выполнит gcloud-команды последовательно, покажет результат каждого шага.

---

## 7. Cursor + Claude Code — как совмещать

| Задача | Инструмент |
|--------|-----------|
| Написать новый модуль целиком | Claude Code |
| Быстрая правка в одном файле | Cursor |
| Настроить инфраструктуру / деплой | Claude Code |
| Навигация по коду, чтение | Cursor |
| Написать и запустить тесты | Claude Code |
| Автокомплит при написании кода | Cursor |
| Рефакторинг нескольких файлов | Claude Code |
| Code review перед коммитом | Claude Code |

Оба работают с одним репозиторием. Claude Code — через терминал (или встроен в Cursor как extension). Cursor — через IDE.

### Claude Code как extension в Cursor

Claude Code можно установить прямо внутрь Cursor как расширение. Откроется панель сбоку — по сути терминал Claude Code прямо в IDE. Так не нужно переключаться между окнами.

---

## 8. Рекомендуемый порядок разработки

```
Фаза 1: Scaffold + Models         (Claude Code, ~30 мин)
  → models/, requirements.txt, структура

Фаза 2: Core Services             (Claude Code, ~1-2 часа)
  → gemini.py, sheets.py, currency.py, user_registry.py
  → тесты для каждого сервиса

Фаза 3: Handlers + Bot Logic      (Cursor + Claude Code)
  → handlers/, main.py
  → локальное тестирование

Фаза 4: GCP Setup + Deploy        (Claude Code)
  → gcloud конфигурация, деплой, webhook

Фаза 5: E2E Testing               (вручную + Claude Code)
  → реальные голосовые в Telegram
  → проверка Sheets записей

Фаза 6: Polish                    (Cursor)
  → UX сообщений бота, edge cases, error messages
```

---

## 9. Tips

**Для Claude Code:**
- Начинай сессию с чёткой задачи, не размытых просьб
- Используй /clear при переключении между задачами
- Если Claude Code спрашивает разрешение на каждое действие — `claude --dangerously-skip-permissions` (для dev окружения)
- Очередь сообщений: можно писать следующий промпт пока Claude работает над текущим

**Для CLAUDE.md:**
- Держи его коротким и конкретным
- Обновляй по мере развития проекта
- Не дублируй всю документацию — ссылайся на файлы

**Общее:**
- Git commit после каждой завершённой фичи
- Не давай Claude Code менять больше 3-4 файлов за раз — сложнее ревьюить
