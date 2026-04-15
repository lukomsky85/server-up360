"""
🏫 Feedback Server — Конфигурация приложения с PostgreSQL
✅ Поддержка различных окружений (development, production, testing)
✅ PostgreSQL для production, SQLite для разработки (опционально)
"""

import os
from pathlib import Path

# Базовые директории
BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = os.environ.get('INSTANCE_DIR', str(BASE_DIR / 'instance'))

# Создаем директорию instance, если её нет
Path(INSTANCE_DIR).mkdir(exist_ok=True)


class Config:
    """Базовый класс конфигурации"""
    
    # ========================================================================
    # 🔐 БЕЗОПАСНОСТЬ И CSRF
    # ========================================================================
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production-min-32-chars-long')
    
    # CSRF настройки
    WTF_CSRF_ENABLED = True
    WTF_CSRF_SECRET_KEY = os.environ.get('WTF_CSRF_SECRET_KEY', SECRET_KEY)
    WTF_CSRF_TIME_LIMIT = 3600
    
    # ========================================================================
    # 🗄️ БАЗА ДАННЫХ (PostgreSQL)
    # ========================================================================
    # Получаем параметры PostgreSQL из переменных окружения
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = os.environ.get('DB_PORT', '5432')
    DB_USER = os.environ.get('DB_USER', 'postgres')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', 'postgres')
    DB_NAME = os.environ.get('DB_NAME', 'feedback_db')
    
    # Формируем URI для PostgreSQL
    # Формат: postgresql://user:password@host:port/database
    SQLALCHEMY_DATABASE_URI = (
        f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    
    # Добавляем параметры для PostgreSQL
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': int(os.environ.get('DB_POOL_SIZE', 10)),
        'pool_recycle': int(os.environ.get('DB_POOL_RECYCLE', 3600)),
        'pool_pre_ping': True,  # Проверка соединения перед использованием
        'pool_timeout': 30,      # Таймаут получения соединения из пула
        'max_overflow': 20,      # Максимум дополнительных соединений
    }
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # ========================================================================
    # 🌐 FLASK НАСТРОЙКИ
    # ========================================================================
    FLASK_ENV = os.environ.get('FLASK_ENV', 'development')
    DEBUG = FLASK_ENV == 'development'
    TESTING = FLASK_ENV == 'testing'
    
    # ========================================================================
    # 📁 ЗАГРУЗКА ФАЙЛОВ
    # ========================================================================
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    UPLOAD_FOLDER = Path(INSTANCE_DIR) / 'uploads'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt'}
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    
    # ========================================================================
    # 🔑 API НАСТРОЙКИ
    # ========================================================================
    API_MASTER_KEY = os.environ.get('API_MASTER_KEY')
    API_RATE_LIMIT = int(os.environ.get('API_RATE_LIMIT', 100))
    
    # ========================================================================
    # 📧 EMAIL НАСТРОЙКИ
    # ========================================================================
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')
    
    # ========================================================================
    # 🍪 СЕССИИ И КУКИ
    # ========================================================================
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = FLASK_ENV == 'production'
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 86400  # 24 hours
    
    # ========================================================================
    # 🚀 ПРОИЗВОДИТЕЛЬНОСТЬ
    # ========================================================================
    JSON_SORT_KEYS = False
    JSONIFY_PRETTYPRINT_REGULAR = DEBUG
    SEND_FILE_MAX_AGE_DEFAULT = 31536000


class DevelopmentConfig(Config):
    """Конфигурация для разработки (PostgreSQL)"""
    DEBUG = True
    FLASK_ENV = 'development'
    
    # В разработке можно использовать SQLite для простоты
    # Или оставить PostgreSQL, раскомментировав нужную строку
    
    # Вариант 1: PostgreSQL для разработки (как в production)
    # Используем тестовую БД
    DB_NAME = os.environ.get('DB_NAME', 'feedback_dev')
    
    # Вариант 2: SQLite для быстрой разработки (закомментируйте PostgreSQL вариант)
    # SQLALCHEMY_DATABASE_URI = f'sqlite:///{Path(INSTANCE_DIR) / "feedback_dev.db"}'
    
    PROPAGATE_EXCEPTIONS = True
    PRESERVE_CONTEXT_ON_EXCEPTION = False
    LOG_LEVEL = 'DEBUG'
    WTF_CSRF_ENABLED = True


class TestingConfig(Config):
    """Конфигурация для тестирования"""
    TESTING = True
    DEBUG = True
    FLASK_ENV = 'testing'
    
    # Используем отдельную тестовую БД
    DB_NAME = os.environ.get('DB_NAME', 'feedback_test')
    
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    LOG_LEVEL = 'WARNING'


class ProductionConfig(Config):
    """Конфигурация для продакшена (PostgreSQL)"""
    DEBUG = False
    TESTING = False
    FLASK_ENV = 'production'
    
    # В продакшене проверяем наличие всех параметров БД
    required_vars = ['DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        raise ValueError(
            f"Missing required environment variables for production: {', '.join(missing_vars)}\n"
            "Please set: DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, and SECRET_KEY"
        )
    
    # Проверяем SECRET_KEY
    if not os.environ.get('SECRET_KEY') or len(os.environ.get('SECRET_KEY', '')) < 32:
        raise ValueError(
            "SECRET_KEY must be at least 32 characters long in production! "
            "Generate with: python -c 'import secrets; print(secrets.token_hex(32))'"
        )
    
    # Безопасные настройки для PostgreSQL
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': int(os.environ.get('DB_POOL_SIZE', 20)),
        'pool_recycle': int(os.environ.get('DB_POOL_RECYCLE', 3600)),
        'pool_pre_ping': True,
        'pool_timeout': 30,
        'max_overflow': 30,
    }
    
    # Безопасные настройки сессий
    SESSION_COOKIE_SECURE = True  # Только HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'


# Словарь конфигураций
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}
