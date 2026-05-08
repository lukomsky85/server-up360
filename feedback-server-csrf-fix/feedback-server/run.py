#!/usr/bin/env python3
"""
🏫 Feedback Server — Точка входа (Flask 3.x + CLI + reloader совместимый)
✅ Загружает .env ДО всего остального
✅ Использует абсолютный путь к БД (без chdir, чтобы не ломать reloader)
✅ ✅ ✅ Импорт create_app в глобальной области — для Flask CLI
✅ Корректно передаёт путь к скрипту для reloader
✅ Предоставляет диагностику при ошибках
"""

import os
import sys
from pathlib import Path

# ============================================================================
# 🔧 ШАГ 0: ИМПОРТЫ В ГЛОБАЛЬНОЙ ОБЛАСТИ (для CLI!)
# ============================================================================
# ✅ Импортируем create_app СРАЗУ, чтобы он был доступен глобально
from app import create_app

try:
    from dotenv import load_dotenv
except ImportError:
    pass


# ============================================================================
# 🔧 ШАГ 1: ЗАГРУЗКА .env ПЕРЕД ВСЕМ ОСТАЛЬНЫМ
# ============================================================================
PROJECT_ROOT = Path(__file__).resolve().parent

try:
    dotenv_path = PROJECT_ROOT / '.env'
    if dotenv_path.exists():
        load_dotenv(dotenv_path)
except ImportError:
    pass
except Exception:
    pass


# ============================================================================
# 🔧 ШАГ 2: НАСТРОЙКА ПУТЕЙ (без chdir, чтобы не ломать Flask reloader)
# ============================================================================
INSTANCE_DIR = PROJECT_ROOT / 'instance'
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

# Устанавливаем DATABASE_URL с абсолютным путём (если не задан в .env)
if not os.environ.get('DATABASE_URL'):
    DB_FILE = INSTANCE_DIR / 'feedback.db'
    abs_path = str(DB_FILE.resolve()).replace('\\', '/')
    os.environ['DATABASE_URL'] = f'sqlite:///{abs_path}'


# ============================================================================
# 🔧 ШАГ 3: ДИАГНОСТИКА (только для development, только в главном процессе)
# ============================================================================
def _print_startup_info():
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        return
    
    print(f'\n📁 PROJECT_ROOT: {PROJECT_ROOT}')
    print(f'📁 CWD: {Path.cwd()}')
    print(f'📁 INSTANCE_DIR: {INSTANCE_DIR}')
    print(f'✅ INSTANCE_DIR writable: {os.access(INSTANCE_DIR, os.W_OK)}')
    
    db_url = os.environ.get('DATABASE_URL', 'not set')
    print(f'🗄️ DATABASE_URL: {db_url[:100]}{"..." if len(db_url) > 100 else ""}')
    
    dotenv_loaded = dotenv_path.exists() and dotenv_path.is_file()
    print(f'📄 .env loaded: {dotenv_loaded}')
    
    try:
        import flask_wtf
        print(f'✅ flask-wtf: {flask_wtf.__version__}')
    except ImportError:
        print(f'❌ flask-wtf: NOT INSTALLED')
    
    secret_key = os.environ.get('SECRET_KEY', '')
    if not secret_key or len(secret_key) < 32:
        print(f'⚠️  SECRET_KEY: missing or too short')
    else:
        print(f'✅ SECRET_KEY: set ({len(secret_key)} chars)')
    print()


def _print_admin_debug():
    if os.environ.get('FLASK_ENV') != 'development':
        return
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        return
    
    print('🔐 DEBUG: Admin Panel Configuration')
    print('-' * 60)
    
    username = os.environ.get('ADMIN_USERNAME', '(not set)')
    password = os.environ.get('ADMIN_PASSWORD', '(not set)')
    
    print(f'   ADMIN_USERNAME: "{username}"')
    
    if password and password != '(not set)':
        if len(password) <= 8:
            pwd_display = '*' * len(password)
        else:
            pwd_display = f'{password[:4]}{"*" * (len(password) - 8)}{password[-4:]}'
        print(f'   ADMIN_PASSWORD: "{pwd_display}" (length: {len(password)})')
    else:
        print(f'   ADMIN_PASSWORD: "{password}"')
    
    print(f'   FLASK_ENV: "{os.environ.get("FLASK_ENV", "not set")}"')
    print(f'   ADMIN_DEBUG: "{os.environ.get("ADMIN_DEBUG", "not set")}"')
    print('-' * 60)
    print('⚠️  If login fails: check password matches exactly!\n')


# ============================================================================
# 🚀 ШАГ 4: СОЗДАНИЕ ПРИЛОЖЕНИЯ (ГЛОБАЛЬНО — для Flask CLI!)
# ============================================================================
# ✅ Теперь create_app импортирован выше, поэтому это работает:
app = create_app()


# ============================================================================
# 🚀 ШАГ 5: ЗАПУСК СЕРВЕРА (только при прямом запуске файла)
# ============================================================================
if __name__ == '__main__':
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        _print_startup_info()
        _print_admin_debug()
    
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        print(f'🚀 Starting Feedback API Server on http://{host}:{port}')
        print(f'🔧 Debug mode: {debug}')
        print(f'🔐 Admin: http://{host}:{port}/admin/login')
        print(f'🔌 API: http://{host}:{port}/api/v1/health\n')
    
    # ✅ Запускаем с правильным путем к скрипту для reloader
    app.run(
        host=host,
        port=port,
        debug=debug,
        use_reloader=debug,
        # ✅ Явно указываем файлы для отслеживания изменений
        extra_files=[
            str(PROJECT_ROOT / '.env'),
            str(PROJECT_ROOT / 'config.py'),
            str(PROJECT_ROOT / 'app.py'),
        ] if debug else None
    )