from aiosqlite import connect
from pathlib import Path
from datetime import date, timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / 'storage'
DB_PATH = STORAGE_DIR / 'bot.db'

async def add_deadline(group_name: str, subject: str, title: str, due_date: str, created_by: int):
    async with connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO deadlines (group_name, subject, title, due_date, created_by)
            VALUES (?, ?, ?, ?, ?)
        """, (group_name, subject, title, due_date, created_by))
        await db.commit()

async def get_group_deadlines(group_name: str):
    """Достает дедлайны группы ВМЕСТЕ с юзернеймом автора (через JOIN)"""
    async with connect(DB_PATH) as db:
        cursor = await db.execute('''
            SELECT d.id, d.subject, d.title, d.due_date, d.created_by, s.username
            FROM deadlines d
            LEFT JOIN students s ON d.created_by = s.tg_id
            WHERE d.group_name = ?
            ORDER BY d.due_date ASC
        ''', (group_name,))
        return await cursor.fetchall()

async def get_student_completed_ids(user_id: int) -> set[int]:
    async with connect(DB_PATH) as db:
        cursor = await db.execute('''
            SELECT deadline_id FROM student_progress WHERE user_id = ?
        ''', (user_id,))
        rows = await cursor.fetchall()
        return {row[0] for row in rows}

async def toggle_deadline_status(user_id: int, deadline_id: int):
    async with connect(DB_PATH) as db:
        cursor = await db.execute('''
            SELECT 1 FROM student_progress WHERE user_id = ? AND deadline_id = ?
        ''', (user_id, deadline_id))
        exists = await cursor.fetchone()

        if exists:
            await db.execute('''
                DELETE FROM student_progress WHERE user_id = ? AND deadline_id = ?
            ''', (user_id, deadline_id))
        else:
            await db.execute('''
                INSERT INTO student_progress (user_id, deadline_id) VALUES (?, ?)
            ''', (user_id, deadline_id))

        await db.commit()

async def get_burning_deadlines(group_name: str, user_id: int, days_ahead: int = 3) -> list:
    today = date.today().strftime("%Y-%m-%d")
    max_date = (date.today() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    async with connect(DB_PATH) as db:
        cursor = await db.execute("""
                SELECT subject, title, due_date 
                FROM deadlines 
                WHERE group_name = ? 
                  AND due_date BETWEEN ? AND ?
                  AND id NOT IN (
                      SELECT deadline_id FROM student_progress WHERE user_id = ?
                  )
                ORDER BY due_date ASC
            """, (group_name, today, max_date, user_id))
        return await cursor.fetchall()


async def delete_deadline(deadline_id: int, user_id: int) -> bool:
    async with connect(DB_PATH) as db:
        cursor = await db.execute("SELECT created_by FROM deadlines WHERE id = ?", (deadline_id,))
        row = await cursor.fetchone()

        if not row:
            return False

        creator_id = row[0]

        if creator_id != user_id:
            return False

        await db.execute("DELETE FROM deadlines WHERE id = ?", (deadline_id,))
        await db.execute("DELETE FROM student_progress WHERE deadline_id = ?", (deadline_id,))
        await db.commit()
        return True