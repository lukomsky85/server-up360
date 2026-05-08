# feedback-server/routes/api.py
from flask import Blueprint, request, jsonify, current_app, g
from datetime import datetime, timezone
from extensions import db
from models import Feedback, APIKey
from services.auth import require_api_key
from services.webhooks import send_webhook, queue_pending_webhooks

api_bp = Blueprint('api', __name__, url_prefix='/api/v1')


@api_bp.route('/feedback', methods=['POST'])
@require_api_key
def create_feedback():
    """
    POST /api/v1/feedback
    Создание нового обращения от клиентского приложения
    
    Body:
    {
        "external_id": "123",           # ID в клиентской системе (опционально)
        "user_id": 456,                  # ID пользователя (опционально)
        "username": "ivanov",           # Логин для отображения
        "type": "bug",                   # bug|feature|question|other
        "title": "Ошибка при экспорте",
        "description": "При нажатии...",
        "page_url": "/export",          # Страница, где возникла проблема
        "browser_info": "Chrome 120",   # Информация о браузере
        "app_version": "3.1.0",         # Версия приложения
        "priority": "high",             # critical|high|medium|low
        "webhook_url": "https://..."    # URL для получения ответов (опционально)
    }
    """
    data = request.get_json()
    
    # Валидация обязательных полей
    required = ['type', 'title', 'description']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    # Валидация типа
    valid_types = ['bug', 'feature', 'question', 'other']
    if data['type'] not in valid_types:
        return jsonify({'error': f'Invalid type. Must be one of: {valid_types}'}), 400
    
    # Создание обращения
    feedback = Feedback(
        remote_id=data.get('external_id'),
        client_id=g.api_key.name,
        user_id=data.get('user_id'),
        username=data.get('username'),
        type=data['type'],
        title=data['title'][:200],  # Ограничение длины
        description=data['description'],
        page_url=data.get('page_url'),
        browser_info=data.get('browser_info'),
        app_version=data.get('app_version'),
        priority=data.get('priority', 'medium'),
        webhook_url=data.get('webhook_url'),
    )
    
    db.session.add(feedback)
    db.session.commit()
    
    # Если есть webhook_url — пробуем отправить подтверждение
    if feedback.webhook_url:
        # Отправляем в фоне или в очереди
        # Здесь для простоты — синхронно
        send_webhook(feedback)
    
    return jsonify({
        'id': feedback.id,
        'remote_id': feedback.remote_id,
        'status': feedback.status,
        'created_at': feedback.created_at.isoformat(),
    }), 201


@api_bp.route('/feedback', methods=['GET'])
@require_api_key
def list_feedback():
    """
    GET /api/v1/feedback
    Список обращений для клиента
    
    Query params:
        status: new|in_progress|resolved|rejected
        type: bug|feature|question|other
        priority: critical|high|medium|low
        page: номер страницы
        limit: записей на странице (макс. 100)
    """
    # Фильтры
    query = Feedback.query.filter_by(client_id=g.api_key.name)
    
    if status := request.args.get('status'):
        query = query.filter_by(status=status)
    if ftype := request.args.get('type'):
        query = query.filter_by(type=ftype)
    if priority := request.args.get('priority'):
        query = query.filter_by(priority=priority)
    
    # Пагинация
    page = request.args.get('page', 1, type=int)
    limit = min(request.args.get('limit', 50, type=int), 100)
    
    pagination = query.order_by(Feedback.created_at.desc()).paginate(
        page=page, per_page=limit, error_out=False
    )
    
    return jsonify({
        'items': [fb.to_dict() for fb in pagination.items],
        'page': pagination.page,
        'pages': pagination.pages,
        'total': pagination.total,
    })


@api_bp.route('/feedback/<int:feedback_id>', methods=['GET'])
@require_api_key
def get_feedback(feedback_id):
    """Получение конкретного обращения"""
    feedback = Feedback.query.filter_by(
        id=feedback_id,
        client_id=g.api_key.name
    ).first_or_404()
    
    return jsonify(feedback.to_dict())


@api_bp.route('/feedback/<int:feedback_id>', methods=['PATCH'])
@require_api_key
def update_feedback(feedback_id):
    """
    PATCH /api/v1/feedback/<id>
    Обновление статуса и ответа (обычно вызывается админом через вебхук)
    
    Body:
    {
        "status": "resolved",              # new|in_progress|resolved|rejected
        "developer_response": "Исправлено",
        "priority": "low"                  # опционально
    }
    """
    feedback = Feedback.query.filter_by(
        id=feedback_id,
        client_id=g.api_key.name
    ).first_or_404()
    
    data = request.get_json()
    
    # Обновляем поля
    if 'status' in data and data['status'] in ['new', 'in_progress', 'resolved', 'rejected']:
        feedback.status = data['status']
    
    if 'developer_response' in data:
        feedback.developer_response = data['developer_response']
        feedback.responded_at = datetime.now(timezone.utc)
        feedback.responded_by = g.api_key.name
    
    if 'priority' in data and data['priority'] in ['critical', 'high', 'medium', 'low']:
        feedback.priority = data['priority']
    
    feedback.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    
    # Если есть webhook_url — отправляем уведомление
    if feedback.webhook_url and feedback.status in ['resolved', 'rejected']:
        send_webhook(feedback)
    
    return jsonify({
        'id': feedback.id,
        'status': feedback.status,
        'developer_response': feedback.developer_response,
        'updated_at': feedback.updated_at.isoformat(),
    })


@api_bp.route('/feedback/responses', methods=['GET'])
@require_api_key
def get_responses():
    """
    GET /api/v1/feedback/responses
    Получение обращений с новыми ответами (для синхронизации)
    
    Возвращает обращения, где статус изменился на resolved/rejected
    и есть developer_response, но ещё не отправлен вебхук.
    """
    # Фильтры
    query = Feedback.query.filter_by(client_id=g.api_key.name)
    
    # Только с ответами и финальными статусами
    query = query.filter(
        Feedback.developer_response != None,
        Feedback.status.in_(['resolved', 'rejected']),
        Feedback.webhook_sent == False  # Ещё не отправлено
    )
    
    limit = min(request.args.get('limit', 50, type=int), 100)
    feedbacks = query.order_by(Feedback.responded_at.desc()).limit(limit).all()
    
    return jsonify({
        'items': [fb.to_dict() for fb in feedbacks],
    })


@api_bp.route('/health', methods=['GET'])
def health_check():
    """Проверка работоспособности сервера"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'version': '1.0.0',
    })


# ============================================================================
# ✅ Вспомогательный метод для сериализации
# ============================================================================
def _feedback_to_dict(fb: Feedback):
    """Конвертирует модель в словарь для API"""
    return {
        'id': fb.id,
        'remote_id': fb.remote_id,
        'client_id': fb.client_id,
        'user_id': fb.user_id,
        'username': fb.username,
        'type': fb.type,
        'title': fb.title,
        'description': fb.description,
        'page_url': fb.page_url,
        'browser_info': fb.browser_info,
        'app_version': fb.app_version,
        'priority': fb.priority,
        'priority_class': fb.priority_class,
        'status': fb.status,
        'status_class': fb.status_class,
        'developer_response': fb.developer_response,
        'responded_at': fb.responded_at.isoformat() if fb.responded_at else None,
        'created_at': fb.created_at.isoformat(),
        'updated_at': fb.updated_at.isoformat() if fb.updated_at else None,
    }


# Добавляем метод к модели (или используйте mixin)
Feedback.to_dict = _feedback_to_dict