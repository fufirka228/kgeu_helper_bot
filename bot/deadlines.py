from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.db_students import get_student, get_student_profile
from database.db_deadlines import get_group_deadlines, get_student_completed_ids, toggle_deadline_status, add_deadline, delete_deadline
from bot.formatters import format_deadlines_dashboard, normalize_date
from bot.keyboards import get_deadlines_keyboard, get_back_archive, get_delete_deadlines_keyboard


router = Router()

class AddDeadline(StatesGroup):
    waiting_for_subject = State()
    waiting_for_title = State()
    waiting_for_date = State()

cancel_deadline_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_add_deadline")]
])

@router.message(F.text == "⏳ Дедлайны")
async def show_deadlines_menu(message: types.Message):
    user_id = message.from_user.id
    group_name = await get_student(user_id)

    if not group_name:
        await message.answer("Сначала выбери свою группу через команду /start!")
        return

    deadlines = await get_group_deadlines(group_name)
    completed_ids = await get_student_completed_ids(user_id)

    text, active_deadlines = format_deadlines_dashboard(group_name, deadlines, completed_ids)

    completed_count = len([d for d in deadlines if d[0] in completed_ids])
    keyboard = get_deadlines_keyboard(active_deadlines, completed_count)

    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data.startswith("done_"))
async def process_toggle_deadline(callback: types.CallbackQuery):
    deadline_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    await toggle_deadline_status(user_id, deadline_id)

    await callback.answer("Статус обновлен! ✅")

    group_name = await get_student(user_id)
    deadlines = await get_group_deadlines(group_name)
    completed_ids = await get_student_completed_ids(user_id)

    text, active_deadlines = format_deadlines_dashboard(group_name, deadlines, completed_ids)
    completed_count = len([d for d in deadlines if d[0] in completed_ids])
    keyboard = get_deadlines_keyboard(active_deadlines, completed_count)

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(F.text == "➕ Добавить дедлайн")
async def start_add_deadline(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    profile = await get_student_profile(user_id)

    if not profile:
        await message.answer("Сначала укажи свою группу через команду /start!")
        return

    # ЗАЩИТА: проверяем статус студента!
    if profile["status"] != "verified":
        await message.answer(
            "🔒 <b>Функция заблокирована!</b>\n\n"
            "Твой аккаунт еще ожидает подтверждения от одногруппников (статус: <i>На проверке</i>).\n"
            "Добавлять дедлайны на всю группу могут только подтвержденные студенты.",
            parse_mode="HTML"
        )
        return

    # Дальше идет старый код запроса предмета...
    await message.answer(
        "📝 <b>Шаг 1 из 3:</b>\n"
        "Введи название предмета (например: <b>ТОЭ</b> или <b>Физика</b>):",
        parse_mode="HTML",
        reply_markup=cancel_deadline_kb
    )
    await state.set_state(AddDeadline.waiting_for_subject)


@router.message(AddDeadline.waiting_for_subject)
async def process_subject(message: types.Message, state: FSMContext):
    await state.update_data(subject=message.text.strip())

    await message.answer(
        "📌 <b>Шаг 2 из 3:</b>\n"
        "Что именно нужно сдать? (например: <b>Лабораторная №2</b> или <b>РГР</b>):",
        parse_mode="HTML",
        reply_markup=cancel_deadline_kb
    )
    await state.set_state(AddDeadline.waiting_for_title)


@router.message(AddDeadline.waiting_for_title)
async def process_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await message.answer(
        "📅 <b>Шаг 3 из 3:</b>\n"
        "До какого числа сдать? Напиши дату (например: <b>25.10</b> или <b>25.10.2026</b>):",
        parse_mode="HTML",
        reply_markup=cancel_deadline_kb
    )
    await state.set_state(AddDeadline.waiting_for_date)


@router.message(AddDeadline.waiting_for_date)
async def process_date(message: types.Message, state: FSMContext):
    raw_date = message.text.strip()
    clean_date = normalize_date(raw_date)

    if not clean_date:
        await message.answer(
            "❌ Неверный формат даты!\n"
            "Напиши в формате день.месяц (например: <b>25.10</b>):",
            parse_mode="HTML"
        )
        return

    data = await state.get_data()
    subject = data["subject"]
    title = data["title"]
    user_id = message.from_user.id
    group_name = await get_student(user_id)

    await add_deadline(
        group_name=group_name,
        subject=subject,
        title=title,
        due_date=clean_date,
        created_by=user_id
    )

    await state.clear()
    await message.answer(
        f"✅ <b>Дедлайн успешно добавлен для группы {group_name}!</b>\n\n"
        f"📚 <b>{subject}</b> — {title}\n"
        f"📅 Срок: <code>{clean_date}</code>",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "back_to_deadlines")
async def back_to_deadlines_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    group_name = await get_student(user_id)

    deadlines = await get_group_deadlines(group_name)
    completed_ids = await get_student_completed_ids(user_id)

    text, active_deadlines = format_deadlines_dashboard(group_name, deadlines, completed_ids)
    completed_count = len([d for d in deadlines if d[0] in completed_ids])
    keyboard = get_deadlines_keyboard(active_deadlines, completed_count)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest:
        # Если текст не изменился — просто игнорируем, бот не крашится!
        pass

    await callback.answer()


@router.callback_query(F.data == "show_archive")
async def process_archive(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    group_name = await get_student(user_id)

    deadlines = await get_group_deadlines(group_name)
    completed_ids = await get_student_completed_ids(user_id)

    done_deadlines = [d for d in deadlines if d[0] in completed_ids]

    if not done_deadlines:
        await callback.answer("Архив пуст — ты пока ничего не сдал!", show_alert=True)
        return

    archive_text = f"📁 <b>Архив сданных заданий ({group_name}):</b>\n\n"
    for d in done_deadlines:
        _, subject, title, due_date, _ = d
        archive_text += f"✅ <s><b>{subject}</b> — {title}</s> (срок был: {due_date})\n"

    try:
        await callback.message.edit_text(archive_text, parse_mode="HTML", reply_markup=get_back_archive())
    except TelegramBadRequest:
        pass
    await callback.answer()


# 1. Студент нажал кнопку "🗑 Удалить" на дашборде
@router.callback_query(F.data == "enter_delete_mode")
async def show_delete_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    group_name = await get_student(user_id)

    deadlines = await get_group_deadlines(group_name)
    completed_ids = await get_student_completed_ids(user_id)
    active_deadlines = [d for d in deadlines if d[0] not in completed_ids]

    if not active_deadlines:
        await callback.answer("Нет активных задач для удаления!", show_alert=True)
        return

    keyboard = get_delete_deadlines_keyboard(active_deadlines)
    await callback.message.edit_text(
        "🗑 <b>Режим удаления дедлайнов:</b>\n"
        "Выбери задачу, которую хочешь удалить.\n\n"
        "⚠️ <i>Помни: удалить можно только ту задачу, которую создал ты сам!</i>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


# 2. Студент кликнул на конкретную задачу для удаления (callback: "del_5")
@router.callback_query(F.data.startswith("del_"))
async def process_delete_deadline(callback: types.CallbackQuery):
    deadline_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    # Пытаемся удалить через защищенную функцию базы
    is_deleted = await delete_deadline(deadline_id, user_id)

    if is_deleted:
        await callback.answer("✅ Дедлайн успешно удален!", show_alert=True)
        # Возвращаем обновленный дашборд (вызываем наш готовый хэндлер возврата)
        await back_to_deadlines_menu(callback)
    else:
        # Если попытался удалить чужую задачу!
        await callback.answer(
            "❌ Отказано в доступе!\n\n"
            "Ты не можешь удалить этот дедлайн, так как его создал другой одногруппник.",
            show_alert=True
        )


@router.callback_query(F.data == "cancel_add_deadline")
async def cancel_add_deadline_callback(callback: types.CallbackQuery, state: FSMContext):
    # ВАЖНО: полностью очищаем черновик FSM
    await state.clear()

    # Меняем текст сообщения на подтверждение отмены
    await callback.message.edit_text("❌ <b>Добавление дедлайна отменено.</b>", parse_mode="HTML")
    await callback.answer("Отменено!")