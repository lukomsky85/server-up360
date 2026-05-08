# feedback-server/services/webhooks.py
import requests
import logging
from datetime import datetime, timezone
from extensions import db
from models import Feedback, WebhookLog

logger = logging.getLogger(__name__)


def send_webhook(feedback: Feedback, timeout: int = 30) -> bool:
    """Отправляет вебхук с обновлением обращения"""
    if not feedback.webhook_url:
        return True  # Нет вебхука — считаем успешным
    
    payload = {
        'event': 'feedback.updated',
        'feedback': {
            'id': feedback.remote_id,
            'external_id': feedback.id,
            'type': feedback.type,
            'title': feedback.title,
            'status': feedback.status,
            'priority': feedback.priority,
            'developer_response': feedback.developer_response,
            'responded_at': feedback.responded_at.isoformat() if feedback.responded_at else None,
            'updated_at': feedback.updated_at.isoformat() if feedback.updated_at else None,
        },
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
    
    try:
        response = requests.post(
            feedback.webhook_url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=timeout
        )
        
        # Логируем результат
        log = WebhookLog(
            feedback_id=feedback.id,
            url=feedback.webhook_url,
            status_code=response.status_code,
            response_body=response.text[:1000] if response.text else None,
            attempt=feedback.webhook_attempts + 1,
        )
        db.session.add(log)
        
        if response.status_code in (200, 201, 204):
            feedback.webhook_sent = True
            feedback.webhook_attempts = 0
            db.session.commit()
            logger.info(f'Webhook sent to {feedback.webhook_url} for feedback #{feedback.id}')
            return True
        else:
            feedback.webhook_attempts += 1
            db.session.commit()
            logger.warning(f'Webhook failed ({response.status_code}) for feedback #{feedback.id}')
            return False
            
    except requests.exceptions.Timeout:
        logger.error(f'Webhook timeout for feedback #{feedback.id}')
        feedback.webhook_attempts += 1
        db.session.commit()
        return False
    except requests.exceptions.ConnectionError:
        logger.error(f'Webhook connection error for feedback #{feedback.id}')
        feedback.webhook_attempts += 1
        db.session.commit()
        return False
    except Exception as e:
        logger.error(f'Webhook error: {e}')
        return False


def queue_pending_webhooks(max_attempts: int = 5):
    """Обрабатывает очередь неудачных вебхуков"""
    pending = Feedback.query.filter(
        Feedback.webhook_url != None,
        Feedback.webhook_sent == False,
        Feedback.webhook_attempts < max_attempts
    ).limit(50).all()
    
    sent = 0
    for feedback in pending:
        if send_webhook(feedback):
            sent += 1
    
    if sent > 0:
        logger.info(f'Processed {sent} pending webhooks')
    
    return sent