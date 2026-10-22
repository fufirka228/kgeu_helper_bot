from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiosqlite import connect

from database.db_students import DB_PATH
from database.db_deadlines import get_burning_deadlines
from bot.formatters import get_urgency_info


async def send_evening_notifications(bot: Bot):
    print("🔔 Запуск вечерней рассылки дедлайнов...")

    # 1. Достаем всех зарегистрированных студентов
    async with connect(DB_PATH) as db:
        cursor = await db.execute("SELECT tg_id, group_name FROM students WHERE notifications_enabled = 1")
        students = await cursor.fetchall()

    # 2. Проверяем каждого студента
    for tg_id, group_name in students:
        burning_tasks = await get_burning_deadlines(group_name, tg_id)

        # Если на завтра нет горящих дел — не спамим студенту!
        if not burning_tasks:
            continue

        text = (
            f"🔔 <b>НАПОМИНАНИЕ О ДЕДЛАЙНАХ</b> • <code>{group_name}</code>\n\n"
            f"⚠️ <b>Задания на ближайшие 3 дня:</b>\n\n"
        )

        for subject, title, due_date in burning_tasks:
            badge, urgency_text = get_urgency_info(due_date)
            text += f"{badge} <b>{subject}</b> — {title} (<i>{urgency_text}</i>)\n"

        text += "\n<i>Не откладывай на последний момент!</i>"

        try:
            await bot.send_message(chat_id=tg_id, text=text, parse_mode="HTML")
        except TelegramForbiddenError:
            print(f"Пользователь {tg_id} заблокировал бота, пропускаем.")
        except Exception as e:
            print(f"Ошибка отправки пользователю {tg_id}: {e}")