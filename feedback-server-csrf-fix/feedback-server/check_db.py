#!/usr/bin/env python
"""Диагностика проблемы с базой данных"""

import os
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 60)
print("🔍 ДИАГНОСТИКА БАЗЫ ДАННЫХ")
print("=" * 60)

# 1. Проверяем config
print("\n1️⃣ Проверка конфигурации:")
from config import BASE_DIR, INSTANCE_DIR, DB_PATH, DATABASE_URL

print(f"   BASE_DIR: {BASE_DIR}")
print(f"   INSTANCE_DIR: {INSTANCE_DIR}")
print(f"   DB_PATH: {DB_PATH}")
print(f"   DATABASE_URL: {DATABASE_URL}")

# 2. Проверяем существование директорий
print("\n2️⃣ Проверка директорий:")
print(f"   INSTANCE_DIR существует: {INSTANCE_DIR.exists()}")
if not INSTANCE_DIR.exists():
    print(f"   ✨ Создаём INSTANCE_DIR...")
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"   ✅ Создано")

# 3. Проверяем права на запись
print("\n3️⃣ Проверка прав на запись:")
test_file = INSTANCE_DIR / 'test_write.tmp'
try:
    test_file.write_text('test')
    test_file.unlink()
    print(f"   ✅ Права на запись есть")
except Exception as e:
    print(f"   ❌ Нет прав на запись: {e}")
    sys.exit(1)

# 4. Проверяем создание БД через SQLAlchemy
print("\n4️⃣ Проверка SQLAlchemy:")
try:
    from flask import Flask
    from flask_sqlalchemy import SQLAlchemy
    
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db = SQLAlchemy(app)
    
    with app.app_context():
        # Пробуем создать таблицы
        class Test(db.Model):
            __tablename__ = 'test'
            id = db.Column(db.Integer, primary_key=True)
        
        db.create_all()
        print(f"   ✅ База данных успешно создана/подключена")
        
        # Проверяем файл
        if DB_PATH.exists():
            size = DB_PATH.stat().st_size
            print(f"   📁 Файл БД создан: {DB_PATH}")
            print(f"   📊 Размер: {size} байт")
        else:
            print(f"   ❌ Файл БД НЕ создан!")
            
except Exception as e:
    print(f"   ❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ Диагностика завершена")
print("=" * 60)