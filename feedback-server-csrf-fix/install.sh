#!/usr/bin/env bash
# ============================================================================
# 🚀 Feedback Server Docker Installer (HTTPS + Let's Encrypt)
# 🔐 БЕЗ СЕКРЕТОВ В КОДЕ — безопасно для публичного репозитория
# Требует: root, docker, docker compose, curl, openssl, git
# ============================================================================
set -euo pipefail

# Цвета для вывода
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[✓]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
log_error()   { echo -e "${RED}[✗]${NC} $1"; }

# ============================================================================
# ⚙️ НАСТРОЙКИ (можно переопределить через переменные окружения)
# ============================================================================
APP_NAME="feedback-server"
APP_DIR="${APP_DIR:-/opt/${APP_NAME}}"
CERT_DIR="${APP_DIR}/certs"
ENV_FILE="${APP_DIR}/.env"
COMPOSE_FILE="${APP_DIR}/docker-compose.yml"
NGINX_CONF="${APP_DIR}/nginx.conf"
SCRIPTS_DIR="${APP_DIR}/scripts"

# Репозиторий с исходным кодом приложения
APP_REPO_URL="${APP_REPO_URL:-https://github.com/lukomsky85/server-up360.git}"
APP_REPO_BRANCH="${APP_REPO_BRANCH:-main}"

# ============================================================================
# 🔍 ПРОВЕРКА ТРЕБОВАНИЙ
# ============================================================================
check_prereqs() {
    log_info "Проверка системных требований..."
    [[ $EUID -eq 0 ]] || { log_error "Запустите от root: sudo $0"; exit 1; }
    command -v docker &>/dev/null || { log_error "Docker не установлен"; exit 1; }
    docker compose version &>/dev/null || { log_error "Docker Compose v2 не установлен"; exit 1; }
    command -v curl &>/dev/null || { log_error "curl не установлен"; exit 1; }
    command -v openssl &>/dev/null || { log_error "openssl не установлен"; exit 1; }
    command -v git &>/dev/null || { log_error "git не установлен"; exit 1; }
    log_success "Все требования выполнены"
}

# ============================================================================
# 📝 ВВОД ДАННЫХ ОТ ПОЛЬЗОВАТЕЛЯ
# ============================================================================
prompt_inputs() {
    log_info "Введите конфигурационные данные:"
    
    read -rp "🌐 Доменное имя (например: feedback.example.com): " DOMAIN
    [[ -n "$DOMAIN" ]] || { log_error "Домен обязателен"; exit 1; }
    
    read -rp "📧 Email для уведомлений Let's Encrypt: " EMAIL
    [[ "$EMAIL" =~ ^[^@]+@[^@]+\.[^@]+$ ]] || { log_error "Некорректный email"; exit 1; }
    
    read -rp "🔌 Порт HTTPS (по умолчанию: 443): " HTTPS_PORT
    HTTPS_PORT="${HTTPS_PORT:-443}"
    
    echo ""
    log_info "Источник исходного кода приложения:"
    echo "  1) Клонировать из Git репозитория: ${APP_REPO_URL}#${APP_REPO_BRANCH}"
    echo "  2) Указать локальный путь к проекту"
    read -rp "Ваш выбор [1/2]: " source_mode
    source_mode="${source_mode:-1}"
    
    if [[ "$source_mode" == "2" ]]; then
        read -rp "📂 Укажите абсолютный путь к проекту: " LOCAL_SRC_PATH
        [[ -d "$LOCAL_SRC_PATH" ]] || { log_error "Директория не найдена: $LOCAL_SRC_PATH"; exit 1; }
        [[ -f "$LOCAL_SRC_PATH/Dockerfile" ]] || { log_error "В указанной директории нет Dockerfile"; exit 1; }
    else
        # Для приватных репозиториев можно передать токен или настроить SSH заранее
        if [[ -n "${GITHUB_TOKEN:-}" ]]; then
            log_info "Используется GitHub Token для доступа к приватному репозиторию"
            APP_REPO_URL="https://${GITHUB_TOKEN}@github.com/${APP_REPO_URL#https://github.com/}"
        fi
    fi
    
    echo ""
    log_info "Режим генерации секретов:"
    echo "  1) Автоматически сгенерировать безопасные секреты (рекомендуется)"
    echo "  2) Ввести секреты вручную"
    read -rp "Ваш выбор [1/2]: " secret_mode
    secret_mode="${secret_mode:-1}"
    
    if [[ "$secret_mode" == "2" ]]; then
        log_info "Введите секреты вручную (или нажмите Enter для автогенерации):"
        read -rp "🔑 SECRET_KEY (мин. 32 символа): " USER_SECRET_KEY
        read -rp "🔑 API_MASTER_KEY (мин. 32 символа): " USER_API_KEY
        read -rp "🔑 ADMIN_PASSWORD: " USER_ADMIN_PASS
        read -rp "🔑 POSTGRES_PASSWORD: " USER_DB_PASS
        read -rp "🔑 WEBHOOK_SECRET: " USER_WEBHOOK_SECRET
    fi
}

# ============================================================================
# 🔐 ГЕНЕРАЦИЯ СЕКРЕТОВ
# ============================================================================
generate_secrets() {
    log_info "Генерация криптографических секретов..."
    
    SECRET_KEY="${USER_SECRET_KEY:-$(openssl rand -hex 32)}"
    API_MASTER_KEY="${USER_API_KEY:-$(openssl rand -hex 32)}"
    ADMIN_PASSWORD="${USER_ADMIN_PASS:-$(openssl rand -base64 18 | tr -dc 'A-Za-z0-9!@#%^&*' | head -c 20)}"
    POSTGRES_PASSWORD="${USER_DB_PASS:-$(openssl rand -hex 24)}"
    WEBHOOK_SECRET="${USER_WEBHOOK_SECRET:-$(openssl rand -hex 24)}"
    
    [[ ${#SECRET_KEY} -ge 32 ]] || { log_error "SECRET_KEY должен быть минимум 32 символа"; exit 1; }
    [[ ${#API_MASTER_KEY} -ge 32 ]] || { log_error "API_MASTER_KEY должен быть минимум 32 символа"; exit 1; }
    
    log_success "Секреты сгенерированы/приняты"
}

# ============================================================================
# 📁 ПОДГОТОВКА ДИРЕКТОРИЙ
# ============================================================================
setup_directories() {
    log_info "Подготовка директорий: ${APP_DIR}"
    mkdir -p "${APP_DIR}"/{certs/www,logs,instance,backups,scripts,src}
    chmod 700 "${APP_DIR}/certs" "${APP_DIR}/backups"
    log_success "Директории созданы"
}

# ============================================================================
# 📥 ПОЛУЧЕНИЕ ИСХОДНОГО КОДА
# ============================================================================
setup_source() {
    log_info "Подготовка исходного кода приложения..."
    local target_dir="${APP_DIR}/src"
    
    if [[ "$source_mode" == "2" ]]; then
        log_info "Копирование из локальной директории: ${LOCAL_SRC_PATH}"
        rsync -a --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' "${LOCAL_SRC_PATH}/" "${target_dir}/"
    else
        if [[ -d "${target_dir}/.git" ]]; then
            log_info "Репозиторий уже клонирован, обновляем..."
            cd "${target_dir}"
            git fetch origin "${APP_REPO_BRANCH}" 2>/dev/null || true
            git checkout -f "${APP_REPO_BRANCH}"
            git reset --hard "origin/${APP_REPO_BRANCH}"
        else
            log_info "Клонирование: ${APP_REPO_URL}#${APP_REPO_BRANCH}"
            # Очищаем директорию если там мусор
            rm -rf "${target_dir:?}/"*
            git clone --branch "${APP_REPO_BRANCH}" --depth 1 "${APP_REPO_URL}" "${target_dir}"
        fi
    fi
    
    # Критическая проверка
    if [[ ! -f "${target_dir}/Dockerfile" ]]; then
        log_error "❌ В исходном коде не найден Dockerfile!"
        log_error "Убедитесь, что репозиторий содержит Dockerfile в корне проекта."
        exit 1
    fi
    
    log_success "Исходный код подготовлен: ${target_dir}"
}

# ============================================================================
# ⚙️ ГЕНЕРАЦИЯ КОНФИГУРАЦИОННЫХ ФАЙЛОВ
# ============================================================================
generate_config_files() {
    log_info "Генерация конфигурационных файлов..."
    
    # 🔹 .env
    cat > "${ENV_FILE}" <<EOF
# ============================================================================
# 🏫 Feedback Server — Production Configuration
# 🔐 Сгенерировано установщиком $(date -Iseconds)
# ============================================================================
FLASK_ENV=production
LOG_LEVEL=INFO

SECRET_KEY=${SECRET_KEY}
API_MASTER_KEY=${API_MASTER_KEY}

POSTGRES_USER=feedback
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=feedback_db
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_SSL_MODE=prefer

ADMIN_USERNAME=admin
ADMIN_PASSWORD=${ADMIN_PASSWORD}

SESSION_LIFETIME=8
SESSION_COOKIE_SECURE=True
SESSION_COOKIE_SAMESITE=Lax
WTF_CSRF_SSL_STRICT=True

DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=30

WEBHOOK_TIMEOUT=30
WEBHOOK_RETRY_COUNT=3
REMOTE_FEEDBACK_WEBHOOK_SECRET=${WEBHOOK_SECRET}
ITEMS_PER_PAGE=50

DOMAIN=${DOMAIN}
HTTPS_PORT=${HTTPS_PORT}
EOF
    chmod 600 "${ENV_FILE}"
    log_success "Создан: .env (права 600)"
    
    # 🔹 docker-compose.yml — ИСПРАВЛЕННЫЙ ФРАГМЕНТ
    cat > "${COMPOSE_FILE}" <<EOF
services:
  postgres:
    image: postgres:15-alpine
    container_name: feedback-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: \${POSTGRES_USER}
      POSTGRES_PASSWORD: \${POSTGRES_PASSWORD}
      POSTGRES_DB: \${POSTGRES_DB}
      PGDATA: /var/lib/postgresql/data/pgdata
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U \${POSTGRES_USER} -d \${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    networks: [feedback-net]

  feedback-server:
    build: 
      context: ./src
      dockerfile: Dockerfile
    container_name: feedback-server
    restart: unless-stopped
    depends_on: {postgres: {condition: service_healthy}}
    env_file: [.env]
    environment:
      - POSTGRES_HOST=postgres
      - POSTGRES_PORT=5432
      - FLASK_ENV=production
      - SECRET_KEY=\${SECRET_KEY}
      - API_MASTER_KEY=\${API_MASTER_KEY}
      - SESSION_COOKIE_SECURE=True
      - WTF_CSRF_SSL_STRICT=True
    volumes:
      - ./logs:/app/logs
      - ./instance:/app/instance
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5001/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    networks: [feedback-net]

  nginx:
    image: nginx:alpine
    container_name: feedback-nginx
    restart: unless-stopped
    depends_on: [feedback-server]
    ports: ["80:80", "\${HTTPS_PORT:-443}:443"]
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./certs:/etc/letsencrypt:ro
      - ./certs/www:/var/www/certbot
    networks: [feedback-net]

volumes:
  postgres_data:
    driver: local
    name: \${APP_NAME:-feedback-server}_postgres_data

networks:
  feedback-net:
    driver: bridge
    name: \${APP_NAME:-feedback-server}_network
EOF
    log_success "Создан: docker-compose.yml"
    
    # 🔹 nginx.conf
    cat > "${NGINX_CONF}" <<EOF
events { worker_connections 1024; }
http {
    upstream flask_app { server feedback-server:5001; }

    server {
        listen 80;
        server_name ${DOMAIN};
        
        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
            default_type "text/plain";
        }
        
        location / { return 301 https://\$host\$request_uri; }
    }

    server {
        listen 443 ssl http2;
        server_name ${DOMAIN};

        ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
        ssl_prefer_server_ciphers on;
        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout 10m;

        location / {
            proxy_pass http://flask_app;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
            proxy_connect_timeout 60s;
            proxy_send_timeout 60s;
            proxy_read_timeout 60s;
        }

        location /api/v1/health {
            access_log off;
            proxy_pass http://flask_app/api/v1/health;
        }
    }
}
EOF
    log_success "Создан: nginx.conf"
}

# ============================================================================
# 🔑 ВЫПУСК СЕРТИФИКАТОВ
# ============================================================================
issue_certificates() {
    log_info "Запуск временного Nginx для ACME challenge..."
    docker compose -f "${COMPOSE_FILE}" up -d nginx
    
    log_info "Запрос сертификата у Let's Encrypt для ${DOMAIN}..."
    docker run --rm \
      -v "${CERT_DIR}:/etc/letsencrypt" \
      -v "${CERT_DIR}/www:/var/www/certbot" \
      certbot/certbot certonly --webroot \
      --webroot-path=/var/www/certbot \
      --email "${EMAIL}" --agree-tos --no-eff-email \
      -d "${DOMAIN}"
    
    if [[ -f "${CERT_DIR}/live/${DOMAIN}/fullchain.pem" ]]; then
        log_success "SSL-сертификат успешно выпущен!"
    else
        log_error "Не удалось получить сертификат"
        docker compose -f "${COMPOSE_FILE}" logs nginx
        exit 1
    fi
}

# ============================================================================
# 🚀 ЗАПУСК СТЕКА
# ============================================================================
start_stack() {
    log_info "Запуск полного стека сервисов..."
    docker compose -f "${COMPOSE_FILE}" down 2>/dev/null || true
    docker compose -f "${COMPOSE_FILE}" up -d --build
    
    log_info "Ожидание инициализации (до 60 сек)..."
    for i in {1..20}; do
        if curl -sfk "https://localhost:${HTTPS_PORT:-443}/api/v1/health" &>/dev/null; then
            log_success "Сервисы готовы и отвечают!"
            return 0
        fi
        sleep 3
    done
    log_warn "⚠️  Сервисы могут ещё запускаться. Проверьте логи:"
    log_warn "   docker compose -f ${COMPOSE_FILE} logs -f"
}

# ============================================================================
# ⏱️ АВТОПРОДЛЕНИЕ СЕРТИФИКАТОВ
# ============================================================================
setup_cron() {
    log_info "Настройка автопродления SSL..."
    local cron_cmd="0 3 * * * docker run --rm -v ${CERT_DIR}:/etc/letsencrypt certbot/certbot renew --quiet --deploy-hook 'docker compose -f ${COMPOSE_FILE} restart nginx' >/dev/null 2>&1"
    
    if ! crontab -l 2>/dev/null | grep -q "certbot renew.*${DOMAIN}"; then
        (crontab -l 2>/dev/null; echo "${cron_cmd}") | crontab -
        log_success "Cron настроен: продление ежедневно в 03:00"
    else
        log_info "Cron уже настроен"
    fi
}

# ============================================================================
# 📋 ФИНАЛЬНЫЙ ОТЧЁТ
# ============================================================================
print_report() {
    echo -e "\n${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║${NC}  🎉 ${APP_NAME} успешно развёрнут с HTTPS!             ${GREEN}║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}\n"
    
    echo -e "${BLUE}🌐 HTTPS Endpoint:${NC}  https://${DOMAIN}"
    echo -e "${BLUE}🔐 Admin Panel:${NC}     https://${DOMAIN}/admin/login"
    echo -e "${BLUE}🔌 API Health:${NC}      https://${DOMAIN}/api/v1/health\n"
    
    echo -e "${YELLOW}🔑 Учётные данные администратора (СОХРАНИТЕ!):${NC}"
    echo "   Username: admin"
    echo "   Password: ${ADMIN_PASSWORD}"
    echo ""
    echo -e "${BLUE}📦 Управление:${NC}"
    echo "   cd ${APP_DIR}"
    echo "   docker compose ps              # Статус"
    echo "   docker compose logs -f         # Логи"
    echo "   docker compose restart         # Перезапуск"
    echo "   docker compose down            # Остановка"
    echo ""
    echo -e "${RED}⚠️  ВАЖНО:${NC}"
    echo "   • Файл .env содержит секреты — права 600, не коммитьте в Git!"
    echo "   • Для продакшена откройте в фаерволе только порты 80 и 443"
    echo "   • Регулярно проверяйте бэкапы: ${APP_DIR}/backups/"
    echo ""
}

# ============================================================================
# 🏁 ОСНОВНАЯ ЛОГИКА
# ============================================================================
main() {
    echo ""
    echo -e "${GREEN}🚀 ${APP_NAME} Docker Installer (Public Repo Safe)${NC}"
    echo "   Версия: 1.0.0 | $(date '+%Y-%m-%d')"
    echo "   🔐 Все секреты генерируются локально — код безопасен для GitHub"
    echo ""
    
    check_prereqs
    prompt_inputs
    generate_secrets
    setup_directories
    setup_source               # ✅ КЛЮЧЕВОЕ: подготовка исходного кода
    generate_config_files
    issue_certificates
    start_stack
    setup_cron
    print_report
    
    log_success "Установка завершена успешно!"
}

main "$@"