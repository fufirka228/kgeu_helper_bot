import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ================= ПЕРЕХВАТЧИК ВЫВОДА КОНСОЛИ PYTHON =================
STORAGE_DIR = Path(__file__).resolve().parent / "storage"
CONSOLE_LOG_FILE = STORAGE_DIR / "console.log"

class ConsoleInterceptor:
    """Дублирует весь вывод print() и ошибок терминала в файл console.log"""
    def __init__(self, file_path, original_stream):
        self.file_path = file_path
        self.original_stream = original_stream

    def write(self, message):
        # 1. Пишем в обычный терминал (как и раньше)
        self.original_stream.write(message)
        self.original_stream.flush()
        # 2. И одновременно дописываем в файл console.log
        if message:
            try:
                with open(self.file_path, "a", encoding="utf-8") as f:
                    f.write(message)
            except Exception:
                pass

    def flush(self):
        self.original_stream.flush()

# Перенаправляем весь вывод Python (и обычный, и ошибки) в наш перехватчик:
sys.stdout = ConsoleInterceptor(CONSOLE_LOG_FILE, sys.stdout)
sys.stderr = ConsoleInterceptor(CONSOLE_LOG_FILE, sys.stderr)
# ====================================================================

from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot import all_handlers_routers
from bot.admin_bot import router as admin_router
from database.db_students import init_db
from bot.notifications import send_evening_notifications
from database.db_teachers import init_knowledge_base
from bot.admin_management import router as admin_management_router

STUDENT_BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_BOT_TOKEN = os.getenv('ADMIN_BOT_TOKEN')


async def main():
    if not STUDENT_BOT_TOKEN or not ADMIN_BOT_TOKEN:
        print("❌ Ошибка: Проверь наличие BOT_TOKEN и ADMIN_BOT_TOKEN в .env!")
        return

    # 1. Создаем двух ботов
    student_bot = Bot(token=STUDENT_BOT_TOKEN)
    admin_bot = Bot(token=ADMIN_BOT_TOKEN)

    # 2. Создаем два диспетчера
    dp_student = Dispatcher()
    dp_student.include_routers(*all_handlers_routers)

    dp_admin = Dispatcher()
    dp_admin.include_routers(admin_router, admin_management_router)

    # Инициализация базы
    await init_db()
    await init_knowledge_base()
    print("✅ База данных подключена")

    await student_bot.delete_webhook(drop_pending_updates=True)
    await admin_bot.delete_webhook(drop_pending_updates=True)

    # Планировщик вечерних рассылок для студентов
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(
        send_evening_notifications,
        trigger="cron",
        hour=20,
        minute=0,
        args=[student_bot]
    )
    scheduler.start()
    print("⏰ Планировщик уведомлений запущен (20:00 МСК)")

    print("🚀 Оба бота (Студенческий и Админский) успешно запущены!")

    # 3. МАГИЯ: запускаем опрос обоих ботов параллельно в одном процессе!
    await asyncio.gather(
        dp_student.start_polling(student_bot),
        dp_admin.start_polling(admin_bot)
    )


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print('\n🛑 Боты остановлены.')