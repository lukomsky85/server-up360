# feedback-server/test_db_access.py
"""Проверка прямого доступа к БД"""

import sqlite3
from pathlib import Path

DB_PATH = Path('E:/feedback-server/instance/feedback.db')

print(f'🔍 Testing direct SQLite access to: {DB_PATH}')
print(f'   File exists: {DB_PATH.exists()}')
print(f'   Parent exists: {DB_PATH.parent.exists()}')
print(f'   Parent writable: {DB_PATH.parent.is_dir() and __import__("os").access(DB_PATH.parent, __import__("os").W_OK)}')

try:
    # Пробуем подключиться
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('CREATE TABLE IF NOT EXISTS _test (id INTEGER)')
    conn.execute('INSERT INTO _test VALUES (1)')
    conn.commit()
    conn.close()
    print('✅ Direct SQLite access: SUCCESS')
except Exception as e:
    print(f'❌ Direct SQLite access: FAILED - {type(e).__name__}: {e}')
    print('\n💡 Try these fixes:')
    print('   1. Run PowerShell as Administrator')
    print('   2. Add Windows Defender exclusion for instance/')
    print('   3. Use absolute path in DATABASE_URL')
    print('   4. Delete feedback.db-shm and feedback.db-wal files')