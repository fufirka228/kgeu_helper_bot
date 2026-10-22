import json
import asyncio
from pathlib import Path
from aiosqlite import connect

# Пути к файлам
BASE_DIR = Path(__file__).resolve().parent
JSON_PATH = BASE_DIR / 'storage' / 'teachers.json'
DB_PATH = BASE_DIR / 'storage' / 'bot.db'

# Слова-маркеры мусорных записей
JUNK_WORDS = {"вакансия", "тест", "ноль", "ххх", "кафедра", "гуап", "книту"}


async def import_teachers():
    if not JSON_PATH.exists():
        print(f"❌ Ошибка: Файл {JSON_PATH} не найден! Положи teachers.json в папку storage/")
        return

    # 1. Читаем JSON
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    raw_teachers = data.get("data", [])
    cleaned_teachers = []

    # 2. Фильтруем и форматируем ФИО
    for item in raw_teachers:
        t_id = item.get("id")
        last = item.get("lastName", "").strip()
        first = item.get("name", "").strip()
        sur = item.get("surName", "").strip()

        # Пропускаем явные заглушки
        check_str = f"{last} {first} {sur}".lower()
        if any(junk in check_str for junk in JUNK_WORDS):
            continue

        # Пропускаем странные короткие записи вроде "Х1 1 1"
        if len(last) < 2 or len(first) < 2:
            continue

        # Собираем красивое ФИО: "Иванов Иван Иванович"
        # capitalize() / title() страхует от кривого регистра
        full_name = f"{last.capitalize()} {first.capitalize()} {sur.capitalize()}".strip()

        # Заготовка: (id, ФИО, Кафедра по умолчанию, пустые особенности)
        cleaned_teachers.append((t_id, full_name, "КГЭУ", ""))

    print(
        f"🔍 Найдено валидных преподавателей: {len(cleaned_teachers)} (отсеяно {len(raw_teachers) - len(cleaned_teachers)} мусорных)")

    # 3. Загружаем пачкой в SQLite через executemany
    async with connect(DB_PATH) as db:
        # Убеждаемся, что таблица существует
        await db.execute("""
            CREATE TABLE IF NOT EXISTS teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT UNIQUE NOT NULL,
                department TEXT,
                notes TEXT
            );
        """)

        # INSERT OR IGNORE пропустит дубликаты
        await db.executemany("""
            INSERT OR IGNORE INTO teachers (id, full_name, department, notes)
            VALUES (?, ?, ?, ?);
        """, cleaned_teachers)

        await db.commit()

    print(f"🚀 УСПЕХ! Вся база преподавателей КГЭУ загружена в bot.db!")


if __name__ == '__main__':
    asyncio.run(import_teachers())