import os
import html
import asyncio
from pathlib import Path
from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
import os
import html
import asyncio
from pathlib import Path
from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from database.db_teachers import approve_review, reject_review, get_all_teacher_reviews
from database.db_students import get_admin_dashboard_stats, get_all_student_ids
from bot.keyboards import get_admin_panel_keyboard, get_broadcast_confirm_keyboard

router = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
STUDENT_BOT_TOKEN = os.getenv("BOT_TOKEN")
CONSOLE_LOG_PATH = Path(__file__).resolve().parent.parent / "storage" / "console.log"


# FSM состояния для админа
class AdminFSM(StatesGroup):
    waiting_for_reply_text = State()
    waiting_for_broadcast_content = State()


# ================= 1. КОМАНДА /ADMIN И /START В АДМИН-БОТЕ =================

@router.message(Command("admin"))
@router.message(Command("start"))
async def show_admin_panel(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ У вас нет прав администратора.")
        return

    await state.clear()
    stats = await get_admin_dashboard_stats()

    text = (
        f"🛠 <b>ПАНЕЛЬ АДМИНИСТРИРОВАНИЯ KGEU HELPER</b>\n\n"
        f"<blockquote>"
        f"👥 <b>Всего студентов:</b> <code>{stats['total_students']}</code>\n"
        f"🛡 <b>Подтвержденных:</b> <code>{stats['verified_students']}</code>\n"
        f"📅 <b>Активных дедлайнов:</b> <code>{stats['total_deadlines']}</code>\n"
        f"⏳ <b>Отзывов на модерации:</b> <code>{stats['pending_reviews']}</code>"
        f"</blockquote>\n\n"
        f"<i>Выберите действие в меню ниже:</i>"
    )

    keyboard = get_admin_panel_keyboard(stats['pending_reviews'])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "admin_stats")
async def refresh_admin_stats(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    stats = await get_admin_dashboard_stats()
    text = (
        f"🛠 <b>ПАНЕЛЬ АДМИНИСТРИРОВАНИЯ KGEU HELPER</b>\n\n"
        f"<blockquote>"
        f"👥 <b>Всего студентов:</b> <code>{stats['total_students']}</code>\n"
        f"🛡 <b>Подтвержденных:</b> <code>{stats['verified_students']}</code>\n"
        f"📅 <b>Активных дедлайнов:</b> <code>{stats['total_deadlines']}</code>\n"
        f"⏳ <b>Отзывов на модерации:</b> <code>{stats['pending_reviews']}</code>"
        f"</blockquote>\n\n"
        f"<i>Статистика обновлена.</i>"
    )

    keyboard = get_admin_panel_keyboard(stats['pending_reviews'])
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("Данные обновлены! 📊")


# ================= 2. МАССОВАЯ РАССЫЛКА ПО СТУДЕНТАМ =================

@router.callback_query(F.data == "admin_start_broadcast")
async def start_broadcast_prompt(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return

    await callback.message.answer(
        "📢 <b>Массовая рассылка по всем студентам КГЭУ:</b>\n\n"
        "Пришли сообщение (текст, фото или комбинацию), которое увидят <b>ВСЕ зарегистрированные пользователи</b>.\n\n"
        "<i>Поддерживается HTML-разметка!</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_broadcast")]
        ])
    )
    await state.set_state(AdminFSM.waiting_for_broadcast_content)
    await callback.answer()


@router.message(AdminFSM.waiting_for_broadcast_content)
async def preview_broadcast_message(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    # Сохраняем ID сообщения для копирования
    await state.update_data(
        broadcast_msg_id=message.message_id,
        broadcast_chat_id=message.chat.id
    )

    await message.answer(
        "🔎 <b>ПРЕДПРОСМОТР РАССЫЛКИ:</b>\nвыше отображается твое сообщение.\n\n"
        "Отправить его всем студентам?",
        reply_markup=get_broadcast_confirm_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "confirm_broadcast")
async def execute_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()
    msg_id = data.get("broadcast_msg_id")
    from_chat_id = data.get("broadcast_chat_id")
    await state.clear()

    student_ids = await get_all_student_ids()
    await callback.message.edit_text(f"⏳ <b>Запуск рассылки по {len(student_ids)} студентам...</b>", parse_mode="HTML")

    success = 0
    failed = 0

    if STUDENT_BOT_TOKEN:
        async with Bot(token=STUDENT_BOT_TOKEN) as student_bot:
            for user_id in student_ids:
                try:
                    # Скопировать сообщение 1 в 1
                    await student_bot.copy_message(
                        chat_id=user_id,
                        from_chat_id=from_chat_id,
                        message_id=msg_id
                    )
                    success += 1
                    await asyncio.sleep(0.05)  # Пауза против лимитов Telegram
                except TelegramForbiddenError:
                    failed += 1
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                except Exception:
                    failed += 1

    await callback.message.answer(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📈 Успешно доставлено: <code>{success}</code>\n"
        f"📉 Не доставлено (заблокировали бота): <code>{failed}</code>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_broadcast")
async def cancel_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Рассылка отменена.")
    await callback.answer()


# ================= 3. ЛОГИ И КОНСОЛЬ =================

@router.callback_query(F.data == "admin_show_logs")
@router.message(Command("logs"))
async def show_bot_console_output(event: types.Message | types.CallbackQuery):
    user_id = event.from_user.id
    if user_id != ADMIN_ID:
        return

    message = event if isinstance(event, types.Message) else event.message

    if not CONSOLE_LOG_PATH.exists():
        await message.answer("⚠️ Файл логов пока пуст.")
        return

    try:
        with open(CONSOLE_LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
            last_lines = "".join(lines[-25:])

        safe_output = html.escape(last_lines)
        if len(safe_output) > 3500:
            safe_output = safe_output[-3500:]

        download_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Скачать полный console.log", callback_data="download_console_logs")]
        ])

        await message.answer(
            f"🖥 <b>ВЫВОД КОНСОЛИ PYTHON:</b>\n\n<pre><code>{safe_output}</code></pre>",
            reply_markup=download_kb,
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка чтения логов: {e}")

    if isinstance(event, types.CallbackQuery):
        await event.answer()


@router.callback_query(F.data == "download_console_logs")
async def send_full_console_file(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    if not CONSOLE_LOG_PATH.exists():
        await callback.answer("Файл пуст!", show_alert=True)
        return

    await callback.answer("Отправляю...")
    log_doc = FSInputFile(CONSOLE_LOG_PATH, filename="console_output.txt")
    await callback.message.answer_document(
        document=log_doc,
        caption="📄 <b>Полная копия вывода терминала Python.</b>",
        parse_mode="HTML"
    )


# ================= 4. МОДЕРАЦИЯ И ПОДДЕРЖКА =================

@router.callback_query(F.data.startswith("mod_appr_"))
async def admin_approve_review(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    review_id = int(callback.data.split("_")[2])
    await approve_review(review_id)
    await callback.message.edit_text(callback.message.html_text + "\n\n✅ <b>ОДОБРЕНО И ОПУБЛИКОВАНО</b>", parse_mode="HTML")
    await callback.answer("Отзыв опубликован!")


@router.callback_query(F.data.startswith("mod_rej_"))
async def admin_reject_review(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    review_id = int(callback.data.split("_")[2])
    await reject_review(review_id)
    await callback.message.edit_text(callback.message.html_text + "\n\n❌ <b>ОТКЛОНЕНО И УДАЛЕНО</b>", parse_mode="HTML")
    await callback.answer("Отзыв удален!")


@router.callback_query(F.data.startswith("reply_user_"))
async def start_admin_reply(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return

    target_user_id = int(callback.data.split("_")[2])
    await state.update_data(target_student_id=target_user_id)

    cancel_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="cancel_admin_reply")]
    ])

    await callback.message.answer(
        f"✍️ <b>Введи текст ответа для студента (ID: <code>{target_user_id}</code>):</b>",
        reply_markup=cancel_btn,
        parse_mode="HTML"
    )
    await state.set_state(AdminFSM.waiting_for_reply_text)
    await callback.answer()


@router.callback_query(F.data == "cancel_admin_reply")
async def cancel_admin_reply(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Ответ отменен.")
    await callback.answer()


@router.message(AdminFSM.waiting_for_reply_text)
async def process_send_reply_to_student(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()
    target_student_id = data["target_student_id"]
    reply_text = html.escape(message.text.strip())
    await state.clear()

    student_message = (
        f"👨‍💻 <b>ОТВЕТ СЛУЖБЫ ПОДДЕРЖКИ:</b>\n\n"
        f"<blockquote>💬 «{reply_text}»</blockquote>"
    )

    try:
        async with Bot(token=STUDENT_BOT_TOKEN) as student_bot:
            await student_bot.send_message(chat_id=target_student_id, text=student_message, parse_mode="HTML")
        await message.answer(f"✅ <b>Ответ отправлен студенту (ID: <code>{target_student_id}</code>)!</b>", parse_mode="HTML")
    except TelegramForbiddenError:
        await message.answer("❌ Студент заблокировал бота.")
    except Exception as e:
        await message.answer(f"❌ Ошибка отправки: {e}")

from database.db_teachers import approve_review, reject_review, get_all_teacher_reviews
from database.db_students import get_admin_dashboard_stats, get_all_student_ids
from bot.keyboards import get_admin_panel_keyboard, get_broadcast_confirm_keyboard

router = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
STUDENT_BOT_TOKEN = os.getenv("BOT_TOKEN")
CONSOLE_LOG_PATH = Path(__file__).resolve().parent.parent / "storage" / "console.log"


# FSM состояния для админа
class AdminFSM(StatesGroup):
    waiting_for_reply_text = State()
    waiting_for_broadcast_content = State()


# ================= 1. КОМАНДА /ADMIN И /START В АДМИН-БОТЕ =================

@router.message(Command("admin"))
@router.message(Command("start"))
async def show_admin_panel(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ У вас нет прав администратора.")
        return

    await state.clear()
    stats = await get_admin_dashboard_stats()

    text = (
        f"🛠 <b>ПАНЕЛЬ АДМИНИСТРИРОВАНИЯ KGEU HELPER</b>\n\n"
        f"<blockquote>"
        f"👥 <b>Всего студентов:</b> <code>{stats['total_students']}</code>\n"
        f"🛡 <b>Подтвержденных:</b> <code>{stats['verified_students']}</code>\n"
        f"📅 <b>Активных дедлайнов:</b> <code>{stats['total_deadlines']}</code>\n"
        f"⏳ <b>Отзывов на модерации:</b> <code>{stats['pending_reviews']}</code>"
        f"</blockquote>\n\n"
        f"<i>Выберите действие в меню ниже:</i>"
    )

    keyboard = get_admin_panel_keyboard(stats['pending_reviews'])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "admin_stats")
async def refresh_admin_stats(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    stats = await get_admin_dashboard_stats()
    text = (
        f"🛠 <b>ПАНЕЛЬ АДМИНИСТРИРОВАНИЯ KGEU HELPER</b>\n\n"
        f"<blockquote>"
        f"👥 <b>Всего студентов:</b> <code>{stats['total_students']}</code>\n"
        f"🛡 <b>Подтвержденных:</b> <code>{stats['verified_students']}</code>\n"
        f"📅 <b>Активных дедлайнов:</b> <code>{stats['total_deadlines']}</code>\n"
        f"⏳ <b>Отзывов на модерации:</b> <code>{stats['pending_reviews']}</code>"
        f"</blockquote>\n\n"
        f"<i>Статистика обновлена.</i>"
    )

    keyboard = get_admin_panel_keyboard(stats['pending_reviews'])
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("Данные обновлены! 📊")


# ================= 2. МАССОВАЯ РАССЫЛКА ПО СТУДЕНТАМ =================

@router.callback_query(F.data == "admin_start_broadcast")
async def start_broadcast_prompt(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return

    await callback.message.answer(
        "📢 <b>Массовая рассылка по всем студентам КГЭУ:</b>\n\n"
        "Пришли сообщение (текст, фото или комбинацию), которое увидят <b>ВСЕ зарегистрированные пользователи</b>.\n\n"
        "<i>Поддерживается HTML-разметка!</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_broadcast")]
        ])
    )
    await state.set_state(AdminFSM.waiting_for_broadcast_content)
    await callback.answer()


@router.message(AdminFSM.waiting_for_broadcast_content)
@router.message(AdminFSM.waiting_for_broadcast_content)
async def preview_broadcast_message(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    # Достаем текст или подпись к фото
    raw_text = message.caption or message.text or ""

    # Достаем фото, если прикреплено
    photo_bytes = None
    if message.photo:
        photo_bytes_io = await message.bot.download(message.photo[-1])
        photo_bytes = photo_bytes_io.read()

    # Сохраняем в память FSM не ID сообщения, а сам текст и байты фото!
    await state.update_data(
        broadcast_text=raw_text,
        broadcast_photo_bytes=photo_bytes
    )

    # Показываем админу предпросмотр
    preview_prompt = "🔎 <b>ПРЕДПРОСМОТР РАССЫЛКИ:</b>\nОтправить это сообщение всем студентам?"

    if photo_bytes:
        input_photo = BufferedInputFile(photo_bytes, filename="preview.jpg")
        await message.answer_photo(
            photo=input_photo,
            caption=f"{preview_prompt}\n\nТекст:\n{raw_text}",
            reply_markup=get_broadcast_confirm_keyboard(),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"{preview_prompt}\n\nТекст:\n{raw_text}",
            reply_markup=get_broadcast_confirm_keyboard(),
            parse_mode="HTML"
        )


# 2. Админ нажал "Подтвердить" -> Студенческий бот делает рассылку
@router.callback_query(F.data == "confirm_broadcast")
async def execute_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()
    b_text = data.get("broadcast_text", "")
    b_photo_bytes = data.get("broadcast_photo_bytes")
    await state.clear()

    student_ids = await get_all_student_ids()
    await callback.message.edit_reply_markup(reply_markup=None)  # Убираем кнопки у предпросмотра
    await callback.message.answer(f"⏳ <b>Запуск рассылки по {len(student_ids)} студентам...</b>", parse_mode="HTML")

    success = 0
    failed = 0

    if STUDENT_BOT_TOKEN:
        async with Bot(token=STUDENT_BOT_TOKEN) as student_bot:
            for user_id in student_ids:
                try:
                    if b_photo_bytes:
                        # Если было фото — шлем фото с подписью
                        input_photo = BufferedInputFile(b_photo_bytes, filename="broadcast.jpg")
                        await student_bot.send_photo(
                            chat_id=user_id,
                            photo=input_photo,
                            caption=b_text,
                            parse_mode="HTML"
                        )
                    else:
                        # Если просто текст — шлем текст
                        await student_bot.send_message(
                            chat_id=user_id,
                            text=b_text,
                            parse_mode="HTML"
                        )
                    success += 1
                    await asyncio.sleep(0.05)  # Пауза против лимитов Telegram (20 собщ/сек)
                except TelegramForbiddenError:
                    failed += 1
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                except Exception as e:
                    print(f"Ошибка рассылки юзеру {user_id}: {e}")
                    failed += 1

    await callback.message.answer(
        f"✅ <b>Рассылка успешно завершена!</b>\n\n"
        f"📈 Доставлено студентам: <code>{success}</code>\n"
        f"📉 Не доставлено (заблокировали бота): <code>{failed}</code>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_broadcast")
async def cancel_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Рассылка отменена.")
    await callback.answer()


# ================= 3. ЛОГИ И КОНСОЛЬ =================

@router.callback_query(F.data == "admin_show_logs")
@router.message(Command("logs"))
async def show_bot_console_output(event: types.Message | types.CallbackQuery):
    user_id = event.from_user.id
    if user_id != ADMIN_ID:
        return

    message = event if isinstance(event, types.Message) else event.message

    if not CONSOLE_LOG_PATH.exists():
        await message.answer("⚠️ Файл логов пока пуст.")
        return

    try:
        with open(CONSOLE_LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
            last_lines = "".join(lines[-25:])

        safe_output = html.escape(last_lines)
        if len(safe_output) > 3500:
            safe_output = safe_output[-3500:]

        download_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Скачать полный console.log", callback_data="download_console_logs")]
        ])

        await message.answer(
            f"🖥 <b>ВЫВОД КОНСОЛИ PYTHON:</b>\n\n<pre><code>{safe_output}</code></pre>",
            reply_markup=download_kb,
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка чтения логов: {e}")

    if isinstance(event, types.CallbackQuery):
        await event.answer()


@router.callback_query(F.data == "download_console_logs")
async def send_full_console_file(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    if not CONSOLE_LOG_PATH.exists():
        await callback.answer("Файл пуст!", show_alert=True)
        return

    await callback.answer("Отправляю...")
    log_doc = FSInputFile(CONSOLE_LOG_PATH, filename="console_output.txt")
    await callback.message.answer_document(
        document=log_doc,
        caption="📄 <b>Полная копия вывода терминала Python.</b>",
        parse_mode="HTML"
    )


# ================= 4. МОДЕРАЦИЯ И ПОДДЕРЖКА =================

@router.callback_query(F.data.startswith("mod_appr_"))
async def admin_approve_review(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    review_id = int(callback.data.split("_")[2])
    await approve_review(review_id)
    await callback.message.edit_text(callback.message.html_text + "\n\n✅ <b>ОДОБРЕНО И ОПУБЛИКОВАНО</b>", parse_mode="HTML")
    await callback.answer("Отзыв опубликован!")


@router.callback_query(F.data.startswith("mod_rej_"))
async def admin_reject_review(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    review_id = int(callback.data.split("_")[2])
    await reject_review(review_id)
    await callback.message.edit_text(callback.message.html_text + "\n\n❌ <b>ОТКЛОНЕНО И УДАЛЕНО</b>", parse_mode="HTML")
    await callback.answer("Отзыв удален!")


@router.callback_query(F.data.startswith("reply_user_"))
async def start_admin_reply(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return

    target_user_id = int(callback.data.split("_")[2])
    await state.update_data(target_student_id=target_user_id)

    cancel_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="cancel_admin_reply")]
    ])

    await callback.message.answer(
        f"✍️ <b>Введи текст ответа для студента (ID: <code>{target_user_id}</code>):</b>",
        reply_markup=cancel_btn,
        parse_mode="HTML"
    )
    await state.set_state(AdminFSM.waiting_for_reply_text)
    await callback.answer()


@router.callback_query(F.data == "cancel_admin_reply")
async def cancel_admin_reply(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Ответ отменен.")
    await callback.answer()


@router.message(AdminFSM.waiting_for_reply_text)
async def process_send_reply_to_student(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()
    target_student_id = data["target_student_id"]
    reply_text = html.escape(message.text.strip())
    await state.clear()

    student_message = (
        f"👨‍💻 <b>ОТВЕТ СЛУЖБЫ ПОДДЕРЖКИ:</b>\n\n"
        f"<blockquote>💬 «{reply_text}»</blockquote>"
    )

    try:
        async with Bot(token=STUDENT_BOT_TOKEN) as student_bot:
            await student_bot.send_message(chat_id=target_student_id, text=student_message, parse_mode="HTML")
        await message.answer(f"✅ <b>Ответ отправлен студенту (ID: <code>{target_student_id}</code>)!</b>", parse_mode="HTML")
    except TelegramForbiddenError:
        await message.answer("❌ Студент заблокировал бота.")
    except Exception as e:
        await message.answer(f"❌ Ошибка отправки: {e}")