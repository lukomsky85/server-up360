#!/usr/bin/env python3
"""
🏫 Feedback Server — Скрипт инициализации базы данных
✅ Создаёт таблицы
✅ Создаёт тестовый API-ключ (только для development)
"""

import sys
from app import create_app
from extensions import db
from models import APIKey, Feedback, WebhookLog


def main():
    """Основная функция инициализации"""
    # Определяем окружение
    import os
    config_name = os.environ.get('FLASK_ENV', 'development')
    
    print(f'🔧 Инициализация базы данных ({config_name})...')
    
    app = create_app(config_name)
    
    with app.app_context():
        try:
            # Создаём таблицы
            print('🗄️  Создание таблиц базы данных...')
            db.create_all()
            print('✅ Таблицы созданы')
            
            # Создаём тестовый API-ключ (только для dev!)
            if app.config.get('DEBUG'):
                print('\n🔑 Создание тестового API-ключа...')
                
                # Проверяем, есть ли уже ключи
                existing_key = APIKey.query.filter_by(name='test-client').first()
                if existing_key:
                    print('⚠️  Тестовый ключ уже существует')
                    print(f'   Key: {existing_key.key[:20]}...')
                else:
                    test_key = APIKey(
                        key=APIKey.generate_key(),
                        name='test-client',
                        description='Ключ для тестирования (удалите в продакшене)',
                        rate_limit=1000,
                        is_active=True,
                    )
                    db.session.add(test_key)
                    db.session.commit()
                    
                    print('✅ Тестовый API-ключ создан')
                    print(f'🔑 Key: {test_key.key}')
                    print('⚠️  СОХРАНИТЕ ЭТОТ КЛЮЧ! Он не будет показан снова.')
                    print('📝 Используйте его в клиентском приложении:')
                    print(f'   REMOTE_FEEDBACK_API_KEY={test_key.key}')
            
            # Показываем статистику
            print('\n📊 Статистика:')
            print(f'   API ключей: {APIKey.query.count()}')
            print(f'   Обращений: {Feedback.query.count()}')
            
            print('\n✅ База данных инициализирована успешно!')
            print('🚀 Запустите сервер: python run.py')
            
        except Exception as e:
            print(f'\n❌ Ошибка инициализации: {e}')
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == '__main__':
    main()