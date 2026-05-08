# feedback-server/services/auth.py
"""
🔐 Аутентификация по API-ключу для Feedback Server
✅ Проверка ключа в БД, rate limiting, логирование попыток
✅ Совместимо с Flask g-объектом для использования в маршрутах
"""

from functools import wraps
from datetime import datetime, timezone, timedelta
from flask import request, jsonify, g, current_app
import time

from models import APIKey
from extensions import db


# ============================================================================
# 🔐 ДЕКОРАТОР: Проверка API-ключа
# ============================================================================

def require_api_key(f):
    """
    Декоратор: требует валидный активный API-ключ в заголовке запроса.
    
    Ожидает ключ в одном из форматов:
        - Header: X-API-Key: sk_live_abc123...
        - Header: Authorization: Bearer sk_live_abc123...
    
    При успехе:
        - g.api_key содержит объект APIKey из БД
        - Обновляется last_used_at и requests_count ключа
    
    При ошибке:
        - Возвращается JSON 401 с сообщением об ошибке
    
    Использование в маршруте:
        @api_bp.route('/endpoint')
        @require_api_key
        def endpoint():
            # Доступ к ключу: g.api_key.name, g.api_key.rate_limit, etc.
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Получаем ключ из заголовков
        api_key = _extract_api_key_from_request()
        
        if not api_key:
            current_app.logger.warning(f'API key missing from {request.remote_addr}')
            return jsonify({
                'error': 'Missing API key',
                'message': 'Please provide your API key in the X-API-Key header',
                'documentation': 'https://docs.example.com/api/authentication'
            }), 401
        
        # 2. Ищем ключ в БД
        key_obj = APIKey.query.filter_by(key=api_key).first()
        
        if not key_obj:
            current_app.logger.warning(f'Invalid API key attempt from {request.remote_addr}: {api_key[:10]}...')
            return jsonify({
                'error': 'Invalid API key',
                'message': 'The provided API key is not valid'
            }), 401
        
        # 3. Проверяем, активен ли ключ
        if not key_obj.is_active:
            current_app.logger.warning(f'Inactive API key used: {key_obj.name} from {request.remote_addr}')
            return jsonify({
                'error': 'API key disabled',
                'message': 'This API key has been disabled. Please contact support.'
            }), 403
        
        # 4. Rate limiting (опционально)
        if key_obj.rate_limit and key_obj.rate_limit > 0:
            if not _check_rate_limit(key_obj):
                current_app.logger.warning(f'Rate limit exceeded for {key_obj.name}')
                return jsonify({
                    'error': 'Rate limit exceeded',
                    'message': f'Too many requests. Maximum {key_obj.rate_limit} requests per minute.',
                    'retry_after': 60
                }), 429
        
        # 5. ✅ Ключ валиден — сохраняем в g для использования в маршруте
        g.api_key = key_obj
        
        # 6. Обновляем статистику использования (асинхронно в продакшене)
        _update_key_usage(key_obj)
        
        # 7. Логирование успешного доступа (только для отладки)
        if current_app.debug:
            current_app.logger.debug(f'API access: {key_obj.name} → {request.path}')
        
        return f(*args, **kwargs)
    
    return decorated_function


# ============================================================================
# 🔧 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def _extract_api_key_from_request():
    """
    Извлекает API-ключ из заголовков запроса.
    
    Поддерживаемые форматы:
        - X-API-Key: sk_live_abc123...
        - Authorization: Bearer sk_live_abc123...
    
    Returns:
        str or None: Ключ если найден, None если нет
    """
    # Приоритет 1: X-API-Key header
    api_key = request.headers.get('X-API-Key')
    if api_key:
        return api_key.strip()
    
    # Приоритет 2: Authorization: Bearer <key>
    auth_header = request.headers.get('Authorization')
    if auth_header:
        if auth_header.startswith('Bearer '):
            return auth_header[7:].strip()
        # Также поддерживаем просто ключ без префикса
        if ' ' not in auth_header:
            return auth_header.strip()
    
    return None


# feedback-server/services/auth.py — строка ~140-160

def _check_rate_limit(api_key_obj):
    """Проверяет rate limit для API-ключа"""
    from datetime import datetime, timezone, timedelta
    
    # ✅ now — offset-aware (UTC)
    now = datetime.now(timezone.utc)
    
    # ✅ last_used_at может быть None или offset-naive (из БД)
    last_used = api_key_obj.last_used_at
    
    # 🔹 Если last_used — naive, делаем его aware (предполагаем, что он в UTC)
    if last_used and last_used.tzinfo is None:
        last_used = last_used.replace(tzinfo=timezone.utc)
    
    # ✅ Теперь оба datetime — offset-aware, можно вычитать
    if not last_used or (now - last_used) > timedelta(minutes=1):
        api_key_obj.requests_count = 0
        api_key_obj.last_used_at = now  # ✅ Сохраняем aware datetime
        db.session.commit()
        return True
    
    # Проверяем лимит запросов
    if api_key_obj.requests_count >= api_key_obj.rate_limit:
        return False
    
    # Увеличиваем счётчик
    api_key_obj.requests_count += 1
    api_key_obj.last_used_at = now
    db.session.commit()
    return True


def _update_key_usage(api_key_obj):
    """
    Обновляет статистику использования ключа.
    
    - Увеличивает requests_count
    - Обновляет last_used_at
    
    В продакшене: делайте это асинхронно или в фоне, чтобы не замедлять ответ.
    """
    try:
        now = datetime.now(timezone.utc)
        
        # Сброс счётчика если прошла минута
        if api_key_obj.last_used_at and (now - api_key_obj.last_used_at) > timedelta(minutes=1):
            api_key_obj.requests_count = 0
        
        # Обновляем статистику
        api_key_obj.requests_count = (api_key_obj.requests_count or 0) + 1
        api_key_obj.last_used_at = now
        
        db.session.commit()
        
    except Exception as e:
        # Не ломаем запрос если не удалось обновить статистику
        current_app.logger.error(f'Failed to update API key usage: {e}')
        db.session.rollback()


# ============================================================================
# 🔍 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ УПРАВЛЕНИЯ КЛЮЧАМИ
# ============================================================================

def get_api_key_by_name(name: str):
    """
    Получает API-ключ по имени.
    
    Args:
        name: Уникальное имя ключа
    
    Returns:
        APIKey object or None
    """
    return APIKey.query.filter_by(name=name).first()


def create_api_key(name: str, description: str = None, rate_limit: int = 100, 
                   allowed_origins: str = None) -> APIKey:
    """
    Создаёт новый API-ключ.
    
    Args:
        name: Уникальное имя ключа (для идентификации)
        description: Описание назначения ключа
        rate_limit: Максимальное количество запросов в минуту
        allowed_origins: Разрешённые CORS-домены (через запятую)
    
    Returns:
        APIKey: Созданный объект ключа
    
    Raises:
        ValueError: Если ключ с таким именем уже существует
    """
    # Проверка на дубликат
    if APIKey.query.filter_by(name=name).first():
        raise ValueError(f'API key with name "{name}" already exists')
    
    # Генерация криптографически стойкого ключа
    key_value = APIKey.generate_key()
    
    new_key = APIKey(
        key=key_value,
        name=name,
        description=description,
        rate_limit=rate_limit,
        allowed_origins=allowed_origins,
        is_active=True,
    )
    
    db.session.add(new_key)
    db.session.commit()
    
    return new_key


def revoke_api_key(api_key_obj: APIKey, reason: str = None):
    """
    Деактивирует (отзывает) API-ключ.
    
    Args:
        api_key_obj: Объект ключа для отзыва
        reason: Причина отзыва (для логирования)
    
    Returns:
        bool: True если успешно
    """
    api_key_obj.is_active = False
    api_key_obj.revoked_at = datetime.now(timezone.utc)
    api_key_obj.revoked_reason = reason
    
    db.session.commit()
    
    current_app.logger.info(f'API key revoked: {api_key_obj.name} - {reason or "No reason provided"}')
    
    return True


# ============================================================================
# 🛡️ ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: CORS Origins
# ============================================================================

def check_origin_allowed(api_key_obj, origin: str) -> bool:
    """
    Проверяет, разрешён ли указанный Origin для данного API-ключа.
    
    Args:
        api_key_obj: Объект APIKey
        origin: Значение заголовка Origin из запроса
    
    Returns:
        bool: True если Origin разрешён или не задан в ключе
    """
    if not api_key_obj.allowed_origins:
        return True  # Если не задано — разрешаем все
    
    allowed = [o.strip() for o in api_key_obj.allowed_origins.split(',') if o.strip()]
    
    if not allowed:
        return True
    
    # Поддержка wildcard для поддоменов: *.example.com
    for pattern in allowed:
        if pattern == origin:
            return True
        if pattern.startswith('*.') and origin.endswith(pattern[1:]):
            return True
        if pattern == '*':
            return True
    
    return False


def require_origin_allowed(f):
    """
    Декоратор: дополнительно проверяет CORS Origin если задан в ключе.
    
    Использование (после @require_api_key):
        @api_bp.route('/endpoint')
        @require_api_key
        @require_origin_allowed
        def endpoint():
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Проверяем, что ключ уже проверен (должен быть в g)
        if not hasattr(g, 'api_key'):
            return jsonify({'error': 'Authentication required'}), 401
        
        origin = request.headers.get('Origin')
        
        if origin and not check_origin_allowed(g.api_key, origin):
            current_app.logger.warning(f'Origin not allowed: {origin} for key {g.api_key.name}')
            return jsonify({
                'error': 'Origin not allowed',
                'message': f'Origin {origin} is not allowed for this API key'
            }), 403
        
        return f(*args, **kwargs)
    
    return decorated_function