# Квитто: API платежей

Тестовое задание на Junior Python (FastAPI). Через этот сервис онлайн-школа принимает оплату курса: он отдаёт тарифы, создаёт платежи (можно с промокодом и в рассрочку) и узнаёт от банка, что статус платежа изменился.

Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2, SQLite. Тесты на pytest и httpx (через `TestClient`).

## Запуск

Нужен Python 3.11 или новее.

```bash
python3 -m venv .venv
source .venv/bin/activate        # на Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Сервис слушает http://localhost:8000, Swagger открывается на http://localhost:8000/docs. При старте создаются таблицы и три тарифа. База лежит в файле `kvitto.db` в папке, откуда запущен uvicorn.

Через Docker:

```bash
docker compose up --build
```

В этом случае база хранится в volume `kvitto-data` и переживает перезапуск контейнера.

Обе переменные окружения необязательные:

| Переменная | По умолчанию | Зачем |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./kvitto.db` | строка подключения SQLAlchemy |
| `WEBHOOK_SECRET` | не задан | секрет для подписи вебхука; пока он не задан, подпись не проверяется |

## Тесты

```bash
pytest
ruff check . && ruff format --check .
```

Те же команды запускает GitHub Actions на каждый push (`.github/workflows/ci.yml`).

## Примеры запросов

Список тарифов, цены в копейках:

```bash
curl http://localhost:8000/tariffs
# [{"id":1,"title":"basic","price":990000},{"id":2,"title":"standard","price":1990000},{"id":3,"title":"premium","price":2990000}]
```

Оплата картой с промокодом. Регистр кода не важен:

```bash
curl -X POST http://localhost:8000/payments \
  -H 'Content-Type: application/json' \
  -d '{"tariff_id": 2, "email": "student@example.com", "method": "card", "promo_code": "kvitto10"}'
# 201, "amount":1791000, "discount":199000
```

Рассрочка на 3 месяца с ключом идемпотентности. Если отправить запрос ещё раз, придёт тот же платёж с кодом 200, второй не создастся:

```bash
curl -i -X POST http://localhost:8000/payments \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: order-42' \
  -d '{"tariff_id": 2, "email": "student@example.com", "method": "installment", "installment_months": 3}'
# "amount":1990000, "schedule":[663334,663333,663333]
```

Платёж по id и список с фильтрами:

```bash
curl http://localhost:8000/payments/1
curl 'http://localhost:8000/payments?email=student@example.com&status=pending'
```

Вебхук банка. Первый запрос вернёт `{"result":"ok"}`, повтор вернёт 409 `{"error":"invalid_transition"}`, потому что succeeded → succeeded не входит в разрешённые переходы:

```bash
curl -X POST http://localhost:8000/webhooks/bank \
  -H 'Content-Type: application/json' \
  -d '{"payment_id": 1, "status": "succeeded"}'
```

Если задан `WEBHOOK_SECRET`, в заголовке `X-Signature` нужен hex HMAC-SHA256 от тела запроса. Без подписи или с неверной ответ 401:

```bash
BODY='{"payment_id": 1, "status": "refunded"}'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | awk '{print $NF}')
curl -X POST http://localhost:8000/webhooks/bank \
  -H 'Content-Type: application/json' \
  -H "X-Signature: $SIG" \
  -d "$BODY"
```

## Где задание молчит и что я выбрал

Скидка округляется до целой копейки, половина копейки вверх. У нынешних тарифов 10% делится нацело, так что на суммы это пока не влияет.

Неверные данные отсекаются на входе с 422 в стандартном формате FastAPI. Так сервис отвечает на несуществующий `tariff_id` (это поле тела, а не часть URL, поэтому не 404), на `installment_months` вместе с `card` или `sbp`, на пустой `Idempotency-Key` и на id, который не помещается в 64 бита (в пути, в теле или в `offset`). Лишнее поле в платёжном запросе молча игнорировать не хочется. С пустым ключом все такие запросы склеились бы в один платёж, и следующий покупатель получил бы чужой. А слишком большое число база всё равно не сохранит.

Пустой `promo_code` (`""` или пробелы) считается отсутствующим, неизвестный код даёт 422.

Тот же `Idempotency-Key` с другим телом вернёт первый платёж, тело не сравнивается. Stripe в такой ситуации отвечает ошибкой. Чтобы сделать так же, хватит хранить хеш тела рядом с ключом.

Повторный вебхук с тем же статусом получает 409: задание разрешает только три перехода. В живом сервисе я бы, скорее всего, отвечал на такой дубль 200, иначе банк будет его переотправлять. Статус меняется запросом `UPDATE ... WHERE status = <прочитанный статус>`, поэтому из двух одновременных вебхуков второй получит 409 и не затрёт первый.

Фильтр `GET /payments?email=` не учитывает регистр, `created_at` отдаётся в UTC.

## Структура

```
app/
  main.py       приложение, создание таблиц и тарифов при старте
  config.py     настройки из переменных окружения
  db.py         движок и сессия SQLAlchemy
  models.py     таблицы tariffs и payments
  schemas.py    Pydantic-схемы запросов и ответов
  enums.py      способы оплаты, статусы, разрешённые переходы
  pricing.py    скидка и график рассрочки, только целые копейки
  services.py   создание платежа и смена статуса
  routers/      эндпоинты
tests/
```

Из бонусов сделаны `docker compose up`, подпись вебхука, `GET /payments` с фильтрами, GitHub Actions и `AGENTS.md` с правилами для ассистента. Alembic не подключал: таблицы создаются через `create_all` при старте. Для тестового этого хватает, но схему без пересоздания базы не поменять.

Как я работал с ИИ, описано в [AI_LOG.md](AI_LOG.md).
