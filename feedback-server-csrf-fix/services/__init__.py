# feedback-server/services/__init__.py
"""
📦 Services package for Feedback Server
✅ Экспорт основных функций для удобного импорта
"""

from .auth import (
    require_api_key,
    require_origin_allowed,
    get_api_key_by_name,
    create_api_key,
    revoke_api_key,
    check_origin_allowed,
)

from .webhooks import (
    send_webhook,
    queue_pending_webhooks,
)

__all__ = [
    # Auth
    'require_api_key',
    'require_origin_allowed',
    'get_api_key_by_name',
    'create_api_key',
    'revoke_api_key',
    'check_origin_allowed',
    # Webhooks
    'send_webhook',
    'queue_pending_webhooks',
]