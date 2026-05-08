#!/usr/bin/env python3
"""
🔍 Прямой тест подключения к SQLite — обходит SQLAlchemy
"""

import os
import sys
from pathlib import Path
import sqlite3

# Добавляем проект в path
sys.path.insert(0, str(Path(__file__).parent))

print('🔍 SQLite Direct Connection Test')
print('=' * 60)

# 1. Проверяем пути
print(f'\n📁 Paths:')
print(f'   Script: {Path(__file__).resolve()}')
print(f'   CWD: {Path.cwd()}')
print(f'   Project: {Path(__file__).parent.resolve()}')

# 2. Импортируем конфиг
from config import INSTANCE_DIR, DATABASE_URL
print(f'\n⚙️ Config:')
print(f'   INSTANCE_DIR: {INSTANCE_DIR}')
print(f'   INSTANCE_DIR exists: {INSTANCE_DIR.exists()}')
print(f'   INSTANCE_DIR writable: {os.access(INSTANCE_DIR, os.W_OK)}')
print(f'   DATABASE_URL: {DATABASE_URL}')

# 3. Извлекаем путь к файлу из DATABASE_URL
db_path = DATABASE_URL.replace('sqlite:///', '')
print(f'\n🗄️ Database:')
print(f'   DB path (raw): {db_path}')
print(f'   DB file exists: {Path(db_path).exists()}')
if Path(db_path).exists():
    print(f'   DB file size: {Path(db_path).stat().st_size} bytes')
print(f'   DB parent exists: {Path(db_path).parent.exists()}')
print(f'   DB parent writable: {os.access(Path(db_path).parent, os.W_OK)}')

# 4. Пытаемся подключиться напрямую через sqlite3
print(f'\n🔌 Direct SQLite connection test:')
try:
    # Важно: используем абсолютный путь и увеличиваем timeout
    conn = sqlite3.connect(db_path, timeout=30, isolation_level=None)
    conn.execute('PRAGMA journal_mode=WAL')  # Улучшает работу на Windows
    conn.execute('CREATE TABLE IF NOT EXISTS _test_connect (id INTEGER)')
    conn.execute('INSERT INTO _test_connect VALUES (1)')
    conn.execute('DELETE FROM _test_connect WHERE id = 1')
    conn.close()
    print('   ✅ SUCCESS: Direct SQLite connection works!')
except sqlite3.OperationalError as e:
    print(f'   ❌ FAILED: {e}')
    print('\n💡 Возможные решения:')
    print('   1. Запустите от имени администратора')
    print('   2. Добавьте исключение в Защитник для папки:')
    print(f'      Add-MpPreference -ExclusionPath "{INSTANCE_DIR}"')
    print('   3. Проверьте, что путь не содержит кириллицы или спецсимволов')
    print('   4. Попробуйте использовать PostgreSQL вместо SQLite')
except Exception as e:
    print(f'   ❌ FAILED: {type(e).__name__}: {e}')

print('\n' + '=' * 60)