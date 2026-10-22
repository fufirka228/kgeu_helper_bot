from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import html
import os
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.types import BufferedInputFile

from database.db_students import (
    get_student_stats,
    toggle_student_notifications,
    change_student_group_in_db
)
from kgeu_info.group_checking import change_raw_group
from bot.keyboards import get_profile_keyboard, get_main_keyboard

router = Router()

ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")

class ChangeGroupFSM(StatesGroup):
    waiting_for_new_group = State()
    waiting_for_support_text = State()


# 1. Студент нажал "⚙️ Мой профиль" в нижнем меню
@router.message(F.text == "⚙️ Мой профиль")
async def show_profile(message: types.Message):
    user_id = message.from_user.id
    stats = await get_student_stats(user_id)

    if not stats:
        await message.answer("Сначала зарегистрируйся через команду /start!")
        return

    status_badge = "✅ Подтвержден" if stats["status"] == "verified" else "⏳ На проверке"

    profile_text = (
        f"👤 <b>ЛИЧНЫЙ ПРОФИЛЬ СТУДЕНТА</b>\n\n"
        f"<blockquote>"
        f"🎓 <b>Группа:</b> <code>{stats['group_name']}</code>\n"
        f"🛡 <b>Статус:</b> {status_badge}\n"
        f"🆔 <b>Telegram ID:</b> <code>{user_id}</code>\n"
        f"</blockquote>\n"
        f"<blockquote>"
        f"📊 <b>ТВОЯ АКТИВНОСТЬ:</b>\n"
        f"├ 🎯 <b>Сдано дедлайнов:</b> <code>{stats['completed_tasks']}</code>\n"
        f"└ 💬 <b>Написано отзывов:</b> <code>{stats['reviews_count']}</code>\n"
        f"</blockquote>"
    )

    keyboard = get_profile_keyboard(stats["notify_enabled"])
    await message.answer(profile_text, reply_markup=keyboard, parse_mode="HTML")


# 2. Тумблер переключения уведомлений (ВКЛ / ВЫКЛ)
@router.callback_query(F.data == "toggle_notifications")
async def toggle_notify_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    new_state = await toggle_student_notifications(user_id)

    # Обновляем кнопки прямо на месте
    keyboard = get_profile_keyboard(new_state)
    await callback.message.edit_reply_markup(reply_markup=keyboard)

    state_text = "включены 🔔" if new_state == 1 else "выключены 🔕"
    await callback.answer(f"Вечерние уведомления {state_text}!")


# 3. Студент нажал "🔄 Сменить группу"
@router.callback_query(F.data == "change_my_group")
async def start_change_group(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "🔄 <b>Смена учебной группы:</b>\n\n"
        "Введи название своей новой группы (например: <b>ЭП-1-24</b> или <b>ПИ-1-23</b>):\n\n"
        "⚠️ <i>Обрати внимание: после смены группы твой профиль перейдет в статус 'На проверке', "
        "пока новые одногруппники не подтвердят тебя.</i>",
        parse_mode="HTML"
    )
    await state.set_state(ChangeGroupFSM.waiting_for_new_group)
    await callback.answer()


# 4. Ловим ввод новой группы
@router.message(ChangeGroupFSM.waiting_for_new_group)
async def process_new_group_entered(message: types.Message, state: FSMContext):
    new_group = change_raw_group(message.text)

    if not new_group:
        await message.answer(
            "❌ <b>Группа не найдена в официальной базе КГЭУ!</b>\n"
            "Пожалуйста, проверь название и напиши еще раз (пример: <b>ЭП-1-23</b>):",
            parse_mode="HTML"
        )
        return

    user_id = message.from_user.id
    # Меняем группу в базе со сбросом статуса в 'pending'
    await change_student_group_in_db(user_id, new_group)
    await state.clear()

    await message.answer(
        f"✅ <b>Группа успешно изменена на {new_group}!</b>\n\n"
        f"Теперь ты привязан к новой группе. Напиши /start, чтобы обновить данные.",
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "contact_support")
async def start_support_ticket(callback: types.CallbackQuery, state: FSMContext):
    # Кнопка возврата обратно в профиль
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад в профиль", callback_data="cancel_support")]
    ])

    await callback.message.edit_text(
        "💬 <b>Служба поддержки и обратной связи:</b>\n\n"
        "Нашел ошибку? Не совпадает расписание? Есть предложение по улучшению бота?\n\n"
        "Напиши свое сообщение прямо в чат — оно будет передано разработчику бота!",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )
    # Включаем ожидание текста от студента
    await state.set_state(ChangeGroupFSM.waiting_for_support_text)
    await callback.answer()


# 2. НОВЫЙ ХЭНДЛЕР: Студент нажал "⬅️ Назад в профиль" (Отмена тикета)
@router.callback_query(F.data == "cancel_support")
async def cancel_support_callback(callback: types.CallbackQuery, state: FSMContext):
    # ВАЖНО: сбрасываем состояние, чтобы бот не ждал текст сообщения!
    await state.clear()

    user_id = callback.from_user.id
    stats = await get_student_stats(user_id)

    if not stats:
        await callback.answer("Ошибка получения профиля!", show_alert=True)
        return

    status_badge = "✅ Подтвержден" if stats["status"] == "verified" else "⏳ На проверке"

    profile_text = (
        f"👤 <b>ЛИЧНЫЙ ПРОФИЛЬ СТУДЕНТА</b>\n\n"
        f"<blockquote>"
        f"🎓 <b>Группа:</b> <code>{stats['group_name']}</code>\n"
        f"🛡 <b>Статус:</b> {status_badge}\n"
        f"🆔 <b>Telegram ID:</b> <code>{user_id}</code>\n"
        f"</blockquote>\n"
        f"<blockquote>"
        f"📊 <b>ТВОЯ АКТИВНОСТЬ:</b>\n"
        f"├ 🎯 <b>Сдано дедлайнов:</b> <code>{stats['completed_tasks']}</code>\n"
        f"└ 💬 <b>Написано отзывов:</b> <code>{stats['reviews_count']}</code>\n"
        f"</blockquote>"
    )

    keyboard = get_profile_keyboard(stats["notify_enabled"])
    # Возвращаем профиль прямо на месте без спама!
    await callback.message.edit_text(profile_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# 2. Ловим текст проблемы от студента и пересылаем АДМИНУ
@router.message(ChangeGroupFSM.waiting_for_support_text)
async def process_support_text(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    stats = await get_student_stats(user_id)
    group_name = stats["group_name"] if stats else "Не указана"
    author_username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {user_id}"

    # 1. Текст или подпись к фото
    raw_text = message.caption or message.text or "Без текстового описания"
    clean_text = html.escape(raw_text.strip())

    # 2. ЕСЛИ ЕСТЬ ФОТО: скачиваем его байты через Студенческого бота!
    photo_bytes = None
    if message.photo:
        photo_bytes_io = await message.bot.download(message.photo[-1])
        photo_bytes = photo_bytes_io.read()

    await state.clear()

    # Уведомляем студента
    await message.answer(
        "✅ <b>Твое обращение передано в службу поддержки!</b>\n"
        "Мы ответим тебе прямо здесь, в этом чате.",
        parse_mode="HTML"
    )

    # 3. ОТПРАВЛЯЕМ АДМИНУ В АДМИН-БОТ
    current_admin_id = int(os.getenv("ADMIN_ID", 0))
    admin_bot_token = os.getenv("ADMIN_BOT_TOKEN")

    if current_admin_id != 0 and admin_bot_token:
        admin_ticket_text = (
            f"🆘 <b>НОВОЕ ОБРАЩЕНИЕ В ПОДДЕРЖКУ!</b>\n\n"
            f"👤 <b>Отправитель:</b> {author_username}\n"
            f"🎓 <b>Группа:</b> <code>{group_name}</code>\n"
            f"🆔 <b>ID студента:</b> <code>{user_id}</code>\n\n"
            f"<blockquote>💬 «{clean_text}»</blockquote>"
        )

        reply_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Ответить студенту", callback_data=f"reply_user_{user_id}")]
        ])

        try:
            async with Bot(token=admin_bot_token) as admin_bot:
                if photo_bytes:
                    # Упаковываем байты в файл для Админ-бота
                    input_photo = BufferedInputFile(photo_bytes, filename="support_photo.jpg")
                    await admin_bot.send_photo(
                        chat_id=current_admin_id,
                        photo=input_photo,  # <--- ПЕРЕДАЕМ БАЙТЫ, А НЕ ЧУЖОЙ FILE_ID!
                        caption=admin_ticket_text,
                        reply_markup=reply_keyboard,
                        parse_mode="HTML"
                    )
                else:
                    await admin_bot.send_message(
                        chat_id=current_admin_id,
                        text=admin_ticket_text,
                        reply_markup=reply_keyboard,
                        parse_mode="HTML"
                    )
            print(f"✅ Тикет поддержки отправлен в Админ-бот!")
        except Exception as e:
            print(f"❌ Ошибка отправки тикета админу: {e}")