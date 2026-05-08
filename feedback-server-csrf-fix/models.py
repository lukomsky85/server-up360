# feedback-server/models.py
from datetime import datetime, timezone
from extensions import db
import secrets


class APIKey(db.Model):
    """API-ключи для аутентификации клиентских приложений"""
    __tablename__ = 'api_keys'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)  # Название приложения
    description = db.Column(db.Text)
    client_id = db.Column(db.String(100))  # Идентификатор клиента (опционально)
    
    is_active = db.Column(db.Boolean, default=True)
    rate_limit = db.Column(db.Integer, default=100)  # Запросов в минуту
    allowed_origins = db.Column(db.Text)  # JSON-список разрешённых доменов
    requests_count = db.Column(db.Integer, default=0)  # Счётчик запросов (для rate limit)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_used_at = db.Column(db.DateTime)
    revoked_at = db.Column(db.DateTime, nullable=True)
    revoked_reason = db.Column(db.String(200), nullable=True)
    
    @staticmethod
    def generate_key():
        """Генерирует криптографически стойкий ключ"""
        return f'sk_live_{secrets.token_urlsafe(32)}'
    
    def __repr__(self):
        return f'<APIKey {self.name}>'


class Feedback(db.Model):
    """Обращение пользователя"""
    __tablename__ = 'feedback'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # 🔗 Идентификаторы
    remote_id = db.Column(db.String(100), unique=True, index=True)  # ID от клиента
    client_id = db.Column(db.String(100), nullable=False, index=True)  # API key name
    
    # 👤 Пользователь (если авторизован)
    user_id = db.Column(db.Integer)  # ID пользователя в клиентском приложении
    username = db.Column(db.String(100))  # Логин для отображения
    
    # 📝 Содержание
    type = db.Column(db.String(20), nullable=False)  # bug, feature, question, other
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    
    # 🌐 Контекст
    page_url = db.Column(db.String(500))
    browser_info = db.Column(db.String(200))
    app_version = db.Column(db.String(50))
    
    # 🎯 Приоритет и статус
    priority = db.Column(db.String(20), default='medium')  # critical, high, medium, low
    status = db.Column(db.String(20), default='new')  # new, in_progress, resolved, rejected
    
    # 💬 Ответ разработчика
    developer_response = db.Column(db.Text)
    responded_at = db.Column(db.DateTime)
    responded_by = db.Column(db.String(100))
    
    # 📅 Даты
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(db.DateTime, onupdate=lambda: datetime.now(timezone.utc))
    
    # 🔗 Вебхуки
    webhook_url = db.Column(db.String(500))  # URL для отправки ответов этому клиенту
    webhook_sent = db.Column(db.Boolean, default=False)
    webhook_attempts = db.Column(db.Integer, default=0)
    
    __table_args__ = (
        db.Index('idx_client_status', 'client_id', 'status'),
        db.Index('idx_created', 'created_at'),
    )
    
    @property
    def priority_class(self):
        """CSS-класс для цвета приоритета"""
        return {
            'critical': 'bg-danger',
            'high': 'bg-warning text-dark',
            'medium': 'bg-info text-dark',
            'low': 'bg-success',
        }.get(self.priority, 'bg-secondary')
    
    @property
    def status_class(self):
        """CSS-класс для цвета статуса"""
        return {
            'new': 'bg-primary',
            'in_progress': 'bg-warning text-dark',
            'resolved': 'bg-success',
            'rejected': 'bg-secondary',
        }.get(self.status, 'bg-light text-dark')
    
    def __repr__(self):
        return f'<Feedback #{self.id} [{self.type}] {self.title[:30]}>'


class WebhookLog(db.Model):
    """Лог отправки вебхуков"""
    __tablename__ = 'webhook_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    feedback_id = db.Column(db.Integer, db.ForeignKey('feedback.id'), nullable=False)
    
    url = db.Column(db.String(500), nullable=False)
    method = db.Column(db.String(10), default='POST')
    status_code = db.Column(db.Integer)
    response_body = db.Column(db.Text)
    error = db.Column(db.Text)
    
    attempt = db.Column(db.Integer, default=1)
    sent_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    feedback = db.relationship('Feedback', backref='webhook_logs')
    
class SystemSetting(db.Model):
    """
    Настройки сервера (ключ-значение)
    ✅ Используется для динамической конфигурации без перезапуска
    """
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=True)
    value_type = db.Column(db.String(20), default='string')  # string, bool, int, float
    description = db.Column(db.String(200), nullable=True)
    category = db.Column(db.String(50), default='general')  # email, system, security, etc.
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, onupdate=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.String(100))  # Кто создал
    updated_by = db.Column(db.String(100))  # Кто обновил
    
    def __repr__(self):
        return f'<SystemSetting {self.key}={self.value}>'
    
    @property
    def typed_value(self):
        """Возвращает значение с правильным типом"""
        if self.value is None:
            return None
        
        if self.value_type == 'bool':
            return self.value.lower() in ('true', '1', 'yes', 'on')
        elif self.value_type == 'int':
            try:
                return int(self.value)
            except (ValueError, TypeError):
                return None
        elif self.value_type == 'float':
            try:
                return float(self.value)
            except (ValueError, TypeError):
                return None
        return self.value  # string или fallback