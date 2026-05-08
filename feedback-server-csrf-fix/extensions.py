# feedback-server/extensions.py
"""
🏫 Feedback Server — Инициализация расширений Flask
✅ Единая точка инициализации для db, migrate, csrf
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf import CSRFProtect

# ✅ Инициализация расширений (без привязки к app)
db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()  # ✅ Добавлено: экземпляр CSRFProtect для @csrf.exempt