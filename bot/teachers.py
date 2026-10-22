from aiogram import Router, F, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import html
from aiogram import Bot
import os


from database.db_students import get_student
from kgeu_info.schedule_parser import fetch_and_import_group_subjects
from database.db_teachers import (
    get_group_subjects,
    get_group_subject_details,
    update_group_subject_notes,
    search_teachers,
    get_teacher_dossier,
    get_teacher_reviews,
    get_all_teacher_reviews,
    get_group_subject_by_id,
    update_group_subject_notes_by_id,
    add_teacher_review,
    approve_review,
    reject_review
)
from bot.keyboards import (
    get_knowledge_hub_keyboard,
    get_group_subjects_keyboard,
    get_teachers_list_keyboard,
    get_rating_keyboard,
    get_admin_moderation_keyboard
)

ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")

router = Router()

import os
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

# Состояния для поиска и ввода заметок/отзывов
class KnowledgeFSM(StatesGroup):
    waiting_for_teacher_name = State()   # Ждем фамилию для поиска
    waiting_for_subject_note = State()
    waiting_for_rating = State()
    waiting_for_review_text = State()    # Ждем текст отзыва на препода


# ================= ГЛАВНОЕ МЕНЮ БАЗЫ ЗНАНИЙ =================

@router.message(F.text == "📚 База знаний")
async def open_knowledge_hub(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    group_name = await get_student(user_id)

    if not group_name:
        await message.answer("Сначала выбери группу через команду /start!")
        return

    text = (
        f"🏛 <b>БАЗА ЗНАНИЙ КГЭУ</b> • <code>{group_name}</code>\n\n"
        f"Здесь собраны требования к предметам твоей группы, "
        f"досье на 900+ преподавателей и отзывы студентов.\n\n"
        f"<i>Что тебя интересует?</i>"
    )
    await message.answer(text, reply_markup=get_knowledge_hub_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "back_to_hub")
async def back_to_hub_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    group_name = await get_student(user_id)

    text = (
        f"🏛 <b>БАЗА ЗНАНИЙ КГЭУ</b> • <code>{group_name}</code>\n\n"
        f"<i>Что тебя интересует?</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_knowledge_hub_keyboard(), parse_mode="HTML")
    await callback.answer()


# ================= РАЗДЕЛ: ПРЕДМЕТЫ ГРУППЫ =================

@router.callback_query(F.data == "hub_subjects")
async def show_group_subjects_list(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    group_name = await get_student(user_id)

    subjects = await get_group_subjects(group_name)

    # ЕСЛИ ПРЕДМЕТОВ ЕЩЕ НЕТ В БАЗЕ — ПОДТЯГИВАЕМ ИЗ РАСПИСАНИЯ КГЭУ!
    if not subjects:
        await callback.message.edit_text(
            f"⏳ <b>Подгружаю предметы из официального расписания КГЭУ для {group_name}...</b>",
            parse_mode="HTML"
        )
        # Скачиваем на лету из API pro.kgeu.ru:
        success = await fetch_and_import_group_subjects(group_name)

        if success:
            subjects = await get_group_subjects(group_name)
        else:
            await callback.message.edit_text(
                f"⚠️ Для группы <b>{group_name}</b> не удалось найти расписание на сервере КГЭУ.\n"
                f"Возможно, расписание еще не заполнено на сайте.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_hub")]
                ]),
                parse_mode="HTML"
            )
            return

    keyboard = get_group_subjects_keyboard(subjects)
    await callback.message.edit_text(
        f"📖 <b>Предметы группы {group_name}:</b>\nВыбери предмет для просмотра требований и заметок:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gsubj_"))
async def show_subject_wiki_card(callback: types.CallbackQuery):
    subject_id = int(callback.data.split("_")[1])
    details = await get_group_subject_by_id(subject_id)

    if not details:
        await callback.answer("Предмет не найден!", show_alert=True)
        return

    s_id, subj, teacher, exam_type, conspect, notes, updated_by, group_name = details

    card_text = (
        f"📖 <b>ПРЕДМЕТ ГРУППЫ</b> • <code>{group_name}</code>\n"
        f"<b>{subj}</b>\n\n"
        f"<blockquote>"
        f"👨‍🏫 <b>Преподаватель:</b> {teacher}\n"
        f"🎯 <b>Контроль:</b> {exam_type}\n"
        f"📝 <b>Конспект:</b> {conspect}\n"
        f"</blockquote>\n"
        f"<blockquote>"
        f"💡 <b>ЗАМЕТКИ И СОВЕТЫ ГРУППЫ:</b>\n{notes}\n\n"
        f"👤 <i>Изменил: {updated_by}</i>"
        f"</blockquote>"
    )

    buttons = [
        [InlineKeyboardButton(text="✏️ Изменить заметку", callback_data=f"editnotes_{s_id}")],
        [InlineKeyboardButton(text="⬅️ К списку предметов", callback_data="hub_subjects")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(card_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# Редактирование заметок
@router.callback_query(F.data.startswith("editnotes_"))
async def start_edit_notes(callback: types.CallbackQuery, state: FSMContext):
    subject_id = int(callback.data.split("_")[1])
    details = await get_group_subject_by_id(subject_id)

    if not details:
        await callback.answer("Ошибка: предмет не найден!", show_alert=True)
        return

    subj_name = details[1]
    await state.update_data(edit_subject_id=subject_id, edit_subject_name=subj_name)

    # Кнопка отмены редактирования:
    cancel_edit_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_edit_note")]
    ])

    await callback.message.answer(
        f"✏️ <b>Редактирование заметок по {subj_name}:</b>\n\n"
        f"Напиши полезный совет для группы (про автоматы, конспекты или сдачу лаб).\n"
        f"Это сообщение увидят все твои одногруппники!",
        reply_markup=cancel_edit_kb,  # <--- ПРИКРЕПИЛИ КНОПКУ
        parse_mode="HTML"
    )
    await state.set_state(KnowledgeFSM.waiting_for_subject_note)
    await callback.answer()


# Обработчик нажатия на "❌ Отменить" при редактировании заметки
@router.callback_query(F.data == "cancel_edit_note")
async def cancel_edit_note_callback(callback: types.CallbackQuery, state: FSMContext):
    # ВАЖНО: сбрасываем состояние FSM, чтобы бот не ждал текст
    await state.clear()

    # Меняем текст сообщения на подтверждение отмены
    await callback.message.edit_text("❌ <b>Редактирование заметки отменено.</b>", parse_mode="HTML")
    await callback.answer("Отменено!")


@router.message(KnowledgeFSM.waiting_for_subject_note)
async def process_save_note(message: types.Message, state: FSMContext):
    data = await state.get_data()
    subject_id = data["edit_subject_id"]
    subj_name = data["edit_subject_name"]
    author = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
    clean_note = html.escape(message.text.strip())

    await update_group_subject_notes_by_id(subject_id, clean_note, author)
    await state.clear()

    await message.answer(
        f"✅ <b>Заметка по предмету {subj_name} успешно обновлена!</b>",
        parse_mode="HTML"
    )


# ================= РАЗДЕЛ: ПРЕПОДАВАТЕЛИ ВУЗА (ПОИСК ИЗ 920+ ЧЕЛОВЕК) =================

@router.callback_query(F.data == "hub_teachers")
async def prompt_search_teacher(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "🔍 <b>Поиск преподавателя:</b>\n"
        "Введи фамилию преподавателя (например: <b>Иванов</b>, <b>Абдуллин</b> или <b>Аскаров</b>):",
        parse_mode="HTML"
    )
    await state.set_state(KnowledgeFSM.waiting_for_teacher_name)
    await callback.answer()


@router.message(KnowledgeFSM.waiting_for_teacher_name)
async def process_search_teacher(message: types.Message, state: FSMContext):
    query = message.text.strip()
    teachers = await search_teachers(query)

    if not teachers:
        await message.answer(
            f"❌ Преподаватель с фамилией <b>{query}</b> не найден в базе КГЭУ.\n"
            f"Попробуй ввести только корень фамилии или проверить ошибки:",
            parse_mode="HTML"
        )
        return

    await state.clear()
    keyboard = get_teachers_list_keyboard(teachers)
    await message.answer(
        f"🎯 <b>Найдено преподавателей ({len(teachers)}):</b>\nВыбери из списка:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("teach_"))
async def show_teacher_card(callback: types.CallbackQuery):
    teacher_id = int(callback.data.split("_")[1])
    dossier = await get_teacher_dossier(teacher_id)
    reviews = await get_teacher_reviews(teacher_id)

    stars = "⭐️" * int(round(dossier["avg_rating"]))

    card_text = (
        f"👨‍🏫 <b>ДОСЬЕ ПРЕПОДАВАТЕЛЯ</b>\n"
        f"<b>{dossier['full_name']}</b> • <code>{dossier['department']}</code>\n\n"
        f"<blockquote>"
        f"⭐️ <b>Ср. оценка:</b> <code>{dossier['avg_rating']} / 5.0</code> {stars}\n"
        f"📊 <b>Всего отзывов:</b> {dossier['reviews_count']}\n"
        f"</blockquote>\n"
    )

    if reviews:
        r_text, r_rate, r_date = reviews[0]
        card_text += (
            f"💬 <b>Последний отзыв ({r_rate}/5 ⭐️):</b>\n"
            f"<blockquote><i>«{r_text}»</i>\n\n"
            f"📅 <code>{r_date}</code></blockquote>"
        )
    else:
        card_text += "<blockquote>💬 <i>Отзывов пока нет. Будь первым, кто его оставит!</i></blockquote>"

    buttons = []
    if dossier['reviews_count'] > 0:
        buttons.append([InlineKeyboardButton(text=f"💬 Все отзывы ({dossier['reviews_count']})", callback_data=f"allrev_{teacher_id}")])

    buttons.append([InlineKeyboardButton(text="✍️ Оставить отзыв", callback_data=f"rev_{teacher_id}")])
    buttons.append([InlineKeyboardButton(text="🔍 Другой препод", callback_data="hub_teachers")])
    buttons.append([InlineKeyboardButton(text="⬅️ В меню базы", callback_data="back_to_hub")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(card_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("allrev_"))
async def show_all_reviews(callback: types.CallbackQuery):
    teacher_id = int(callback.data.split("_")[1])
    dossier = await get_teacher_dossier(teacher_id)
    all_reviews = await get_all_teacher_reviews(teacher_id)

    text = f"💬 <b>Все отзывы о преподавателе:</b>\n<b>{dossier['full_name']}</b>\n\n"

    for r_text, r_rate, r_date in all_reviews:
        text += (
            f"<blockquote>"
            f"⭐️ <b>Оценка: {r_rate}/5</b> • 📅 <code>{r_date}</code>\n"
            f"<i>«{r_text}»</i>"
            f"</blockquote>\n"
        )

    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад в досье", callback_data=f"teach_{teacher_id}")]
    ])
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()


# Оставить отзыв на преподавателя
@router.callback_query(F.data.startswith("rev_"))
async def start_add_review(callback: types.CallbackQuery, state: FSMContext):
    teacher_id = int(callback.data.split("_")[1])
    await state.update_data(review_teacher_id=teacher_id)

    await callback.message.answer(
        "⭐️ <b>Шаг 1 из 2:</b>\n"
        "Поставь оценку преподавателю от 1 до 5 звезд:",
        reply_markup=get_rating_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(KnowledgeFSM.waiting_for_rating)
    await callback.answer()


# 2. Студент выбрал оценку (кликнул на звездочку)
@router.callback_query(KnowledgeFSM.waiting_for_rating, F.data.startswith("rate_"))
async def process_rating_chosen(callback: types.CallbackQuery, state: FSMContext):
    stars = int(callback.data.split("_")[1])
    await state.update_data(review_rating=stars)

    await callback.message.edit_text(
        f"⭐️ Выбрана оценка: <b>{stars} из 5</b>\n\n"
        f"📝 <b>Шаг 2 из 2:</b>\n"
        f"Напиши свой честный отзыв текстом:\n"
        f"<i>(Как принимает лабы, требует ли конспект, ставит ли автоматы?)</i>",
        parse_mode="HTML"
    )
    await state.set_state(KnowledgeFSM.waiting_for_review_text)
    await callback.answer()


# 3. Студент прислал текст отзыва -> отправляем АДМИНУ на модерацию
@router.message(KnowledgeFSM.waiting_for_review_text)
async def process_save_review(message: types.Message, state: FSMContext):
    data = await state.get_data()
    teacher_id = data["review_teacher_id"]
    rating = data["review_rating"]
    author_id = message.from_user.id
    # Экранируем текст отзыва для безопасности разметки
    review_text = html.escape(message.text.strip())

    # Сохраняем в базу со статусом "на модерации" (0)
    review_id = await add_teacher_review(teacher_id, author_id, review_text, rating)
    await state.clear()

    # Уведомляем студента
    await message.answer(
        "📨 <b>Спасибо! Твой отзыв отправлен на модерацию.</b>\n"
        "Он появится в досье преподавателя после быстрой проверки администратором.",
        parse_mode="HTML"
    )

    # 4. ОТПРАВЛЯЕМ АДМИНУ В ЛИЧКУ
    current_admin_id = int(os.getenv("ADMIN_ID", 0))
    print(f"DEBUG: Текущий ADMIN_ID = {current_admin_id}")  # Отладка в консоль

    if current_admin_id != 0:
        dossier = await get_teacher_dossier(teacher_id)
        author_username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {author_id}"

        admin_text = (
            f"👮‍♂️ <b>НОВЫЙ ОТЗЫВ НА МОДЕРАЦИЮ (#{review_id})</b>\n\n"
            f"👨‍🏫 <b>Преподаватель:</b> {dossier['full_name']}\n"
            f"⭐️ <b>Оценка:</b> {'⭐️' * rating} ({rating}/5)\n"
            f"👤 <b>Автор:</b> {author_username}\n\n"
            f"<blockquote>💬 «{review_text}»</blockquote>"
        )
        try:
            async with Bot(token=ADMIN_BOT_TOKEN) as admin_bot:
                await admin_bot.send_message(
                    chat_id=current_admin_id,
                    text=admin_text,
                    reply_markup=get_admin_moderation_keyboard(review_id),
                    parse_mode="HTML"
                )
            print(f"✅ Уведомление успешно отправлено админу ({current_admin_id})!")
        except Exception as e:
            print(f"❌ Не удалось отправить уведомление админу: {e}")
    else:
        print("⚠️ ВНИМАНИЕ: ADMIN_ID равен 0! Проверь файл .env")


# ================= ОБРАБОТЧИКИ ДЛЯ АДМИНА =================

@router.callback_query(F.data.startswith("mod_appr_"))
async def admin_approve_review(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("У тебя нет прав администратора!", show_alert=True)
        return

    review_id = int(callback.data.split("_")[2])
    await approve_review(review_id)

    # html_text сохраняет красивые цитаты и жирный шрифт!
    await callback.message.edit_text(
        callback.message.html_text + "\n\n✅ <b>ОДОБРЕНО И ОПУБЛИКОВАНО</b>",
        parse_mode="HTML"
    )
    await callback.answer("Отзыв опубликован!")


@router.callback_query(F.data.startswith("mod_rej_"))
async def admin_reject_review(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("У тебя нет прав администратора!", show_alert=True)
        return

    review_id = int(callback.data.split("_")[2])
    await reject_review(review_id)

    await callback.message.edit_text(
        callback.message.html_text + "\n\n❌ <b>ОТКЛОНЕНО И УДАЛЕНО</b>",
        parse_mode="HTML"
    )
    await callback.answer("Отзыв удален!")