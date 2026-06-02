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
| `API_IMAGE_TAG` | нет | `latest` | Тег Docker Hub образа для VPS-запуска через `docker-compose.yml`. |
| `SERVER_PUBLIC_HOST` | да | - | Публичный IP или домен сервера для peer-конфигураций. |
| `SERVER_DISPLAY_NAME` | нет | `AmneziaWG Server` | Имя сервера в конфигурациях для Amnezia VPN. |
| `API_KEY` | да | - | Ключ для защищенных маршрутов. Если не задан, приложение завершит запуск с ошибкой. |
| `API_ALLOWED_HOSTS` | нет | `SERVER_PUBLIC_HOST` | Разрешенные значения Host в production через запятую, например `api.example.com,198.51.100.10`. |
| `API_ENFORCE_HTTPS` | нет | `false` | Включает редирект HTTP на HTTPS на уровне FastAPI. Используйте только когда перед приложением корректно настроен TLS/proxy. |
| `DOCKER_SOCKET_GID` | нет | `0` | GID группы Docker socket на хосте для VPS-запуска готового образа. |
| `CENTRAL_API_URL` | нет | `None` | URL центрального API для синхронизации. В production должен использовать `https`. |
| `CENTRAL_API_KEY` | нет | `None` | Отдельный ключ центрального API для синхронизации. Не используйте локальный `API_KEY`. |
| `CENTRAL_API_ALLOWED_HOSTS` | нет | `None` | Разрешенные хосты центрального API через запятую, например `central-api.example.com`. Обязательно при включенной синхронизации. |
| `SYNC_INTERVAL_SECONDS` | нет | `60` | Интервал фоновой синхронизации. |
| `PROTOCOL_CONFIG_PATH` | нет | `src/management/protocols.yaml` | Путь к конфигурации протоколов. |
| `PERSISTENT_KEEPALIVE_SECONDS` | нет | `25` | Значение keepalive для peer-конфигураций. |
| `PEER_ONLINE_THRESHOLD_SECONDS` | нет | `180` | Порог определения online-статуса peer. |
| `NGINX_SERVER_NAME` | нет | `SERVER_PUBLIC_HOST`, затем `localhost` | Домен или IP, который nginx принимает в `server_name`. Нужен только если отличается от `SERVER_PUBLIC_HOST`. |
| `NGINX_CERTS_PATH` | нет | `./nginx/certs` | Каталог с `fullchain.pem` и `privkey.pem` для TLS. |
| `NGINX_SSL_CERTIFICATE` | нет | `/etc/nginx/certs/fullchain.pem` | Путь к TLS-сертификату внутри nginx-контейнера. Для certbot используйте `/etc/letsencrypt/live/<domain>/fullchain.pem`. |
| `NGINX_SSL_CERTIFICATE_KEY` | нет | `/etc/nginx/certs/privkey.pem` | Путь к TLS-ключу внутри nginx-контейнера. Для certbot используйте `/etc/letsencrypt/live/<domain>/privkey.pem`. |
| `NGINX_CLIENT_MAX_BODY_SIZE` | нет | `1m` | Лимит размера HTTP-запроса на nginx. |
| `NGINX_RATE_LIMIT_RATE` | нет | `60r/m` | nginx rate limit на один клиентский IP. |
| `NGINX_RATE_LIMIT_BURST` | нет | `20` | Допустимый кратковременный burst для nginx rate limit. |
| `CERTBOT_EMAIL` | нет | - | Email для регистрации Let's Encrypt аккаунта при выпуске сертификата через certbot. |
| `CERTBOT_DOMAIN` | нет | `NGINX_SERVER_NAME`, затем `SERVER_PUBLIC_HOST` | Домен, для которого certbot выпускает сертификат. Нужен только если отличается от nginx host. |
| `CERTBOT_LETSENCRYPT_PATH` | нет | `./nginx/letsencrypt` | Хостовый каталог для `/etc/letsencrypt` certbot. |
| `CERTBOT_WWW_PATH` | нет | `./nginx/certbot/www` | Webroot-каталог для HTTP-01 challenge. |

Для production можно начать с отдельного шаблона:

```bash
cp .env.production.example .env
```

Перед запуском production-профиля оставьте `DEVELOPMENT=false`, задайте `SERVER_PUBLIC_HOST` и положите TLS-сертификаты в `NGINX_CERTS_PATH`. `API_ALLOWED_HOSTS`, `NGINX_SERVER_NAME` и `CERTBOT_DOMAIN` нужны только если они отличаются от `SERVER_PUBLIC_HOST`. При `DEVELOPMENT=false` маршруты `/docs`, `/redoc` и `/openapi.json` не публикуются приложением.

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

## Установка на VPS из готового образа

Этот способ не собирает API на сервере. VPS берет compose-файл, nginx template и env-шаблон из репозитория, а API-контейнер скачивает из Docker Hub: `burdakovdv/amnezia-cluster-api:${API_IMAGE_TAG:-latest}`.

Перед началом убедитесь, что на VPS уже есть:

- установленный и настроенный Amnezia-сервер;
- Docker Engine и Docker Compose plugin;
- git;
- доступ к `/opt/amnezia`;
- доступ к `/var/run/docker.sock`;
- домен или публичный IP для `SERVER_PUBLIC_HOST`.

Проверить это можно прямо на VPS:

```bash
# Amnezia-контейнер уже установлен и запущен
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' | grep -Ei 'amnezia-awg'

# Docker Engine и Docker Compose plugin доступны
docker --version
docker compose version

# git установлен
git --version

# есть доступ к каталогу Amnezia
sudo test -d /opt/amnezia && sudo test -r /opt/amnezia && sudo test -w /opt/amnezia && echo "/opt/amnezia: ok"

# Docker socket существует и доступен для команд docker
test -S /var/run/docker.sock && docker ps >/dev/null && echo "docker.sock: ok"

# домен или IP для SERVER_PUBLIC_HOST резолвится и указывает на этот VPS
SERVER_PUBLIC_HOST=vpn-x.burdakov.su
getent hosts "$SERVER_PUBLIC_HOST"
curl -4 ifconfig.me
```

В последнем блоке замените `vpn-x.burdakov.su` на свой домен или публичный IP. IP из `getent hosts "$SERVER_PUBLIC_HOST"` должен совпадать с публичным IP VPS из `curl -4 ifconfig.me`. Если `docker ps` возвращает `permission denied`, выполняйте установку тем же пользователем, у которого есть доступ к Docker, или настройте доступ к Docker socket до запуска API.

Создайте runtime-каталог приложения и временно клонируйте репозиторий:

```bash
sudo rm -rf /opt/amnezia-cluster-api
sudo mkdir -p /opt/amnezia-cluster-api
sudo chown "$USER":"$USER" /opt/amnezia-cluster-api

AMNEZIA_CLUSTER_API_BRANCH=main
git clone --depth 1 --branch "$AMNEZIA_CLUSTER_API_BRANCH" https://github.com/akaUNik/amnezia-cluster-api.git /tmp/amnezia-cluster-api
```

Для установки из `develop` замените `AMNEZIA_CLUSTER_API_BRANCH=main` на `AMNEZIA_CLUSTER_API_BRANCH=develop`.

Скопируйте в runtime-каталог только файлы, нужные для запуска:

```bash
cd /opt/amnezia-cluster-api
mkdir -p nginx/templates
mkdir -p src/management

cp /tmp/amnezia-cluster-api/docker-compose.yml ./docker-compose.yml
cp /tmp/amnezia-cluster-api/.env.production.example ./.env.production.example
cp /tmp/amnezia-cluster-api/nginx/templates/default.conf.template ./nginx/templates/default.conf.template
cp /tmp/amnezia-cluster-api/src/management/protocols.yaml ./src/management/protocols.yaml
```

Создайте production `.env` из шаблона репозитория:

```bash
cp .env.production.example .env
```

Заполните в `.env` как минимум:

- `SERVER_PUBLIC_HOST`;
- `API_KEY`;
- `CERTBOT_EMAIL`;
- `NGINX_SSL_CERTIFICATE` и `NGINX_SSL_CERTIFICATE_KEY`, если используете certbot-сертификаты из `/etc/letsencrypt`;
- `DOCKER_SOCKET_GID`.

Сгенерировать `API_KEY` можно так:

```bash
openssl rand -hex 32
```

`DOCKER_SOCKET_GID` должен совпадать с GID группы, которой принадлежит Docker socket на VPS:

```bash
stat -c '%g' /var/run/docker.sock
```

Для certbot-сертификатов обычно нужны такие пути внутри `.env`:

```env
NGINX_SSL_CERTIFICATE=/etc/letsencrypt/live/api.example.com/fullchain.pem
NGINX_SSL_CERTIFICATE_KEY=/etc/letsencrypt/live/api.example.com/privkey.pem
```

В runtime-каталоге должны остаться только нужные для запуска файлы: `docker-compose.yml`, `.env`, `.env.production.example`, `nginx/templates/default.conf.template` и `src/management/protocols.yaml`.

Сначала скачайте API-образ и запустите только API:

```bash
docker compose pull api
docker compose up -d api
docker compose ps
```

Проверьте API с VPS:

1. Проверить health check:

```bash
curl http://127.0.0.1:8000/health
```

Загрузить `API_KEY` из `.env`:

```bash
set -a
. ./.env
set +a
```

2. Проверить статус сервера:

```bash
curl -sS http://127.0.0.1:8000/server/status \
  -H "X-API-Key: $API_KEY" | jq
```

3. Проверить общий трафик:

```bash
curl -sS http://127.0.0.1:8000/server/traffic \
  -H "X-API-Key: $API_KEY" | jq
```

4. Получить список peers:

```bash
curl -sS http://127.0.0.1:8000/peers/ \
  -H "X-API-Key: $API_KEY" | jq
```

Если сертификата еще нет, временно освободите порт `80` и выпустите первый сертификат через standalone challenge:

```bash
docker compose --profile certbot run --rm -p 80:80 --entrypoint /bin/sh certbot -c 'certbot certonly --standalone -d "$CERTBOT_DOMAIN" --email "$CERTBOT_EMAIL" --agree-tos --no-eff-email'
```

После выпуска сертификата запустите nginx:

```bash
docker compose --profile nginx up -d
docker compose ps
```

Теперь API доступен через nginx по `https://api.example.com`. Проверка:

```bash
curl https://api.example.com/health
```

Для продления сертификата, когда nginx уже запущен, используйте webroot challenge:

```bash
docker compose --profile certbot run --rm certbot
docker compose --profile nginx exec nginx nginx -s reload
```

Обновление конфигов из репозитория и последнего опубликованного образа:

```bash
AMNEZIA_CLUSTER_API_BRANCH=main
rm -rf /tmp/amnezia-cluster-api
git clone --depth 1 --branch "$AMNEZIA_CLUSTER_API_BRANCH" https://github.com/akaUNik/amnezia-cluster-api.git /tmp/amnezia-cluster-api

cd /opt/amnezia-cluster-api
mkdir -p src/management
cp /tmp/amnezia-cluster-api/docker-compose.yml ./docker-compose.yml
cp /tmp/amnezia-cluster-api/.env.production.example ./.env.production.example
cp /tmp/amnezia-cluster-api/nginx/templates/default.conf.template ./nginx/templates/default.conf.template
cp /tmp/amnezia-cluster-api/src/management/protocols.yaml ./src/management/protocols.yaml
rm -rf /tmp/amnezia-cluster-api

docker compose --profile nginx --profile certbot pull
docker compose --profile nginx up -d
docker image prune -f
```

Для более предсказуемого production-деплоя вместо `latest` можно закрепить тег образа в `.env`:

```env
API_IMAGE_TAG=sha-<commit>
```

Логи:

```bash
docker compose logs -f api nginx
```

## Docker: сборка из репозитория

Этот раздел нужен, если репозиторий склонирован локально или на сервере и образ собирается из исходников. Для VPS-запуска без сборки используйте раздел выше.

Сборка и запуск API для локальной разработки:

```bash
docker compose -f docker-compose.dev.yml up --build
```

Публикация API-образа в Docker Hub настроена через GitHub Actions workflow `Docker Image Publish`.

Для настройки публикации создайте Docker Hub access token:

1. Откройте Docker Hub: `Account settings` -> `Personal access tokens`.
2. Создайте токен с правами на push в репозиторий `burdakovdv/amnezia-cluster-api`.
3. Скопируйте токен один раз при создании.

Затем добавьте repository secrets в GitHub:

1. Откройте репозиторий в GitHub.
2. Перейдите в `Settings` -> `Secrets and variables` -> `Actions`.
3. Нажмите `New repository secret` и добавьте:

- `DOCKERHUB_USERNAME`: имя Docker Hub пользователя, например `burdakovdv`.
- `DOCKERHUB_TOKEN`: Docker Hub access token с правом push.

Workflow запускается при push в ветку `main` и публикует теги `latest` и `sha-<commit>`:

```bash
docker push burdakovdv/amnezia-cluster-api:latest
```

API публикуется только на `127.0.0.1:${API_PORT:-8000}`. Для production-запуска через nginx со сборкой из исходников используйте `.env.production.example` как основу, положите TLS-сертификаты в `NGINX_CERTS_PATH` с именами `fullchain.pem` и `privkey.pem`, задайте `DEVELOPMENT=false` и `SERVER_PUBLIC_HOST`, затем запустите:

```bash
docker compose -f docker-compose.dev.yml --profile nginx up --build
```

nginx слушает `80` и `443`, перенаправляет HTTP на HTTPS, проксирует запросы к API и передает исходный `Host`, который дополнительно проверяется приложением в production.

Для выпуска сертификата через certbot задайте `CERTBOT_EMAIL`. `CERTBOT_DOMAIN` по умолчанию берется из `NGINX_SERVER_NAME` или `SERVER_PUBLIC_HOST`. При первом выпуске, если nginx еще не может стартовать из-за отсутствующих TLS-файлов, временно освободите порт `80` и запустите certbot в standalone-режиме:

```bash
docker compose -f docker-compose.dev.yml --profile certbot run --rm -p 80:80 --entrypoint /bin/sh certbot -c 'certbot certonly --standalone -d "$CERTBOT_DOMAIN" --email "$CERTBOT_EMAIL" --agree-tos --no-eff-email'
```

Для HTTP-01 validation порт `80` должен быть доступен извне на время выпуска и продления сертификата. Если UFW ограничивает доступ к `80/tcp` только административными IP, временно откройте его для проверки домена и верните ограничения после успешного выпуска.

После выпуска сертификата переключите nginx на certbot-файлы:

```env
NGINX_SSL_CERTIFICATE=/etc/letsencrypt/live/api.example.com/fullchain.pem
NGINX_SSL_CERTIFICATE_KEY=/etc/letsencrypt/live/api.example.com/privkey.pem
```

Когда nginx уже запущен, certbot может использовать webroot challenge через общий каталог `${CERTBOT_WWW_PATH:-./nginx/certbot/www}`:

```bash
docker compose -f docker-compose.dev.yml --profile certbot run --rm certbot
```

Для продления сертификата:

```bash
docker compose -f docker-compose.dev.yml --profile certbot run --rm --entrypoint certbot certbot renew --webroot --webroot-path /var/www/certbot
docker compose -f docker-compose.dev.yml --profile nginx exec nginx nginx -s reload
```

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

Docker может публиковать порты через собственные iptables-правила, поэтому обычного вывода `ufw status` недостаточно. После запуска `docker compose -f docker-compose.dev.yml --profile nginx up --build` проверьте доступ к `80` и `443` с адреса вне allowlist; если доступ открыт, подключите UFW к цепочке `DOCKER-USER` или примените эквивалентные `ufw route`-правила для Docker-forwarded traffic до production-запуска.

nginx также ограничивает частоту запросов на один клиентский IP через `NGINX_RATE_LIMIT_RATE` и `NGINX_RATE_LIMIT_BURST`.

API-контейнер запускается не от root. Пользователь приложения и группа доступа к Docker socket задаются в `src/Dockerfile`; файлы и каталоги, которые контейнер должен менять через bind mount, должны быть доступны этому UID/GID. `API_KEY` обязателен: задайте его в `.env` или через механизм секретов перед запуском.

Просмотр логов:

```bash
docker compose -f docker-compose.dev.yml logs -f api
```

`docker-compose.dev.yml` монтирует:

- `/var/run/docker.sock:/var/run/docker.sock`
- `/opt/amnezia:/opt/amnezia:rw`
- `${NGINX_CERTS_PATH:-./nginx/certs}:/etc/nginx/certs:ro` при профиле `nginx`
- `${CERTBOT_LETSENCRYPT_PATH:-./nginx/letsencrypt}:/etc/letsencrypt` при профиле `certbot`, read-only в nginx
- `${CERTBOT_WWW_PATH:-./nginx/certbot/www}:/var/www/certbot` при профиле `certbot`, read-only в nginx

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
