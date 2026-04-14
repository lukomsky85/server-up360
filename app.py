# feedback-server/app.py
"""
🏫 Feedback Server — Factory-функция создания приложения (Flask 3.x)
✅ Инициализация расширений, регистрация блюпринтов, CLI команды
✅ Безопасные обработчики ошибок и контекст-процессоры
✅ ✅ ✅ CSRF-токен доступен в шаблонах через {{ csrf_token }}
✅ ✅ ✅ Flask 3.x совместимость + отладочные маршруты
✅ ✅ ✅ CSRF ОТКЛЮЧЁН ДЛЯ API ENDPOINT'ов (/api/v1/*) — только API-ключ требуется
✅ ✅ ✅ ✅ НАДЁЖНАЯ ИНИЦИАЛИЗАЦИЯ SECRET_KEY для работы сессий и CSRF
✅ ✅ ✅ ✅ ✅ ОТЛАДКА CSRF: перед каждым запросом логируем куки и сессии
"""

import os
import sys
import click
import logging
from pathlib import Path
from datetime import datetime, timezone

from flask import Flask, jsonify, request, redirect, url_for, flash, session, g

# ✅ Flask-WTF для CSRF защиты
from flask_wtf import CSRFProtect
from flask_wtf.csrf import generate_csrf

from flask_cors import CORS

from config import config, INSTANCE_DIR
from extensions import db, migrate
from models import APIKey, Feedback, WebhookLog, SystemSetting


# ============================================================================
# 🔧 НАСТРОЙКА ЛОГИРОВАНИЯ
# ============================================================================
logging.basicConfig(
    level=logging.DEBUG if os.environ.get('FLASK_ENV') == 'development' else logging.INFO,
    format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler(INSTANCE_DIR / 'app.log', encoding='utf-8', mode='a')
    ]
)
logger = logging.getLogger(__name__)


def create_app(config_name=None):
    """Factory-функция создания приложения"""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config[config_name])
    
    # ========================================================================
    # ✅ ✅ ✅ КРИТИЧЕСКИ ВАЖНО: Инициализация SECRET_KEY для CSRF
    # ========================================================================
    # Flask-WTF CSRF требует, чтобы app.secret_key был установлен
    # Даже если SECRET_KEY есть в config, Flask может не подставить его автоматически
    
    secret_key = app.config.get('SECRET_KEY')
    
    # Проверка длины ключа (минимум 32 символа для безопасности)
    if not secret_key or len(secret_key) < 32:
        logger.warning('⚠️ SECRET_KEY missing or too short! Generating temporary key...')
        # Генерируем временный ключ для разработки (в продакшене используйте .env!)
        import secrets
        secret_key = secrets.token_hex(32)
        app.config['SECRET_KEY'] = secret_key
    
    # ✅ Явно устанавливаем app.secret_key
    app.secret_key = secret_key
    logger.info(f'✅ app.secret_key initialized (length: {len(secret_key)})')
    
    # ========================================================================
    # ✅ ИНИЦИАЛИЗАЦИЯ РАСШИРЕНИЙ
    # ========================================================================
    db.init_app(app)
    migrate.init_app(app, db)
    
    # ✅ CSRF PROTECTION — создаём экземпляр для последующего exempt
    csrf = CSRFProtect(app)
    
    # ========================================================================
    # ✅ ✅ ✅ ОТЛАДКА CSRF: логируем куки и сессии перед каждым запросом
    # ========================================================================
    @app.before_request
    def debug_csrf_cookies():
        """
        Отладка CSRF и сессий (только в DEBUG режиме для админки)
        Показывает:
        - Какие куки отправляет браузер
        - Что есть в сессии на сервере
        - Есть ли CSRF-токен в сессии
        - Какой токен пришёл в форме (для POST)
        """
        if not app.debug:
            return
        
        if request.path.startswith('/admin'):
            # Логируем куки запроса
            cookies = dict(request.cookies)
            logger.debug(f'🍪 Request cookies: {cookies}')
            
            # Логируем ключи сессии
            session_keys = list(session.keys())
            logger.debug(f'🔑 Session keys: {session_keys}')
            
            # Проверяем наличие CSRF-токена в сессии
            csrf_in_session = '_csrf_token' in session
            logger.debug(f'🔐 _csrf_token in session: {csrf_in_session}')
            
            # Для POST-запросов: логируем токен из формы
            if request.method == 'POST':
                form_token = request.form.get('csrf_token', 'NOT SENT')
                if form_token != 'NOT SENT':
                    logger.debug(f'📝 Form CSRF token: {form_token[:20]}...')
                else:
                    logger.debug('📝 Form CSRF token: NOT SENT')
                
                # Если токены не совпадают — это причина ошибки
                if csrf_in_session and form_token != 'NOT SENT':
                    session_token = session.get('_csrf_token', '')
                    if session_token != form_token:
                        logger.warning(f'⚠️ CSRF token mismatch! Session: {session_token[:20]}... vs Form: {form_token[:20]}...')
    
    # ========================================================================
    # ✅ КОНТЕКСТ-ПРОЦЕССОР: делаем csrf_token доступным в шаблонах
    # ========================================================================
    @app.context_processor
    def inject_csrf_token():
        """
        Делает переменную csrf_token доступной во ВСЕХ шаблонах.
        Использование: <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
        """
        try:
            token = generate_csrf()
            if app.debug:
                logger.debug(f'✅ CSRF token generated: {token[:20]}...')
            return dict(csrf_token=token)  # ✅ Возвращаем САМ ТОКЕН (строку)
        except Exception as e:
            logger.error(f'❌ CSRF token error: {e}', exc_info=True)
            return dict(csrf_token='')
    
    # ========================================================================
    # ✅ БЕЗОПАСНЫЙ контекст-процессор для админ-панели
    # ========================================================================
    @app.context_processor
    def inject_admin_globals():
        """
        Добавляет статистику в шаблоны админки.
        ✅ Возвращает stats={'new': count} как ожидает шаблон.
        """
        def safe_new_count():
            """Безопасный подсчёт новых обращений"""
            try:
                # Проверяем, что есть активный request context
                if request:
                    return Feedback.query.filter_by(status='new').count()
            except Exception as e:
                logger.debug(f'Context processor stats error (ignored): {e}')
            return 0
        
        return dict(
            now=lambda: datetime.now(timezone.utc),
            # ✅ Возвращаем stats как dict с результатом (не функцию!)
            stats={'new': safe_new_count()},
        )
    
    # ========================================================================
    # ✅ ИНИЦИАЛИЗАЦИЯ БД — Flask 3.x способ
    # ========================================================================
    with app.app_context():
        try:
            db.create_all()
            logger.info('✅ Database tables created')
        except Exception as e:
            logger.error(f'⚠️ Database init warning: {e}')
    
    # ========================================================================
    # ✅ РЕГИСТРАЦИЯ БЛЮПРИНТОВ
    # ========================================================================
    
    # 🔹 Сначала импортируем blueprint'ы
    from routes.api import api_bp
    from routes.admin import admin_bp
    
    # 🔹 ✅ ОТКЛЮЧАЕМ CSRF ДЛЯ ВСЕХ API ENDPOINT'ов
    csrf.exempt(api_bp)
    logger.info('✅ CSRF protection disabled for /api/v1/* endpoints')
    
    # 🔹 Регистрируем blueprint'ы
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)
    
    # ========================================================================
    # 🔍 ОТЛАДОЧНЫЕ МАРШРУТЫ
    # ========================================================================
    
    @app.route('/ping')
    def ping():
        """Публичная проверка работоспособности"""
        return jsonify({
            'status': 'ok',
            'csrf_enabled': app.config.get('WTF_CSRF_ENABLED', True),
            'timestamp': datetime.now(timezone.utc).isoformat(),
        })
    
    @app.route('/debug-config')
    def debug_config_public():
        """Публичная отладка конфигурации"""
        return jsonify({
            'SECRET_KEY_set': bool(app.config.get('SECRET_KEY')),
            'SECRET_KEY_length': len(app.config.get('SECRET_KEY', '')),
            'WTF_CSRF_ENABLED': app.config.get('WTF_CSRF_ENABLED'),
            'DATABASE_URI': app.config.get('SQLALCHEMY_DATABASE_URI')[:100],
            'FLASK_ENV': os.environ.get('FLASK_ENV'),
        })
    
    # ========================================================================
    # ✅ CLI КОМАНДЫ
    # ========================================================================
    @app.cli.command('create-api-key')
    @click.argument('name')
    @click.option('--desc', help='Описание ключа')
    @click.option('--limit', type=int, help='Rate limit (запросов/мин)')
    def create_api_key(name, desc=None, limit=None):
        master_key = app.config.get('API_MASTER_KEY')
        if not master_key:
            click.echo('❌ API_MASTER_KEY not configured')
            return
        
        provided = click.prompt('Enter master key', hide_input=True)
        if provided != master_key:
            click.echo('❌ Invalid master key')
            return
        
        key = APIKey(
            key=APIKey.generate_key(),
            name=name,
            description=desc,
            rate_limit=limit or 100,
        )
        db.session.add(key)
        db.session.commit()
        
        click.echo(f'✅ API key created for "{name}"')
        click.echo(f'🔑 Key: {key.key}')
        click.echo('⚠️  Save this key securely!')
    
    @app.cli.command('sync-webhooks')
    def sync_webhooks():
        from services.webhooks import queue_pending_webhooks
        count = queue_pending_webhooks()
        click.echo(f'✅ Processed {count} pending webhooks')
    
    # ========================================================================
    # ✅ ОБРАБОТЧИКИ ОШИБОК
    # ========================================================================
    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith('/admin'):
            return redirect(url_for('admin.login', next=request.url))
        return jsonify({'error': 'Not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(e):
        logger.error(f'Internal error: {e}', exc_info=True)
        if request.path.startswith('/admin'):
            flash('Внутренняя ошибка сервера', 'danger')
            return redirect(url_for('admin.dashboard'))
        return jsonify({'error': 'Internal server error'}), 500
    
    @app.errorhandler(401)
    def unauthorized(e):
        if request.path.startswith('/admin'):
            return redirect(url_for('admin.login', next=request.url))
        return jsonify({'error': 'Unauthorized'}), 401
    
    @app.errorhandler(403)
    def forbidden(e):
        if request.path.startswith('/admin'):
            flash('Доступ запрещён', 'danger')
            return redirect(url_for('admin.dashboard'))
        return jsonify({'error': 'Forbidden'}), 403
    
    # ========================================================================
    # ✅ ЛОГИРОВАНИЕ ПРИ СТАРТЕ
    # ========================================================================
    logger.info(f'🚀 Feedback API Server started ({config_name})')
    logger.info(f'🗄️ Database: {app.config["SQLALCHEMY_DATABASE_URI"]}')
    logger.info(f'🔐 CSRF: enabled for admin, disabled for API')
    logger.info(f'🔐 Admin panel: /admin/login (CSRF protected)')
    logger.info(f'🔌 Public API: /api/v1/health (API key only)')
    
    return app
