from aiogram.types import KeyboardButton, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

def get_main_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()

    builder.add(
        KeyboardButton(
            text='📅 Расписание',
            web_app=WebAppInfo(url="https://pro.kgeu.ru/schedule")
        ),
        KeyboardButton(
            text='🧿 Баллы БРС',
            web_app=WebAppInfo(url="https://pro.kgeu.ru/grades")
        ),
        KeyboardButton(text='⏳ Дедлайны'),
        KeyboardButton(text='➕ Добавить дедлайн'),
        KeyboardButton(text='⚙️ Мой профиль'),
        KeyboardButton(text='📚 База знаний'),
    )

    builder.adjust(2, 2, 2)
    return builder.as_markup(resize_keyboard=True)


def get_deadlines_keyboard(active_deadlines: list, completed_count: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for d in active_deadlines:
        # ДОБАВЛЯЕМ [:5] — берем первые 5 элементов (d_id, subject, title, due_date, created_by)
        d_id, subject, title, due_date, created_by = d[:5]
        btn_text = f'▫️ Сдать: {subject[:10]} ({title[:12]})'
        builder.button(text=btn_text, callback_data=f'done_{d_id}')

    builder.adjust(1)

    bottom_buttons = []
    if completed_count > 0:
        bottom_buttons.append(
            InlineKeyboardButton(text=f"📁 Архив ({completed_count})", callback_data="show_archive")
        )
    if active_deadlines:
        bottom_buttons.append(
            InlineKeyboardButton(text="🗑 Удалить", callback_data="enter_delete_mode")
        )

    builder.row(*bottom_buttons)
    return builder.as_markup()


def get_delete_deadlines_keyboard(active_deadlines: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for d in active_deadlines:
        # ТОЖЕ ДОБАВЛЯЕМ [:5]
        d_id, subject, title, due_date, created_by = d[:5]
        builder.button(text=f"🗑 {subject}: {title[:12]}", callback_data=f"del_{d_id}")

    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="⬅️ Отмена", callback_data="back_to_deadlines"))

    return builder.as_markup()

def get_back_archive() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text='⬅️ Вернуться', callback_data='back_to_deadlines')
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# Меню выбора раздела базы знаний
def get_knowledge_hub_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📖 Предметы нашей группы", callback_data="hub_subjects")],
        [InlineKeyboardButton(text="👨‍🏫 Преподаватели вуза (Отзывы)", callback_data="hub_teachers")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# Список предметов группы
def get_group_subjects_keyboard(subjects: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for s_id, s_name in subjects:
        # s_id — это короткое число (например, 5), вес всего несколько байт!
        builder.button(text=f"📚 {s_name}", callback_data=f"gsubj_{s_id}")

    # Делаем по 1 кнопке в ряд, так как названия предметов длинные
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_hub"))
    return builder.as_markup()


# Список преподавателей вуза
def get_teachers_list_keyboard(teachers: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for t_id, full_name, dept in teachers:
        parts = full_name.split()
        # Если есть имя и отчество: "Иванов И.И.", если нет — просто фамилия
        short_name = f"{parts[0]} {parts[1][:1]}." if len(parts) > 1 else full_name
        builder.button(text=f"👨‍🏫 {short_name}", callback_data=f"teach_{t_id}")

    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="🔍 Искать другого", callback_data="hub_teachers"))
    builder.row(InlineKeyboardButton(text="⬅️ В главное меню базы", callback_data="back_to_hub"))
    return builder.as_markup()

# Клавиатура выбора звезд (1-5)
def get_rating_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="⭐️ 1", callback_data="rate_1"),
            InlineKeyboardButton(text="⭐️ 2", callback_data="rate_2"),
            InlineKeyboardButton(text="⭐️ 3", callback_data="rate_3"),
            InlineKeyboardButton(text="⭐️ 4", callback_data="rate_4"),
            InlineKeyboardButton(text="⭐️ 5", callback_data="rate_5"),
        ],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="back_to_hub")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# Кнопки для Админа под прилетевшим отзывом
def get_admin_moderation_keyboard(review_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"mod_appr_{review_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"mod_rej_{review_id}"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_verification_vote_keyboard(candidate_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="👍 Да, наш", callback_data=f"vvote_yes_{candidate_id}"),
            InlineKeyboardButton(text="👎 Нет / Фейк", callback_data=f"vvote_no_{candidate_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_profile_keyboard(notify_enabled: int) -> InlineKeyboardMarkup:
    notify_text = "🔔 Уведомления: ВКЛ" if notify_enabled == 1 else "🔕 Уведомления: ВЫКЛ"

    buttons = [
        [InlineKeyboardButton(text=notify_text, callback_data="toggle_notifications")],
        [InlineKeyboardButton(text="🔄 Сменить группу", callback_data="change_my_group")],
        # НОВАЯ КНОПКА ПОДДЕРЖКИ:
        [InlineKeyboardButton(text="💬 Написать в поддержку", callback_data="contact_support")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="🚀 Подтвердить и отправить", callback_data="confirm_broadcast"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_broadcast")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_panel_keyboard(pending_reviews_count: int) -> InlineKeyboardMarkup:
    mod_text = f"⏳ Модерация отзывов ({pending_reviews_count})" if pending_reviews_count > 0 else "⏳ Очередь отзывов (0)"

    buttons = [
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🎓 Группы и студенты", callback_data="admin_groups_list")], # <--- НАША КНОПКА
        [InlineKeyboardButton(text="👤 Поиск студента по ID", callback_data="admin_find_student")],
        [InlineKeyboardButton(text=mod_text, callback_data="admin_review_queue")],
        [InlineKeyboardButton(text="📢 Рассылка студентам", callback_data="admin_start_broadcast")],
        [InlineKeyboardButton(text="🖥 Консоль логов", callback_data="admin_show_logs")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_user_control_keyboard(target_id: int, status: str, is_banned: int) -> InlineKeyboardMarkup:
    buttons = []

    if status != "verified":
        buttons.append([InlineKeyboardButton(text="✅ Подтвердить статус", callback_data=f"adm_verify_{target_id}")])

    buttons.append([InlineKeyboardButton(text="🔄 Сменить группу", callback_data=f"adm_chgroup_{target_id}")])

    if is_banned == 1:
        buttons.append([InlineKeyboardButton(text="🟢 Разблокировать (Разбан)", callback_data=f"adm_ban_{target_id}")])
    else:
        buttons.append([InlineKeyboardButton(text="⛔️ Заблокировать (Бан)", callback_data=f"adm_ban_{target_id}")])

    # КНОПКА ПОЛНОГО УДАЛЕНИЯ ИЗ БАЗЫ:
    buttons.append([InlineKeyboardButton(text="🗑 Удалить из базы данных", callback_data=f"adm_deluser_{target_id}")])

    buttons.append([InlineKeyboardButton(text="⬅️ К списку групп", callback_data="admin_groups_list")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_groups_keyboard(groups_summary: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for g_name, total_count, verified_count in groups_summary:
        btn_text = f"🎓 {g_name} ({total_count} студ.)"
        builder.button(text=btn_text, callback_data=f"admingroup_{g_name}")

    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_stats"))
    return builder.as_markup()


# Клавиатура студентов конкретной группы
def get_group_students_keyboard(group_name: str, students: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for tg_id, username, status, is_banned in students:
        icon = "✅" if status == "verified" else "⏳"
        if is_banned == 1:
            icon = "⛔️"

        user_label = f"{username}" if username else f"ID: {tg_id}"
        btn_text = f"{icon} {user_label}"

        builder.button(text=btn_text, callback_data=f"adm_user_{tg_id}")

    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="⬅️ К списку групп", callback_data="admin_groups_list"))
    return builder.as_markup()