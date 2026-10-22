import os
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.db_students import (
    find_student_by_id_or_username,
    admin_set_student_verified,
    admin_change_student_group,
    admin_toggle_ban_student,
    get_admin_groups_summary,
admin_delete_student,
    get_students_in_group
)
from bot.keyboards import (
    get_admin_user_control_keyboard,
    get_admin_groups_keyboard,
    get_group_students_keyboard
)
from kgeu_info.group_checking import change_raw_group

router = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
STUDENT_BOT_TOKEN = os.getenv("BOT_TOKEN")


class AdminUserManageFSM(StatesGroup):
    waiting_for_user_query = State()
    waiting_for_new_group = State()


# 1. Клик по кнопке "👤 Управление студентом"
@router.callback_query(F.data == "admin_find_student")
async def start_find_student(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return

    await callback.message.answer(
        "🔎 <b>Поиск студента для управления:</b>\n\n"
        "Введи <b>Telegram ID</b> студента (например: <code>123456789</code>) "
        "или его <b>@username</b> (например: <code>@ivanov</code>):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_stats")]
        ])
    )
    await state.set_state(AdminUserManageFSM.waiting_for_user_query)
    await callback.answer()


# 2. Ловим ввод ID/Username -> выводим карточку
@router.message(AdminUserManageFSM.waiting_for_user_query)
async def process_find_student(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    query = message.text.strip()
    student = await find_student_by_id_or_username(query)

    if not student:
        await message.answer(
            f"❌ Студент по запросу <b>{query}</b> не найден в базе данных.\nПопробуй вбить точный Telegram ID:",
            parse_mode="HTML"
        )
        return

    await state.clear()
    tg_id, group_name, username, status, is_banned = student
    username_str = f"{username}" if username else "Не указан"
    status_badge = "✅ Подтвержден" if status == "verified" else "⏳ На проверке (pending)"
    ban_badge = "🔴 <b>ЗАБЛОКИРОВАН</b>" if is_banned == 1 else "🟢 Активен"

    card_text = (
        f"👤 <b>КАРТОЧКА СТУДЕНТА</b>\n\n"
        f"<blockquote>"
        f"🆔 <b>Telegram ID:</b> <code>{tg_id}</code>\n"
        f"👤 <b>Юзернейм:</b> {username_str}\n"
        f"🎓 <b>Группа:</b> <code>{group_name}</code>\n"
        f"🛡 <b>Статус:</b> {status_badge}\n"
        f"🚫 <b>Состояние:</b> {ban_badge}"
        f"</blockquote>"
    )

    keyboard = get_admin_user_control_keyboard(tg_id, status, is_banned)
    await message.answer(card_text, reply_markup=keyboard, parse_mode="HTML")


# 3. Клик по кнопке "✅ Подтвердить статус"
@router.callback_query(F.data.startswith("adm_verify_"))
async def process_admin_verify(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    target_id = int(callback.data.split("_")[2])
    await admin_set_student_verified(target_id)

    # Уведомляем админа
    await callback.answer("Студент успешно подтвержден! ✅", show_alert=True)

    # Уведомляем самого студента через Студенческого бота
    if STUDENT_BOT_TOKEN:
        try:
            async with Bot(token=STUDENT_BOT_TOKEN) as student_bot:
                await student_bot.send_message(
                    chat_id=target_id,
                    text="🎉 <b>Администратор принудительно подтвердил твой профиль!</b>\nТеперь тебе доступны все функции бота.",
                    parse_mode="HTML"
                )
        except Exception:
            pass

    # Обновляем карточку
    student = await find_student_by_id_or_username(str(target_id))
    tg_id, group_name, username, status, is_banned = student
    card_text = (
        f"👤 <b>КАРТОЧКА СТУДЕНТА</b>\n\n"
        f"<blockquote>"
        f"🆔 <b>Telegram ID:</b> <code>{tg_id}</code>\n"
        f"🎓 <b>Группа:</b> <code>{group_name}</code>\n"
        f"🛡 <b>Статус:</b> ✅ Подтвержден (Ручно)\n"
        f"🚫 <b>Состояние:</b> 🟢 Активен"
        f"</blockquote>"
    )
    keyboard = get_admin_user_control_keyboard(tg_id, "verified", is_banned)
    await callback.message.edit_text(card_text, reply_markup=keyboard, parse_mode="HTML")


# 4. Клик по кнопке "⛔️ Заблокировать / 🟢 Разблокировать"
@router.callback_query(F.data.startswith("adm_ban_"))
async def process_admin_toggle_ban(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    target_id = int(callback.data.split("_")[2])
    new_ban_state = await admin_toggle_ban_student(target_id)

    ban_msg = "заблокирован ⛔️" if new_ban_state == 1 else "разблокирован 🟢"
    await callback.answer(f"Студент {ban_msg}!", show_alert=True)

    # Уведомляем студента
    if STUDENT_BOT_TOKEN:
        try:
            async with Bot(token=STUDENT_BOT_TOKEN) as student_bot:
                if new_ban_state == 1:
                    await student_bot.send_message(
                        chat_id=target_id,
                        text="⛔️ <b>Твой аккаунт был заблокирован администратором.</b>",
                        parse_mode="HTML"
                    )
                else:
                    await student_bot.send_message(
                        chat_id=target_id,
                        text="🟢 <b>Твой аккаунт разблокирован администратором!</b>",
                        parse_mode="HTML"
                    )
        except Exception:
            pass

    # Обновляем карточку
    student = await find_student_by_id_or_username(str(target_id))
    tg_id, group_name, username, status, is_banned = student
    ban_badge = "🔴 <b>ЗАБЛОКИРОВАН</b>" if is_banned == 1 else "🟢 Активен"
    card_text = (
        f"👤 <b>КАРТОЧКА СТУДЕНТА</b>\n\n"
        f"<blockquote>"
        f"🆔 <b>Telegram ID:</b> <code>{tg_id}</code>\n"
        f"🎓 <b>Группа:</b> <code>{group_name}</code>\n"
        f"🛡 <b>Статус:</b> {status}\n"
        f"🚫 <b>Состояние:</b> {ban_badge}"
        f"</blockquote>"
    )
    keyboard = get_admin_user_control_keyboard(tg_id, status, is_banned)
    await callback.message.edit_text(card_text, reply_markup=keyboard, parse_mode="HTML")


# 5. Клик по кнопке "🔄 Сменить группу"
@router.callback_query(F.data.startswith("adm_chgroup_"))
async def start_admin_change_group(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return

    target_id = int(callback.data.split("_")[2])
    await state.update_data(target_student_id=target_id)

    await callback.message.answer(
        f"🔄 <b>Смена группы для студента ID <code>{target_id}</code>:</b>\n\n"
        f"Введи новую группу из КГЭУ (например: <b>ЭП-1-23</b>):",
        parse_mode="HTML"
    )
    await state.set_state(AdminUserManageFSM.waiting_for_new_group)
    await callback.answer()


# 6. Ловим ввод новой группы от Админа
@router.message(AdminUserManageFSM.waiting_for_new_group)
async def process_admin_group_entered(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    new_group = change_raw_group(message.text)
    if not new_group:
        await message.answer("❌ Группа не найдена в КГЭУ! Попробуй еще раз:")
        return

    data = await state.get_data()
    target_id = data["target_student_id"]
    await state.clear()

    await admin_change_student_group(target_id, new_group)
    await message.answer(f"✅ Группа студента {target_id} изменена на <b>{new_group}</b>!", parse_mode="HTML")


# 1. Показ списка всех активных групп в боте
@router.callback_query(F.data == "admin_groups_list")
async def show_admin_groups_list(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    groups_summary = await get_admin_groups_summary()

    if not groups_summary:
        await callback.answer("В боте пока нет зарегистрированных студентов!", show_alert=True)
        return

    keyboard = get_admin_groups_keyboard(groups_summary)
    await callback.message.edit_text(
        "🎓 <b>СПИСОК АКТИВНЫХ ГРУПП В БОТЕ:</b>\n"
        "Выбери группу, чтобы посмотреть список её студентов:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


# 2. Показ списка студентов выбранной группы
@router.callback_query(F.data.startswith("admingroup_"))
async def show_group_students_roster(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    group_name = callback.data.split("_", 1)[1]
    students = await get_students_in_group(group_name)

    if not students:
        await callback.answer("В этой группе пока нет студентов!", show_alert=True)
        return

    keyboard = get_group_students_keyboard(group_name, students)

    verified_cnt = len([s for s in students if s[2] == 'verified'])
    pending_cnt = len(students) - verified_cnt

    await callback.message.edit_text(
        f"🎓 <b>ГРУППА: {group_name}</b> (Всего: {len(students)} студ.)\n"
        f"├ ✅ Подтвержденных: <code>{verified_cnt}</code>\n"
        f"└ ⏳ На проверке: <code>{pending_cnt}</code>\n\n"
        f"<i>Выбери студента для управления:</i>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


# 3. Клик по студенту из списка -> открывает карточку управления
@router.callback_query(F.data.startswith("adm_user_"))
async def open_user_card_from_list(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    target_id = int(callback.data.split("_")[2])
    student = await find_student_by_id_or_username(str(target_id))

    if not student:
        await callback.answer("Студент не найден!", show_alert=True)
        return

    tg_id, group_name, username, status, is_banned = student
    username_str = f"{username}" if username else "Не указан"
    status_badge = "✅ Подтвержден" if status == "verified" else "⏳ На проверке (pending)"
    ban_badge = "🔴 <b>ЗАБЛОКИРОВАН</b>" if is_banned == 1 else "🟢 Активен"

    card_text = (
        f"👤 <b>КАРТОЧКА СТУДЕНТА</b>\n\n"
        f"<blockquote>"
        f"🆔 <b>Telegram ID:</b> <code>{tg_id}</code>\n"
        f"👤 <b>Юзернейм:</b> {username_str}\n"
        f"🎓 <b>Группа:</b> <code>{group_name}</code>\n"
        f"🛡 <b>Статус:</b> {status_badge}\n"
        f"🚫 <b>Состояние:</b> {ban_badge}"
        f"</blockquote>"
    )

    keyboard = get_admin_user_control_keyboard(tg_id, status, is_banned)
    await callback.message.edit_text(card_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("adm_deluser_"))
async def process_admin_delete_student_callback(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    target_id = int(callback.data.split("_")[2])

    # 1. Стираем из базы
    await admin_delete_student(target_id)
    await callback.answer("Студент полностью удален из базы данных! 🗑", show_alert=True)

    # 2. Уведомляем студента
    if STUDENT_BOT_TOKEN:
        try:
            async with Bot(token=STUDENT_BOT_TOKEN) as student_bot:
                await student_bot.send_message(
                    chat_id=target_id,
                    text="🗑 <b>Твой аккаунт был сброшен администратором.</b>\n"
                         "Напиши /start для повторной регистрации.",
                    parse_mode="HTML"
                )
        except Exception:
            pass

    # 3. Возвращаем админа к списку групп
    await show_admin_groups_list(callback)