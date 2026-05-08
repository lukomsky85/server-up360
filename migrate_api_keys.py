#!/usr/bin/env python3
"""
Миграция feedback-server: добавление полей в таблицу api_keys

Добавляет:
  - requests_count  — счётчик запросов (для rate limiting)
  - revoked_at      — время отзыва ключа
  - revoked_reason  — причина отзыва

Запуск из папки feedback-server:
    python migrate_api_keys.py
"""

import sys
import os
import sqlite3

# Ищем БД рядом со скриптом
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'instance', 'feedback.db')

NEW_COLUMNS = [
    ('requests_count', 'INTEGER DEFAULT 0'),
    ('revoked_at',     'DATETIME'),
    ('revoked_reason', 'VARCHAR(200)'),
]


def upgrade():
    if not os.path.exists(DB_PATH):
        print(f'❌ БД не найдена: {DB_PATH}')
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    try:
        cur.execute('PRAGMA table_info(api_keys)')
        existing = {row[1] for row in cur.fetchall()}

        added = []
        for col_name, col_def in NEW_COLUMNS:
            if col_name not in existing:
                cur.execute(f'ALTER TABLE api_keys ADD COLUMN {col_name} {col_def}')
                added.append(col_name)
                print(f'✅ Добавлена колонка: {col_name}')
            else:
                print(f'⚠️  Уже существует: {col_name}')

        conn.commit()

        if added:
            print(f'\n✅ Миграция выполнена. Добавлено: {len(added)} колонок')
        else:
            print('\n✅ Миграция не нужна — все колонки уже есть')

    except Exception as e:
        conn.rollback()
        print(f'\n❌ Ошибка: {e}')
        sys.exit(1)
    finally:
        conn.close()


if __name__ == '__main__':
    upgrade()
