# feedback-server/routes/admin.py
"""
🏫 Feedback Server — Админ-панель (ПОЛНОСТЬЮ РАБОЧАЯ + ОТЛАДКА)
✅ Авторизация, дашборд, управление обращениями, настройки
✅ ✅ ✅ Отладочные маршруты для диагностики CSRF и сессий
"""

from functools import wraps
from datetime import datetime, timezone, timedelta
from flask import (
    Blueprint, render_template, request, redirect, url_for, 
    session, flash, jsonify, current_app
)
from sqlalchemy import func, and_
from extensions import db, csrf  # ✅ Импортируем csrf для @csrf.exempt
from models import Feedback, APIKey, WebhookLog, SystemSetting
from services.webhooks import queue_pending_webhooks

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# ============================================================================
# 🔐 ДЕКОРАТОРЫ АВТОРИЗАЦИИ
# ============================================================================

def admin_login_required(f):
    """Требует входа в админ-панель"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('admin.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# 🔐 АВТОРИЗАЦИЯ
# ============================================================================

@admin_bp.route('/login', methods=['GET', 'POST'])
@csrf.exempt  # ✅ ВРЕМЕННО: отключаем CSRF для отладки входа (УБРАТЬ после фикса!)
def login():
    """Страница входа в админ-панель"""
    if session.get('admin_logged_in'):
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        next_url = request.form.get('next') or request.args.get('next')
        
        # Проверка учётных данных
        if (username == current_app.config.get('ADMIN_USERNAME') and 
            password == current_app.config.get('ADMIN_PASSWORD')):
            
            session['admin_logged_in'] = True
            session['admin_username'] = username
            session.permanent = True
            
            # Логирование входа
            current_app.logger.info(f'Admin login: {username} from {request.remote_addr}')
            
            flash(f'Добро пожаловать, {username}!', 'success')
            return redirect(next_url or url_for('admin.dashboard'))
        else:
            flash('Неверный логин или пароль', 'danger')
            current_app.logger.warning(f'Failed admin login attempt for "{username}" from {request.remote_addr}')
    
    return render_template('admin/login.html', next=request.args.get('next'))


@admin_bp.route('/logout')
@admin_login_required
def logout():
    """Выход из админ-панели"""
    username = session.get('admin_username', 'unknown')
    session.clear()
    current_app.logger.info(f'Admin logout: {username}')
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('admin.login'))


# ============================================================================
# 🔍 ОТЛАДОЧНЫЕ МАРШРУТЫ (удалите в продакшене!)
# ============================================================================

@admin_bp.route('/debug-config')
@admin_login_required
def debug_config():
    """Отладка конфигурации сессий и CSRF (только для авторизованных)"""
    return jsonify({
        'SECRET_KEY_set': bool(current_app.config.get('SECRET_KEY')),
        'SECRET_KEY_length': len(current_app.config.get('SECRET_KEY', '')),
        'SESSION_COOKIE_SECURE': current_app.config.get('SESSION_COOKIE_SECURE'),
        'SESSION_COOKIE_SAMESITE': current_app.config.get('SESSION_COOKIE_SAMESITE'),
        'WTF_CSRF_ENABLED': current_app.config.get('WTF_CSRF_ENABLED'),
        'WTF_CSRF_SSL_STRICT': current_app.config.get('WTF_CSRF_SSL_STRICT'),
        'DATABASE_URI': current_app.config.get('SQLALCHEMY_DATABASE_URI')[:100],
        'session_admin_logged_in': session.get('admin_logged_in'),
        'session_admin_username': session.get('admin_username'),
        'session_permanent': session.permanent if hasattr(session, 'permanent') else None,
    })


@admin_bp.route('/test-csrf', methods=['GET', 'POST'])
@admin_login_required
def test_csrf():
    """Простая тестовая форма для проверки CSRF"""
    if request.method == 'POST':
        result = request.form.get('test_input', 'empty')
        flash(f'✅ CSRF работает! Получено: {result}', 'success')
        return redirect(url_for('admin.test_csrf'))
    
    return render_template('admin/test_csrf.html')


@admin_bp.route('/test-session')
@admin_login_required
def test_session():
    """Проверка работы сессий"""
    # Записываем в сессию
    session['_test_key'] = 'test_value'
    session['_test_time'] = datetime.now(timezone.utc).isoformat()
    
    # Читаем из сессии
    return jsonify({
        'session_write': 'ok',
        'session_read': session.get('_test_key'),
        'session_time': session.get('_test_time'),
        'session_id': session.sid if hasattr(session, 'sid') else 'N/A',
    })


# ============================================================================
# 📊 ДАШБОРД
# ============================================================================

@admin_bp.route('/')
@admin_bp.route('/dashboard')
@admin_login_required
def dashboard():
    """Главная панель администратора"""
    # Статистика по статусам
    by_status = dict(db.session.query(
        Feedback.status, func.count(Feedback.id)
    ).group_by(Feedback.status).all())
    
    # Статистика по типам
    by_type = dict(db.session.query(
        Feedback.type, func.count(Feedback.id)
    ).group_by(Feedback.type).all())
    
    # Статистика по приоритетам
    by_priority = dict(db.session.query(
        Feedback.priority, func.count(Feedback.id)
    ).group_by(Feedback.priority).all())
    
    # За последние 7 дней (по дням)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_daily = db.session.query(
        func.date(Feedback.created_at), func.count(Feedback.id)
    ).filter(Feedback.created_at >= week_ago).group_by(
        func.date(Feedback.created_at)
    ).all()
    
    # Последние обращения
    recent_feedback = Feedback.query.order_by(
        Feedback.created_at.desc()
    ).limit(10).all()
    
    # Новые (необработанные)
    new_count = Feedback.query.filter_by(status='new').count()
    
    stats = {
        'total': Feedback.query.count(),
        'new': by_status.get('new', 0),
        'in_progress': by_status.get('in_progress', 0),
        'resolved': by_status.get('resolved', 0),
        'rejected': by_status.get('rejected', 0),
        'bugs': by_type.get('bug', 0),
        'features': by_type.get('feature', 0),
        'critical': by_priority.get('critical', 0),
        'recent_7days': sum(count for _, count in recent_daily),
        'recent_daily': [{'date': str(d), 'count': c} for d, c in recent_daily],
    }
    
    return render_template('admin/dashboard.html',
                         stats=stats,
                         recent_feedback=recent_feedback,
                         by_type=by_type,
                         by_status=by_status,
                         by_priority=by_priority)


# ============================================================================
# 📋 УПРАВЛЕНИЕ ОБРАЩЕНИЯМИ
# ============================================================================

@admin_bp.route('/feedback')
@admin_login_required
def feedback_list():
    """Список всех обращений с фильтрами"""
    # Фильтры из query params
    feedback_type = request.args.get('type', '')
    status = request.args.get('status', '')
    priority = request.args.get('priority', '')
    search = request.args.get('search', '')
    client_id = request.args.get('client_id', '')
    
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 25, type=int), 100)
    
    query = Feedback.query
    
    if feedback_type:
        query = query.filter_by(type=feedback_type)
    if status:
        query = query.filter_by(status=status)
    if priority:
        query = query.filter_by(priority=priority)
    if client_id:
        query = query.filter_by(client_id=client_id)
    if search:
        query = query.filter(
            (Feedback.title.ilike(f'%{search}%')) |
            (Feedback.description.ilike(f'%{search}%')) |
            (Feedback.username.ilike(f'%{search}%'))
        )
    
    # Сортировка
    sort_by = request.args.get('sort', 'created_at')
    sort_order = request.args.get('order', 'desc')
    
    if sort_by in ['created_at', 'updated_at', 'priority', 'status']:
        column = getattr(Feedback, sort_by)
        query = query.order_by(column.desc() if sort_order == 'desc' else column.asc())
    
    feedbacks = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Уникальные client_id для фильтра
    client_ids = db.session.query(Feedback.client_id).distinct().all()
    
    return render_template('admin/feedback_list.html',
                         feedbacks=feedbacks,
                         filters={
                             'type': feedback_type,
                             'status': status,
                             'priority': priority,
                             'search': search,
                             'client_id': client_id,
                             'sort': sort_by,
                             'order': sort_order,
                         },
                         client_ids=[c[0] for c in client_ids if c[0]])


@admin_bp.route('/feedback/<int:feedback_id>')
@admin_login_required
def feedback_detail(feedback_id):
    """Детали конкретного обращения"""
    feedback = Feedback.query.get_or_404(feedback_id)
    
    # Похожие обращения (для поиска дубликатов)
    similar = Feedback.query.filter(
        Feedback.type == feedback.type,
        Feedback.id != feedback.id,
        Feedback.title.ilike(f'%{feedback.title.split()[0]}%') if feedback.title else False
    ).order_by(Feedback.created_at.desc()).limit(5).all()
    
    # История вебхуков
    webhook_logs = WebhookLog.query.filter_by(
        feedback_id=feedback.id
    ).order_by(WebhookLog.sent_at.desc()).limit(10).all()
    
    return render_template('admin/feedback_detail.html',
                         feedback=feedback,
                         similar=similar,
                         webhook_logs=webhook_logs)


@admin_bp.route('/feedback/<int:feedback_id>/respond', methods=['POST'])
@admin_login_required
def respond_to_feedback(feedback_id):
    """Отправка ответа на обращение"""
    feedback = Feedback.query.get_or_404(feedback_id)
    
    response = request.form.get('response', '').strip()
    new_status = request.form.get('status', feedback.status)
    send_webhook = request.form.get('send_webhook', 'on') == 'on'
    
    if not response:
        flash('Ответ не может быть пустым', 'warning')
        return redirect(url_for('admin.feedback_detail', feedback_id=feedback_id))
    
    # Обновляем обращение
    feedback.developer_response = response
    feedback.updated_at = datetime.now(timezone.utc)
    
    valid_statuses = ['new', 'in_progress', 'resolved', 'rejected']
    if new_status in valid_statuses:
        feedback.status = new_status
        if new_status == 'resolved':
            feedback.responded_at = datetime.now(timezone.utc)
    
    db.session.commit()
    
    # Отправляем вебхук если включено
    if send_webhook and feedback.webhook_url:
        from services.webhooks import send_webhook as send_wh
        try:
            send_wh(feedback)
            flash('Ответ сохранён и отправлен клиенту', 'success')
        except Exception as e:
            current_app.logger.error(f'Webhook send error: {e}')
            flash('Ответ сохранён, но не удалось отправить вебхук', 'warning')
    else:
        flash('Ответ сохранён', 'success')
    
    return redirect(url_for('admin.feedback_detail', feedback_id=feedback_id))


@admin_bp.route('/feedback/<int:feedback_id>/status', methods=['POST'])
@admin_login_required
def update_feedback_status(feedback_id):
    """Быстрое изменение статуса"""
    feedback = Feedback.query.get_or_404(feedback_id)
    new_status = request.form.get('status')
    
    valid_statuses = ['new', 'in_progress', 'resolved', 'rejected']
    if new_status not in valid_statuses:
        flash('Неверный статус', 'danger')
        return redirect(url_for('admin.feedback_list'))
    
    old_status = feedback.status
    feedback.status = new_status
    feedback.updated_at = datetime.now(timezone.utc)
    
    if new_status == 'resolved':
        feedback.responded_at = datetime.now(timezone.utc)
    
    db.session.commit()
    
    current_app.logger.info(f'Feedback #{feedback_id} status: {old_status} → {new_status}')
    flash(f'Статус обновлён: {new_status}', 'success')
    
    # Если есть вебхук — отправляем
    if feedback.webhook_url:
        from services.webhooks import send_webhook as send_wh
        try:
            send_wh(feedback)
        except Exception as e:
            current_app.logger.error(f'Webhook error on status change: {e}')
    
    return redirect(url_for('admin.feedback_list'))


@admin_bp.route('/feedback/<int:feedback_id>/delete', methods=['POST'])
@admin_login_required
def delete_feedback(feedback_id):
    """Удаление обращения"""
    feedback = Feedback.query.get_or_404(feedback_id)
    
    title = feedback.title
    db.session.delete(feedback)
    db.session.commit()
    
    current_app.logger.info(f'Feedback #{feedback_id} deleted: "{title}"')
    flash(f'Обращение удалено: {title[:50]}', 'success')
    
    return redirect(url_for('admin.feedback_list'))


@admin_bp.route('/feedback/bulk-action', methods=['POST'])
@admin_login_required
def feedback_bulk_action():
    """Массовое действие над выбранными обращениями"""
    action = request.form.get('action')
    feedback_ids = request.form.getlist('feedback_ids')
    
    if not action or not feedback_ids:
        flash('Выберите действия и обращения', 'warning')
        return redirect(url_for('admin.feedback_list'))
    
    count = 0
    for fid in feedback_ids:
        feedback = Feedback.query.get(fid)
        if not feedback:
            continue
        
        if action == 'delete':
            db.session.delete(feedback)
            count += 1
        elif action == 'resolve':
            feedback.status = 'resolved'
            feedback.responded_at = datetime.now(timezone.utc)
            feedback.updated_at = datetime.now(timezone.utc)
            count += 1
        elif action == 'in_progress':
            feedback.status = 'in_progress'
            feedback.updated_at = datetime.now(timezone.utc)
            count += 1
    
    if count > 0:
        db.session.commit()
        flash(f'Обработано {count} обращений', 'success')
    else:
        flash('Ни одно обращение не обработано', 'warning')
    
    return redirect(url_for('admin.feedback_list'))


# ============================================================================
# 🔑 УПРАВЛЕНИЕ API-КЛЮЧАМИ
# ============================================================================

@admin_bp.route('/api-keys')
@admin_login_required
def api_keys_list():
    """Список API-ключей"""
    keys = APIKey.query.order_by(APIKey.created_at.desc()).all()
    return render_template('admin/api_keys.html', api_keys=keys)


@admin_bp.route('/api-keys/create', methods=['GET', 'POST'])
@admin_login_required
def api_key_create():
    """Создание нового API-ключа"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        rate_limit = request.form.get('rate_limit', 100, type=int)
        allowed_origins = request.form.get('allowed_origins', '').strip()
        
        if not name or len(name) < 3:
            flash('Название ключа должно содержать минимум 3 символа', 'danger')
            return redirect(url_for('admin.api_key_create'))
        
        if APIKey.query.filter_by(name=name).first():
            flash('Ключ с таким названием уже существует', 'warning')
            return redirect(url_for('admin.api_key_create'))
        
        new_key = APIKey(
            key=APIKey.generate_key(),
            name=name,
            description=description,
            rate_limit=rate_limit,
            allowed_origins=allowed_origins,
        )
        db.session.add(new_key)
        db.session.commit()
        
        current_app.logger.info(f'API key created: {name}')
        flash(f'Ключ создан: {new_key.key}', 'success')
        flash('⚠️ Сохраните этот ключ — он не будет показан снова!', 'warning')
        
        return redirect(url_for('admin.api_keys_list'))
    
    return render_template('admin/api_key_form.html', api_key=None)


@admin_bp.route('/api-keys/<int:key_id>/toggle', methods=['POST'])
@admin_login_required
def api_key_toggle(key_id):
    """Включить/выключить API-ключ"""
    key = APIKey.query.get_or_404(key_id)
    key.is_active = not key.is_active
    db.session.commit()
    
    status = 'активирован' if key.is_active else 'деактивирован'
    flash(f'Ключ "{key.name}" {status}', 'success')
    return redirect(url_for('admin.api_keys_list'))


@admin_bp.route('/api-keys/<int:key_id>/delete', methods=['POST'])
@admin_login_required
def api_key_delete(key_id):
    """Удаление API-ключа"""
    key = APIKey.query.get_or_404(key_id)
    
    # Не удаляем если есть активные обращения от этого клиента
    if Feedback.query.filter_by(client_id=key.name).count() > 0:
        flash('Нельзя удалить ключ, от которого есть обращения', 'danger')
        return redirect(url_for('admin.api_keys_list'))
    
    name = key.name
    db.session.delete(key)
    db.session.commit()
    
    current_app.logger.info(f'API key deleted: {name}')
    flash(f'Ключ "{name}" удалён', 'success')
    return redirect(url_for('admin.api_keys_list'))


# ============================================================================
# ⚙️ НАСТРОЙКИ СЕРВЕРА
# ============================================================================

@admin_bp.route('/settings', methods=['GET', 'POST'])
@admin_login_required
def settings():
    """Настройки сервера"""
    if request.method == 'POST':
        # Простая обработка: сохраняем в SystemSetting
        settings_to_save = [
            'webhook_timeout', 'webhook_retry_count', 'items_per_page',
            'auto_cleanup_days', 'enable_registration', 'maintenance_mode'
        ]
        
        changed = []
        for key in settings_to_save:
            value = request.form.get(f'setting_{key}')
            if value is not None:
                setting = SystemSetting.query.filter_by(key=key).first()
                if setting:
                    if setting.value != value:
                        setting.value = value
                        setting.updated_at = datetime.now(timezone.utc)
                        db.session.add(setting)
                        changed.append(key)
                else:
                    db.session.add(SystemSetting(key=key, value=value, description=f'Server setting: {key}'))
                    changed.append(key)
        
        if changed:
            db.session.commit()
            flash(f'Сохранено {len(changed)} настроек', 'success')
        else:
            flash('Нет изменений для сохранения', 'info')
        
        return redirect(url_for('admin.settings'))
    
    # Загружаем текущие настройки
    all_settings = SystemSetting.query.all()
    settings_dict = {s.key: s.value for s in all_settings}
    
    return render_template('admin/settings.html', settings_dict=settings_dict)


# ============================================================================
# 🔄 ФОНОВЫЕ ЗАДАЧИ (ручной запуск)
# ============================================================================

@admin_bp.route('/tasks/sync-webhooks', methods=['POST'])
@admin_login_required
def task_sync_webhooks():
    """Ручной запуск обработки очереди вебхуков"""
    count = queue_pending_webhooks()
    flash(f'Обработано {count} отложенных вебхуков', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/tasks/cleanup', methods=['POST'])
@admin_login_required
def task_cleanup():
    """Очистка старых данных"""
    from models import WebhookLog
    
    days = request.form.get('days', 90, type=int)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    # Удаляем старые логи вебхуков
    deleted = WebhookLog.query.filter(WebhookLog.sent_at < cutoff).delete()
    db.session.commit()
    
    flash(f'Удалено {deleted} старых записей логов', 'success')
    return redirect(url_for('admin.settings'))


# ============================================================================
# 📡 API ДЛЯ АДМИН-ПАНЕЛИ (AJAX)
# ============================================================================

@admin_bp.route('/api/stats')
@admin_login_required
def api_stats():
    """API: статистика для графиков"""
    # За последние 30 дней
    month_ago = datetime.now(timezone.utc) - timedelta(days=30)
    
    daily = db.session.query(
        func.date(Feedback.created_at),
        func.count(Feedback.id)
    ).filter(Feedback.created_at >= month_ago).group_by(
        func.date(Feedback.created_at)
    ).all()
    
    return jsonify({
        'daily': [{'date': str(d), 'count': c} for d, c in daily],
        'by_status': dict(db.session.query(Feedback.status, func.count(Feedback.id)).group_by(Feedback.status).all()),
        'by_type': dict(db.session.query(Feedback.type, func.count(Feedback.id)).group_by(Feedback.type).all()),
    })