from aiosqlite import connect
from pathlib import Path
from datetime import date

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / 'storage' / 'bot.db'


# ================= 1. ИНИЦИАЛИЗАЦИЯ ТАБЛИЦ =================

async def init_knowledge_base():
    async with connect(DB_PATH) as db:
        await db.executescript("""
            -- Преподаватели (Общевузовская база)
            CREATE TABLE IF NOT EXISTS teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT UNIQUE NOT NULL,
                department TEXT,
                notes TEXT
            );

            -- Отзывы на преподавателей (с колонкой модерации is_approved)
            CREATE TABLE IF NOT EXISTS teacher_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER,
                author_id INTEGER,
                review_text TEXT,
                rating INTEGER DEFAULT 5,
                created_at TEXT,
                is_approved INTEGER DEFAULT 0,
                FOREIGN KEY (teacher_id) REFERENCES teachers(id)
            );

            -- Предметы конкретной группы (Википедия группы)
            CREATE TABLE IF NOT EXISTS group_subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT NOT NULL,
                subject_name TEXT NOT NULL,
                teacher_name TEXT,
                exam_type TEXT DEFAULT 'Не указано',
                conspect TEXT DEFAULT 'Не указано',
                group_notes TEXT DEFAULT 'Заметок пока нет. Нажми кнопку ниже, чтобы добавить первую!',
                updated_by TEXT DEFAULT 'Система',
                UNIQUE(group_name, subject_name)
            );
        """)

        # Мягкая миграция: добавляет колонку is_approved, если таблица была создана раньше
        try:
            await db.execute("ALTER TABLE teacher_reviews ADD COLUMN is_approved INTEGER DEFAULT 0;")
        except Exception:
            pass  # Колонка уже существует


        await db.commit()


# ================= 2. ФУНКЦИИ ДЛЯ ПРЕДМЕТОВ ГРУППЫ =================

async def get_group_subjects(group_name: str) -> list:
    """Возвращает список предметов конкретной группы с их ID"""
    async with connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT id, subject_name FROM group_subjects 
            WHERE group_name = ? 
            ORDER BY subject_name ASC
        """, (group_name,))
        return await cursor.fetchall()


async def get_group_subject_details(group_name: str, subject_name: str):
    """Возвращает полную карточку предмета группы"""
    async with connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT subject_name, teacher_name, exam_type, conspect, group_notes, updated_by 
            FROM group_subjects 
            WHERE group_name = ? AND subject_name = ?
        """, (group_name, subject_name))
        return await cursor.fetchone()


async def update_group_subject_notes(group_name: str, subject_name: str, new_notes: str, updated_by: str):
    """Обновляет заметки одногруппников по предмету"""
    async with connect(DB_PATH) as db:
        await db.execute("""
            UPDATE group_subjects 
            SET group_notes = ?, updated_by = ? 
            WHERE group_name = ? AND subject_name = ?
        """, (new_notes, updated_by, group_name, subject_name))
        await db.commit()


# ================= 3. ФУНКЦИИ ДЛЯ ПРЕПОДАВАТЕЛЕЙ (PROPREPODA) =================

async def get_all_teachers() -> list:
    """Возвращает список всех преподавателей вуза"""
    async with connect(DB_PATH) as db:
        cursor = await db.execute("SELECT id, full_name, department FROM teachers ORDER BY full_name ASC")
        return await cursor.fetchall()


async def search_teachers(query: str, limit: int = 15) -> list:
    """Умный регистронезависимый поиск преподавателей по любой части ФИО"""
    query_lower = query.strip().lower()

    async with connect(DB_PATH) as db:
        cursor = await db.execute("SELECT id, full_name, department FROM teachers")
        rows = await cursor.fetchall()

    # Фильтрация в Python для 100% поддержки кириллицы в любом регистре
    matched = [
        row for row in rows
        if query_lower in row[1].lower()
    ]

    matched.sort(key=lambda x: x[1])
    return matched[:limit]


async def get_teacher_dossier(teacher_id: int):
    """Досье препода: инфо + средний рейтинг из ОДОБРЕННЫХ отзывов"""
    async with connect(DB_PATH) as db:
        cursor = await db.execute("SELECT full_name, department, notes FROM teachers WHERE id = ?", (teacher_id,))
        teacher = await cursor.fetchone()

        if not teacher:
            return None

        # Считаем средний балл только среди одобренных отзывов (is_approved = 1)
        cursor_rating = await db.execute("""
            SELECT AVG(rating), COUNT(id) 
            FROM teacher_reviews 
            WHERE teacher_id = ? AND is_approved = 1
        """, (teacher_id,))
        avg_rating, reviews_count = await cursor_rating.fetchone()

        return {
            "full_name": teacher[0],
            "department": teacher[1],
            "notes": teacher[2],
            "avg_rating": round(avg_rating or 5.0, 1),
            "reviews_count": reviews_count or 0
        }


async def get_teacher_reviews(teacher_id: int) -> list:
    """Возвращает последние 5 ОДОБРЕННЫХ отзывов на преподавателя"""
    async with connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT review_text, rating, created_at 
            FROM teacher_reviews 
            WHERE teacher_id = ? AND is_approved = 1
            ORDER BY id DESC LIMIT 5
        """, (teacher_id,))
        return await cursor.fetchall()


async def get_all_teacher_reviews(teacher_id: int) -> list:
    """Достает абсолютно все ОДОБРЕННЫЕ отзывы на преподавателя"""
    async with connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT review_text, rating, created_at 
            FROM teacher_reviews 
            WHERE teacher_id = ? AND is_approved = 1
            ORDER BY id DESC
        """, (teacher_id,))
        return await cursor.fetchall()


# ================= 4. СИСТЕМА МОДЕРАЦИИ ОТЗЫВОВ =================

async def add_teacher_review(teacher_id: int, author_id: int, text: str, rating: int) -> int:
    """Сохраняет отзыв на модерацию (is_approved = 0) и возвращает ID созданного отзыва"""
    today = date.today().strftime("%Y-%m-%d")
    async with connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO teacher_reviews (teacher_id, author_id, review_text, rating, created_at, is_approved)
            VALUES (?, ?, ?, ?, ?, 0)
        """, (teacher_id, author_id, text, rating, today))
        await db.commit()
        return cursor.lastrowid


async def approve_review(review_id: int):
    """Одобряет отзыв администратором (становится виден всем)"""
    async with connect(DB_PATH) as db:
        await db.execute("UPDATE teacher_reviews SET is_approved = 1 WHERE id = ?", (review_id,))
        await db.commit()


async def reject_review(review_id: int):
    """Отклоняет и удаляет отзыв администратором"""
    async with connect(DB_PATH) as db:
        await db.execute("DELETE FROM teacher_reviews WHERE id = ?", (review_id,))
        await db.commit()

async def get_group_subject_by_id(subject_id: int):
    """Возвращает карточку предмета по его ID"""
    async with connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT id, subject_name, teacher_name, exam_type, conspect, group_notes, updated_by, group_name 
            FROM group_subjects 
            WHERE id = ?
        """, (subject_id,))
        return await cursor.fetchone()

async def update_group_subject_notes_by_id(subject_id: int, new_notes: str, updated_by: str):
    """Обновляет заметки по ID предмета"""
    async with connect(DB_PATH) as db:
        await db.execute("""
            UPDATE group_subjects 
            SET group_notes = ?, updated_by = ? 
            WHERE id = ?
        """, (new_notes, updated_by, subject_id))
        await db.commit()