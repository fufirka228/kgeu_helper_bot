from aiosqlite import connect
from pathlib import Path
import secrets
import sqlite3

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / 'storage'
DB_PATH = STORAGE_DIR / 'bot.db'


async def init_db():
    async with connect(DB_PATH) as db:
        await db.executescript('''
            -- 1. Таблица студентов
            CREATE TABLE IF NOT EXISTS students (
                tg_id INTEGER PRIMARY KEY,
                group_name TEXT NOT NULL,
                username TEXT,
                status TEXT DEFAULT 'pending' -- 'pending' или 'verified'
            );

            -- 2. Таблица дедлайнов группы
            CREATE TABLE IF NOT EXISTS deadlines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT NOT NULL,
                subject TEXT NOT NULL,
                title TEXT NOT NULL,
                due_date TEXT NOT NULL,
                created_by INTEGER
            );

            -- 3. Таблица сданных работ
            CREATE TABLE IF NOT EXISTS student_progress (
                user_id INTEGER,
                deadline_id INTEGER,
                PRIMARY KEY (user_id, deadline_id)
            );

            -- 4. Одноразовые токены активации для первого студента
            CREATE TABLE IF NOT EXISTS group_activations (
                token TEXT PRIMARY KEY,
                group_name TEXT NOT NULL,
                creator_id INTEGER NOT NULL,
                is_used INTEGER DEFAULT 0
            );

            -- 5. Голоса за подтверждение новичков (2 голоса = вход)
            CREATE TABLE IF NOT EXISTS verification_votes (
                candidate_id INTEGER,
                voter_id INTEGER,
                vote INTEGER, -- 1 = Да, -1 = Нет
                PRIMARY KEY (candidate_id, voter_id)
            );
        ''')

        # Мягкие миграции (чтобы не ломать старую базу)
        try:
            await db.execute("ALTER TABLE students ADD COLUMN username TEXT;")
        except sqlite3.OperationalError:
            pass

        try:
            await db.execute("ALTER TABLE students ADD COLUMN status TEXT DEFAULT 'verified';")
        except sqlite3.OperationalError:
            pass

        try:
            await db.execute("ALTER TABLE students ADD COLUMN notifications_enabled INTEGER DEFAULT 1;")
        except sqlite3.OperationalError:
            pass

        try:
            await db.execute("ALTER TABLE students ADD COLUMN is_banned INTEGER DEFAULT 0;")
        except sqlite3.OperationalError:
            pass

        await db.commit()


# ================= РАБОТА СО СТУДЕНТАМИ =================

async def add_student(tg_id: int, group_name: str, username: str, status: str = 'pending'):
    async with connect(DB_PATH) as db:
        query = '''
            INSERT INTO students (tg_id, group_name, username, status) 
            VALUES (?, ?, ?, ?)
            ON CONFLICT(tg_id) DO UPDATE SET 
                group_name=excluded.group_name, 
                username=excluded.username,
                status=excluded.status
        '''
        await db.execute(query, (tg_id, group_name, username, status))
        await db.commit()


async def get_student(tg_id: int) -> str | None:
    """Возвращает название группы студента"""
    async with connect(DB_PATH) as db:
        cursor = await db.execute('SELECT group_name FROM students WHERE tg_id = ?', (tg_id,))
        row = await cursor.fetchone()
        return row[0] if row else None


async def get_student_profile(tg_id: int):
    """Возвращает полный профиль (группа, статус, юзернейм)"""
    async with connect(DB_PATH) as db:
        cursor = await db.execute('SELECT group_name, status, username FROM students WHERE tg_id = ?', (tg_id,))
        row = await cursor.fetchone()
        if row:
            return {"group_name": row[0], "status": row[1], "username": row[2]}
        return None


async def get_verified_students_count(group_name: str) -> int:
    """Сколько подтвержденных студентов уже есть в группе"""
    async with connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(tg_id) FROM students WHERE group_name = ? AND status = 'verified'",
                                  (group_name,))
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_verified_group_members(group_name: str, exclude_id: int) -> list[int]:
    """Список ID подтвержденных одногруппников для отправки опроса"""
    async with connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT tg_id FROM students WHERE group_name = ? AND status = 'verified' AND tg_id != ?",
            (group_name, exclude_id))
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


# ================= АКТИВАЦИЯ И ГОЛОСОВАНИЕ =================

async def create_activation_token(group_name: str, creator_id: int) -> str:
    """Генерирует токен СРАЗУ с префиксом act_"""
    token = f"act_{secrets.token_urlsafe(8)}"  # Будет выглядеть как: act_aB9_xZ2q
    async with connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO group_activations (token, group_name, creator_id, is_used)
            VALUES (?, ?, ?, 0)
        """, (token, group_name, creator_id))
        await db.commit()
    return token


async def use_activation_token(token: str, second_user_id: int, second_username: str):
    """Активирует группу при переходе второго студента"""
    async with connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT group_name, creator_id, is_used FROM group_activations WHERE token = ?",
            (token,)
        )
        row = await cursor.fetchone()

        # Если токена нет или он уже сожжен
        if not row or row[2] == 1:
            return None

        group_name, creator_id, _ = row

        # ЗАЩИТА: нельзя активировать группу самому себе!
        if creator_id == second_user_id:
            return "self_click"

        # 1. Сжигаем токен (он больше никогда не сработает)
        await db.execute("UPDATE group_activations SET is_used = 1 WHERE token = ?", (token,))

        # 2. Подтверждаем первого студента (создателя)
        await db.execute("UPDATE students SET status = 'verified' WHERE tg_id = ?", (creator_id,))

        # 3. Регистрируем и подтверждаем второго студента
        await db.execute("""
            INSERT INTO students (tg_id, group_name, username, status)
            VALUES (?, ?, ?, 'verified')
            ON CONFLICT(tg_id) DO UPDATE SET group_name=excluded.group_name, status='verified'
        """, (second_user_id, group_name, second_username))

        await db.commit()
        return group_name, creator_id


async def vote_for_student(candidate_id: int, voter_id: int, vote: int) -> int:
    """
    Записывает голос за студента.
    Возвращает текущее количество голосов 'ДА'.
    """
    async with connect(DB_PATH) as db:
        # Записываем или обновляем голос
        await db.execute("""
            INSERT OR REPLACE INTO verification_votes (candidate_id, voter_id, vote)
            VALUES (?, ?, ?)
        """, (candidate_id, voter_id, vote))

        # Считаем количество голосов "Да" (vote = 1)
        cursor = await db.execute("SELECT COUNT(*) FROM verification_votes WHERE candidate_id = ? AND vote = 1",
                                  (candidate_id,))
        yes_count = (await cursor.fetchone())[0]

        # Если набралось 2 голоса "Да" — автоматически подтверждаем кандидата!
        if yes_count >= 2:
            await db.execute("UPDATE students SET status = 'verified' WHERE tg_id = ?", (candidate_id,))

        await db.commit()
        return yes_count

# 2. Получение полной статистики студента для профиля
async def get_student_stats(user_id: int):
    async with connect(DB_PATH) as db:
        # Профиль
        cursor = await db.execute("""
            SELECT group_name, status, username, notifications_enabled 
            FROM students WHERE tg_id = ?
        """, (user_id,))
        profile_row = await cursor.fetchone()

        if not profile_row:
            return None

        group_name, status, username, notify_enabled = profile_row

        # Считаем, сколько дедлайнов закрыл
        cursor_tasks = await db.execute("SELECT COUNT(*) FROM student_progress WHERE user_id = ?", (user_id,))
        completed_tasks = (await cursor_tasks.fetchone())[0]

        # Считаем, сколько отзывов написал
        cursor_rev = await db.execute("SELECT COUNT(*) FROM teacher_reviews WHERE author_id = ?", (user_id,))
        reviews_count = (await cursor_rev.fetchone())[0]

        return {
            "group_name": group_name,
            "status": status,
            "username": username,
            "notify_enabled": notify_enabled if notify_enabled is not None else 1,
            "completed_tasks": completed_tasks,
            "reviews_count": reviews_count
        }


# 3. Переключатель уведомлений (ВКЛ / ВЫКЛ)
async def toggle_student_notifications(user_id: int) -> int:
    async with connect(DB_PATH) as db:
        cursor = await db.execute("SELECT notifications_enabled FROM students WHERE tg_id = ?", (user_id,))
        row = await cursor.fetchone()
        current = row[0] if (row and row[0] is not None) else 1

        # Инвертируем: 1 -> 0, 0 -> 1
        new_state = 0 if current == 1 else 1

        await db.execute("UPDATE students SET notifications_enabled = ? WHERE tg_id = ?", (new_state, user_id))
        await db.commit()
        return new_state


# 4. Смена группы со сбросом статуса в 'pending' (Защита от прыжков по группам!)
async def change_student_group_in_db(user_id: int, new_group: str):
    async with connect(DB_PATH) as db:
        # Сбрасываем статус в pending, так как в новой группе человека еще никто не подтверждал!
        await db.execute("""
            UPDATE students 
            SET group_name = ?, status = 'pending' 
            WHERE tg_id = ?
        """, (new_group, user_id))
        # Очищаем старые голоса за этого студента
        await db.execute("DELETE FROM verification_votes WHERE candidate_id = ?", (user_id,))
        await db.commit()

async def get_admin_dashboard_stats() -> dict:
    """Собирает цифры статистики для дашборда админа"""
    async with connect(DB_PATH) as db:
        # Всего студентов
        cursor = await db.execute("SELECT COUNT(*) FROM students")
        total_students = (await cursor.fetchone())[0]

        # Подтвержденных студентов
        cursor_v = await db.execute("SELECT COUNT(*) FROM students WHERE status = 'verified'")
        verified_students = (await cursor_v.fetchone())[0]

        # Всего дедлайнов
        cursor_d = await db.execute("SELECT COUNT(*) FROM deadlines")
        total_deadlines = (await cursor_d.fetchone())[0]

        # Отзывов на модерации
        cursor_rev = await db.execute("SELECT COUNT(*) FROM teacher_reviews WHERE is_approved = 0")
        pending_reviews = (await cursor_rev.fetchone())[0]

        return {
            "total_students": total_students,
            "verified_students": verified_students,
            "total_deadlines": total_deadlines,
            "pending_reviews": pending_reviews
        }


async def get_all_student_ids() -> list[int]:
    """Возвращает список ID всех пользователей для массовой рассылки"""
    async with connect(DB_PATH) as db:
        cursor = await db.execute("SELECT tg_id FROM students")
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

async def find_student_by_id_or_username(query: str):
    """Ищет студента по ID (12345678) или по юзернейму (@username)"""
    clean_query = query.strip().replace("@", "")
    async with connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT tg_id, group_name, username, status, is_banned 
            FROM students 
            WHERE CAST(tg_id AS TEXT) = ? OR LOWER(username) LIKE ?
        """, (clean_query, f"%{clean_query.lower()}%"))
        return await cursor.fetchone()


async def admin_set_student_verified(tg_id: int):
    """Принудительно подтверждает студента админом"""
    async with connect(DB_PATH) as db:
        await db.execute("UPDATE students SET status = 'verified' WHERE tg_id = ?", (tg_id,))
        await db.commit()


async def admin_change_student_group(tg_id: int, new_group: str):
    """Админ меняет группу студента с сохранением статуса verified"""
    async with connect(DB_PATH) as db:
        await db.execute("UPDATE students SET group_name = ?, status = 'verified' WHERE tg_id = ?", (new_group, tg_id))
        await db.commit()


async def admin_toggle_ban_student(tg_id: int) -> int:
    """Переключатель бана: забанить / разбанить студента"""
    async with connect(DB_PATH) as db:
        cursor = await db.execute("SELECT is_banned FROM students WHERE tg_id = ?", (tg_id,))
        row = await cursor.fetchone()
        current_ban = row[0] if (row and row[0] is not None) else 0

        new_ban_state = 0 if current_ban == 1 else 1
        await db.execute("UPDATE students SET is_banned = ? WHERE tg_id = ?", (new_ban_state, tg_id))
        await db.commit()
        return new_ban_state


async def is_student_banned(tg_id: int) -> bool:
    """Проверяет, забанен ли студент"""
    async with connect(DB_PATH) as db:
        cursor = await db.execute("SELECT is_banned FROM students WHERE tg_id = ?", (tg_id,))
        row = await cursor.fetchone()
        return bool(row[0]) if (row and row[0] is not None) else False

async def get_admin_groups_summary() -> list:
    """Возвращает список всех групп с количеством студентов в каждой"""
    async with connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT group_name, COUNT(tg_id), SUM(CASE WHEN status = 'verified' THEN 1 ELSE 0 END)
            FROM students
            GROUP BY group_name
            ORDER BY COUNT(tg_id) DESC
        """)
        return await cursor.fetchall()


async def get_students_in_group(group_name: str) -> list:
    """Возвращает список всех студентов конкретной группы"""
    async with connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT tg_id, username, status, is_banned 
            FROM students 
            WHERE group_name = ? 
            ORDER BY status DESC, tg_id ASC
        """, (group_name,))
        return await cursor.fetchall()

async def admin_delete_student(tg_id: int):
    """Полностью стирает студента и всю его историю из базы данных"""
    async with connect(DB_PATH) as db:
        await db.execute("DELETE FROM students WHERE tg_id = ?", (tg_id,))
        await db.execute("DELETE FROM student_progress WHERE user_id = ?", (tg_id,))
        await db.execute("DELETE FROM verification_votes WHERE candidate_id = ? OR voter_id = ?", (tg_id, tg_id))
        await db.commit()