# FishIng Booking — turnkey версия (под ключ)

Готовое веб-приложение для онлайн-записи на рыбалку с шахматкой (клиент + админ), API и deploy-конфигурацией.

## Что сделано

### 1) Анализ текущего сайта `fishing.demom.ru`
Текущий сервис — это платформа рыболовной базы:
- лендинг + онлайн-запись,
- личный кабинет клиента,
- админ-управление бронями,
- магазин и заказы.

### 2) Закрытие болей
**Клиент**
- Быстрый выбор свободного времени на шахматке.
- Понятные статусы брони.
- Минимум шагов до создания заявки.

**Админ**
- Единый экран загрузки зон.
- Быстрый перенос/редактирование/удаление.
- Экспорт CSV и метрики дня.

### 3) ТЗ (MVP)
- Роли: клиент, админ.
- Сетка: зоны (вертикаль) × часы 06:00–23:00 (горизонталь).
- Сущности: `zones`, `bookings`.
- Проверки: телефон, время, длительность, запрет пересечений.
- Метрики: кол-во броней, загрузка, выручка, статусы.
- Экспорт: CSV за выбранную дату.

---

## Архитектура (реально deploy-ready)

- **Frontend:** `index.html` + `styles.css` + `app.js`
- **Backend:** FastAPI (`backend/main.py`) + SQLite (`data.db`)
- **Запуск в контейнере:** `Dockerfile` + `docker-compose.yml`

Приложение отдает API и UI из одного сервиса.

---

## API

- `GET /api/health`
- `GET /api/zones`
- `GET /api/bookings?date=YYYY-MM-DD`
- `POST /api/bookings`
- `PUT /api/bookings/{id}`
- `DELETE /api/bookings/{id}`
- `GET /api/metrics?date=YYYY-MM-DD`
- `GET /api/bookings/export?date=YYYY-MM-DD`

---

## Запуск

### Вариант A — локально (без Docker)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
Открыть: `http://localhost:8000`

### Вариант B — Docker Compose
```bash
docker compose up --build
```
Открыть: `http://localhost:8080`

---

## Что дальше до production
1. Авторизация (JWT) и разделение прав на backend.
2. Подключение PostgreSQL вместо SQLite.
3. Интеграция SMS/WhatsApp уведомлений.
4. Онлайн-оплата и фискализация.
5. Резервное копирование, мониторинг, аудит действий.
