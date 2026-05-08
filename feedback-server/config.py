# feedback-server/config.py
"""
🏫 Feedback Server — Конфигурация приложения (ПОЛНОСТЬЮ РАБОЧАЯ)
✅ Абсолютные пути для SQLite на Windows
✅ Настройки сессий для HTTP-разработки (без HTTPS)
✅ CSRF настройки совместимые с Flask-WTF
✅ Поддержка окружений: development, production
✅ ✅ ✅ DevelopmentConfig: SESSION_COOKIE_SAMESITE = None для локальной отладки
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

# ============================================================================
# 🎯 АБСОЛЮТНЫЕ ПУТИ
# ============================================================================
BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / 'instance'
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# 🗄️ БАЗА ДАННЫХ — АБСОЛЮТНЫЙ ПУТЬ (критично для Windows + SQLAlchemy)
# ============================================================================
# Формат: sqlite:///Полный/Путь/К/Файлу.db
# - Используем прямые слеши / даже на Windows
# - Путь должен быть абсолютным для надёжной работы

DEFAULT_DB_PATH = (INSTANCE_DIR / 'feedback.db').resolve()
# Нормализуем путь: заменяем \ на / для SQLAlchemy
DEFAULT_DB_URL = f'sqlite:///{str(DEFAULT_DB_PATH).replace(chr(92), "/")}'

# Берём из .env или используем дефолтный абсолютный путь
DATABASE_URL = os.environ.get('DATABASE_URL') or DEFAULT_DB_URL


class Config:
    """Базовая конфигурация для всех окружений"""
    
    # ========================================================================
    # 🔐 БЕЗОПАСНОСТЬ
    # ========================================================================
    # Секретный ключ для сессий, CSRF, подписи куки
    # Должен быть минимум 32 символа, сгенерирован криптографически
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-in-production-min-32-chars')
    
    # Соль для хеширования паролей (если используется)
    SECURITY_PASSWORD_SALT = os.environ.get('SECURITY_PASSWORD_SALT') or 'dev-salt-change-me'
    
    # ========================================================================
    # 🗄️ БАЗА ДАННЫХ
    # ========================================================================
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # ✅ Настройки для SQLite на Windows
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,           # Проверка соединения перед использованием
        'pool_recycle': 3600,            # Пересоздавать соединения каждый час
        'connect_args': {
            'timeout': 60,               # Ждать 60 сек если файл заблокирован
            'check_same_thread': False,  # ✅ Разрешить доступ из разных потоков (Flask)
        },
    }
    
    # ========================================================================
    # 🔑 СЕССИИ — базовые настройки (переопределяются в подклассах)
    # ========================================================================
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_REFRESH_EACH_REQUEST = True
    
    # ========================================================================
    # 🔐 CSRF ЗАЩИТА (Flask-WTF) — базовые настройки
    # ========================================================================
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    WTF_CSRF_SSL_STRICT = False
    
    # ========================================================================
    # 🔑 API-КЛЮЧИ
    # ========================================================================
    API_MASTER_KEY = os.environ.get('API_MASTER_KEY')
    
    # ========================================================================
    # 🌐 ВЕБХУКИ
    # ========================================================================
    WEBHOOK_TIMEOUT = int(os.environ.get('WEBHOOK_TIMEOUT', '30'))
    WEBHOOK_RETRY_COUNT = int(os.environ.get('WEBHOOK_RETRY_COUNT', '3'))
    
    # ========================================================================
    # 📊 ПАГИНАЦИЯ
    # ========================================================================
    ITEMS_PER_PAGE = 50
    
    # ========================================================================
    # 🔧 РЕЖИМ РАБОТЫ
    # ========================================================================
    DEBUG = os.environ.get('FLASK_ENV', 'production') == 'development'
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'DEBUG' if DEBUG else 'INFO').upper()
    
    # ========================================================================
    # 🔐 АДМИН-ПАНЕЛЬ
    # ========================================================================
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')
    ADMIN_SESSION_LIFETIME = timedelta(hours=8)
    ADMIN_DEBUG = DEBUG


class DevelopmentConfig(Config):
    """
    🔧 Настройки для локальной разработки — МАКСИМАЛЬНАЯ СОВМЕСТИМОСТЬ
    
    ✅ Ключевые отличия от базовой конфигурации:
    - SESSION_COOKIE_SAMESITE = None (отключает блокировку куки для локалки)
    - Более длительные сессии для отладки
    - Подробное логирование
    """
    DEBUG = True
    SQLALCHEMY_ECHO = True  # Выводить все SQL-запросы в консоль
    LOG_LEVEL = 'DEBUG'
    
    # 🔐 СЕССИИ — критично для CSRF в локальной разработке:
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)  # 24 часа для отладки
    SESSION_REFRESH_EACH_REQUEST = True
    
    # ✅ КУКИ для локальной разработки (127.0.0.1 / 192.168.x.x):
    SESSION_COOKIE_SECURE = False           # ✅ Разрешить по HTTP (не только HTTPS)
    SESSION_COOKIE_HTTPONLY = True          # ✅ Запретить доступ из JavaScript
    SESSION_COOKIE_SAMESITE = None          # ✅ ОТКЛЮЧИТЬ SameSite для локалки!
    SESSION_COOKIE_DOMAIN = None            # ✅ Текущий хост (не ограничивать)
    SESSION_COOKIE_PATH = '/'               # ✅ Доступно для всего сайта
    
    # ✅ CSRF для разработки (мягкие настройки):
    WTF_CSRF_ENABLED = True                 # ✅ Включено, но с мягкими проверками
    WTF_CSRF_SSL_STRICT = False             # ✅ Разрешить без HTTPS
    WTF_CSRF_TIME_LIMIT = None              # ✅ Токены не истекают
    WTF_CSRF_CHECK_DEFAULT = True           # ✅ Проверять по умолчанию
    
    # ✅ Для отладки: показывать больше информации о загрузке шаблонов
    EXPLAIN_TEMPLATE_LOADING = True


class ProductionConfig(Config):
    """
    🔐 Настройки для продакшена — СТРОГАЯ БЕЗОПАСНОСТЬ
    
    ⚠️ Обязательно задайте в .env для продакшена:
    - SECRET_KEY (сложный, 64+ символа, сгенерированный)
    - ADMIN_PASSWORD (очень сложный пароль)
    - DATABASE_URL (PostgreSQL вместо SQLite)
    """
    DEBUG = False
    SQLALCHEMY_ECHO = False
    LOG_LEVEL = 'WARNING'
    ADMIN_DEBUG = False
    
    # 🔐 Строгие настройки сессий для продакшена:
    SESSION_COOKIE_SECURE = True            # ✅ Только через HTTPS
    SESSION_COOKIE_HTTPONLY = True          # ✅ Запретить JS доступ
    SESSION_COOKIE_SAMESITE = 'Strict'      # ✅ Максимальная защита от CSRF
    SESSION_COOKIE_PATH = '/'
    
    # 🔐 Строгие CSRF настройки:
    WTF_CSRF_SSL_STRICT = True              # ✅ Требовать HTTPS для CSRF
    WTF_CSRF_TIME_LIMIT = 3600              # ✅ Токены истекают через 1 час
    
    # ✅ Дополнительные защиты для продакшена
    # (раскомментируйте при необходимости):
    # SESSION_COOKIE_SECURE = True
    # WTF_CSRF_SSL_STRICT = True


# ============================================================================
# 📦 РЕЕСТР КОНФИГУРАЦИЙ
# ============================================================================
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,  # По умолчанию — development для удобства
}


# ============================================================================
# 🛠️ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================
def get_config(config_name=None):
    """
    Получение класса конфигурации по имени
    
    Args:
        config_name: 'development', 'production' или None для default
    
    Returns:
        class: Класс конфигурации
    """
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')
    return config.get(config_name, config['default'])