# Amnezia Cluster API

FastAPI-сервис для управления Amnezia-сервером и peer-конфигурациями. API создает, показывает, обновляет и удаляет peers, отдает статистику сервера и может перезапускать настроенный Amnezia-контейнер.

> [!IMPORTANT]
> Проект не разворачивает Amnezia VPN/AmneziaWG на сервере с нуля. Перед запуском API сервер и выбранный протокол должны быть уже установлены и настроены администратором.

## Возможности

- Создание peer-конфигураций для `amnezia_vpn` и `amnezia_wg`.
- Список peers с фильтрами по типу приложения и online-статусу.
- Обновление peer с сохранением выделенного IP-адреса.
- Удаление peer из конфигурации протокола.
- Проверка состояния Amnezia-контейнера.
- Агрегированная статистика трафика.
- Перезапуск Amnezia-контейнера.
- Защита API-ключом через заголовок `X-API-Key`.
- Загрузка протоколов из `src/management/protocols.yaml`.

## Требования

- Python 3.13
- uv
- Docker и Docker Compose для контейнерного запуска
- Настроенный Amnezia-сервер
- Доступ к `/opt/amnezia` на сервере
- Доступ к Docker socket для управления контейнером
- UFW на production-сервере при публикации nginx-профиля

## Быстрый старт

Установите зависимости:

```bash
uv sync
```

Создайте локальный файл окружения:

```bash
cp .env.example .env
```

Заполните обязательные настройки:

```env
DEVELOPMENT=true
SERVER_PUBLIC_HOST=your-server-ip-or-domain
SERVER_DISPLAY_NAME=My AmneziaWG Server
```

В `.env.example` значение `DEVELOPMENT=false` оставлено безопасным по умолчанию. Включайте `DEVELOPMENT=true` только для локального запуска, когда нужны `/docs`, `/redoc` или `/openapi.json`.

Запустите API локально:

```bash
uv run uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

При `DEVELOPMENT=true` документация доступна по адресам:

- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`
- `http://localhost:8000/openapi.json`

## Настройка окружения

Сервис читает настройки из `.env`.

| Переменная | Обязательна | Значение по умолчанию | Описание |
| --- | --- | --- | --- |
| `DEVELOPMENT` | да | - | Включает OpenAPI/Swagger/Redoc в режиме разработки. |
| `SERVER_PUBLIC_HOST` | да | - | Публичный IP или домен сервера для peer-конфигураций. |
| `SERVER_DISPLAY_NAME` | нет | `AmneziaWG Server` | Имя сервера в конфигурациях для Amnezia VPN. |
| `API_KEY` | да | - | Ключ для защищенных маршрутов. Если не задан, приложение завершит запуск с ошибкой. |
| `API_ALLOWED_HOSTS` | нет | `SERVER_PUBLIC_HOST` | Разрешенные значения Host в production через запятую, например `api.example.com,198.51.100.10`. |
| `API_ENFORCE_HTTPS` | нет | `false` | Включает редирект HTTP на HTTPS на уровне FastAPI. Используйте только когда перед приложением корректно настроен TLS/proxy. |
| `CENTRAL_API_URL` | нет | `None` | URL центрального API для синхронизации. В production должен использовать `https`. |
| `CENTRAL_API_KEY` | нет | `None` | Отдельный ключ центрального API для синхронизации. Не используйте локальный `API_KEY`. |
| `CENTRAL_API_ALLOWED_HOSTS` | нет | `None` | Разрешенные хосты центрального API через запятую, например `central-api.example.com`. Обязательно при включенной синхронизации. |
| `SYNC_INTERVAL_SECONDS` | нет | `60` | Интервал фоновой синхронизации. |
| `PROTOCOL_CONFIG_PATH` | нет | `src/management/protocols.yaml` | Путь к конфигурации протоколов. |
| `PERSISTENT_KEEPALIVE_SECONDS` | нет | `25` | Значение keepalive для peer-конфигураций. |
| `PEER_ONLINE_THRESHOLD_SECONDS` | нет | `180` | Порог определения online-статуса peer. |
| `NGINX_SERVER_NAME` | нет | `localhost` | Домен или IP, который nginx принимает в `server_name`. |
| `NGINX_CERTS_PATH` | нет | `./nginx/certs` | Каталог с `fullchain.pem` и `privkey.pem` для TLS. |
| `NGINX_CLIENT_MAX_BODY_SIZE` | нет | `1m` | Лимит размера HTTP-запроса на nginx. |
| `NGINX_RATE_LIMIT_RATE` | нет | `60r/m` | nginx rate limit на один клиентский IP. |
| `NGINX_RATE_LIMIT_BURST` | нет | `20` | Допустимый кратковременный burst для nginx rate limit. |

Для production можно начать с отдельного шаблона:

```bash
cp .env.production.example .env
```

Перед запуском production-профиля оставьте `DEVELOPMENT=false`, задайте `SERVER_PUBLIC_HOST`, `API_ALLOWED_HOSTS`, `NGINX_SERVER_NAME` и положите TLS-сертификаты в `NGINX_CERTS_PATH`. При `DEVELOPMENT=false` маршруты `/docs`, `/redoc` и `/openapi.json` не публикуются приложением.

Production-профиль nginx должен публиковаться только после настройки UFW. Разрешайте `80/tcp` и `443/tcp` только с доверенных административных IP/CIDR и проверяйте правила с внешнего адреса, которого нет в allowlist.

Не коммитьте реальные `.env` файлы, API-ключи, серверные учетные данные и сгенерированные peer-секреты.

## API

Публичный маршрут:

| Метод | Путь | Описание |
| --- | --- | --- |
| `GET` | `/health` | Health check. Не требует API-ключ. |

Защищенные маршруты требуют заголовок:

```http
X-API-Key: <your-api-key>
```

### Peers

| Метод | Путь | Описание |
| --- | --- | --- |
| `POST` | `/peers/` | Создать peer. |
| `GET` | `/peers/` | Получить список peers. Поддерживает query-параметры `app_type` и `online_only`. |
| `PATCH` | `/peers/` | Пересоздать peer с новым типом приложения, сохранив IP. |
| `DELETE` | `/peers/` | Удалить peer по публичному ключу. |

Поддерживаемые значения `app_type`:

- `amnezia_vpn`
- `amnezia_wg`

Пример создания peer:

```bash
curl -X POST http://localhost:8000/peers/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"app_type":"amnezia_vpn"}'
```

Пример списка только online peers:

```bash
curl "http://localhost:8000/peers/?online_only=true" \
  -H "X-API-Key: $API_KEY"
```

### Server

| Метод | Путь | Описание |
| --- | --- | --- |
| `GET` | `/server/status` | Статус контейнера, порт, интерфейс и протокол. |
| `GET` | `/server/traffic` | Суммарный трафик и количество peers. |
| `POST` | `/server/restart` | Перезапуск настроенного Amnezia-контейнера. |

## Docker

Сборка и запуск API для локальной разработки:

```bash
docker compose up --build
```

API публикуется только на `127.0.0.1:${API_PORT:-8000}`. Для production-запуска через nginx используйте `.env.production.example` как основу, положите TLS-сертификаты в `NGINX_CERTS_PATH` с именами `fullchain.pem` и `privkey.pem`, задайте `DEVELOPMENT=false`, `SERVER_PUBLIC_HOST`, `API_ALLOWED_HOSTS` и `NGINX_SERVER_NAME`, затем запустите:

```bash
docker compose --profile nginx up --build
```

nginx слушает `80` и `443`, перенаправляет HTTP на HTTPS, проксирует запросы к API и передает исходный `Host`, который дополнительно проверяется приложением в production.

Перед запуском nginx-профиля настройте UFW на хосте. Замените `203.0.113.10/32` на реальные IP/CIDR администраторов и сохраните отдельное правило для SSH, чтобы не потерять доступ к серверу:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow from 203.0.113.10/32 to any port 80 proto tcp
sudo ufw allow from 203.0.113.10/32 to any port 443 proto tcp
sudo ufw enable
sudo ufw status verbose
```

Docker может публиковать порты через собственные iptables-правила, поэтому обычного вывода `ufw status` недостаточно. После запуска `docker compose --profile nginx up --build` проверьте доступ к `80` и `443` с адреса вне allowlist; если доступ открыт, подключите UFW к цепочке `DOCKER-USER` или примените эквивалентные `ufw route`-правила для Docker-forwarded traffic до production-запуска.

nginx также ограничивает частоту запросов на один клиентский IP через `NGINX_RATE_LIMIT_RATE` и `NGINX_RATE_LIMIT_BURST`.

API-контейнер запускается не от root. Пользователь приложения и группа доступа к Docker socket задаются в `src/Dockerfile`; файлы и каталоги, которые контейнер должен менять через bind mount, должны быть доступны этому UID/GID. `API_KEY` обязателен: задайте его в `.env` или через механизм секретов перед запуском.

Просмотр логов:

```bash
docker compose logs -f api
```

`docker-compose.yml` монтирует:

- `/var/run/docker.sock:/var/run/docker.sock`
- `/opt/amnezia:/opt/amnezia:rw`
- `${NGINX_CERTS_PATH:-./nginx/certs}:/etc/nginx/certs:ro` при профиле `nginx`

Доступ к Docker socket и запись в `/opt/amnezia` являются привилегированными операциями. Проверяйте такие изменения особенно внимательно.

## Разработка

Структура проекта:

```text
src/
  main.py                         создание FastAPI-приложения и подключение роутеров
  api/v1/                         роутеры, схемы, middleware и CRUD helpers
  services/                       бизнес-логика и интеграции с протоколами
  management/                     настройки, логирование, безопасность и protocols.yaml
tests/
  functional/                     функциональные тесты API
  services/                       unit-тесты сервисов и протоколов
```

Основная проверка:

```bash
make test
```

Полезные команды:

```bash
uv run pytest
uv run mypy
make functional-test
make smoke
```

`make smoke` проверяет импорт приложения, наличие маршрута `/health` и сборку Docker-образа.

## Протоколы

Протоколы описаны в `src/management/protocols.yaml`. Сейчас включен `amneziawg2`:

```text
src.services.protocols.amneziawg2.amneziawg2_service.AmneziaWG2Service
```

Конфигурация протокола задает имя контейнера, интерфейс, путь к конфигам, подсеть, DNS-серверы и параметры AmneziaWG.

## Проверка перед PR

Перед передачей изменений по возможности выполните:

```bash
make test
```

Для изменений в запуске, маршрутизации, Dockerfile или зависимостях дополнительно выполните:

```bash
make smoke
```
