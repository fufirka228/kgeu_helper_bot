from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import TelegramAPIError

from database.db_students import (
    get_student_profile,
    add_student,
    get_verified_students_count,
    get_verified_group_members,
    create_activation_token,
    use_activation_token,
    vote_for_student
)
from kgeu_info.group_checking import change_raw_group
from bot.keyboards import get_main_keyboard, get_verification_vote_keyboard
from bot.notifications import send_evening_notifications
from database.db_students import is_student_banned

router = Router()


class Registration(StatesGroup):
    waiting_for_group = State()


# ================= 1. КОМАНДА /START (С ПОДДЕРЖКОЙ ИНВАЙТ-ССЫЛОК) =================

@router.message(CommandStart())
async def start(message: Message, command: CommandObject, state: FSMContext, bot: Bot):
    await state.clear()
    user_id = message.from_user.id

    if await is_student_banned(user_id):
        await message.answer("⛔️ <b>Твой аккаунт заблокирован администратором.</b>", parse_mode="HTML")
        return

    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
    args = command.args  # Аргумент из ссылки вида t.me/bot?start=TOKEN

    # 1. СЦЕНАРИЙ: ПЕРЕХОД ПО ОДНОРАЗОВОЙ ИНВАЙТ-ССЫЛКЕ
    if args and args.startswith("act_"):
        token = args
        result = await use_activation_token(token, user_id, username)

        if result == "self_click":
            await message.answer(
                "⚠️ <b>Это твоя собственная инвайт-ссылка!</b>\n\n"
                "Перешли её своему реальному одногруппнику в личку или в беседу группы, чтобы он перешел по ней.",
                parse_mode="HTML"
            )
            return

        if result:
            group_name, creator_id = result
            # Радуем второго студента
            await message.answer(
                f"🎉 <b>Добро пожаловать в группу {group_name}!</b>\n\n"
                f"Ты перешел по ссылке одногруппника. Группа успешно <b>активирована</b>, "
                f"а ваши профили взаимно подтверждены!",
                reply_markup=get_main_keyboard(),
                parse_mode="HTML"
            )
            # Уведомляем создателя ссылки (Первого студента)
            try:
                await bot.send_message(
                    chat_id=creator_id,
                    text=f"🎉 <b>Группа {group_name} активирована!</b>\n"
                         f"Твой одногруппник {username} перешел по твоей ссылке. Теперь вам доступны все функции бота!",
                    parse_mode="HTML"
                )
            except TelegramAPIError:
                pass
            return
        else:
            await message.answer("⚠️ Эта инвайт-ссылка недействительна или уже была использована.")

    # 2. СЦЕНАРИЙ: ОБЫЧНЫЙ ВХОД
    profile = await get_student_profile(user_id)

    if profile:
        group_name = profile["group_name"]
        status = profile["status"]

        if status == "verified":
            status_text = "✅ Подтвержденный студент"
        else:
            status_text = "⏳ Ожидает подтверждения одногруппников"

        await message.answer(
            f"С возвращением!\n"
            f"🎓 Твоя группа: <b>{group_name}</b>\n"
            f"👤 Статус: <i>{status_text}</i>",
            reply_markup=get_main_keyboard(),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "Привет! Я бот-помощник студента КГЭУ. 🎓\n"
            "Напиши свою группу (например: <b>ЭП-1-23</b> или <b>ИВТ-2-22</b>):",
            parse_mode="HTML"
        )
        await state.set_state(Registration.waiting_for_group)


# ================= 2. ОБРАБОТКА ВВОДА ГРУППЫ =================

@router.message(Registration.waiting_for_group)
async def process_group(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
    user_group = change_raw_group(message.text)

    if not user_group:
        await message.answer(
            "❌ <b>Группа не найдена в официальной базе КГЭУ!</b>\n"
            "Пожалуйста, проверь название (пример: <b>ЭП-1-23</b>, <b>ПИ-1-24</b>):",
            parse_mode="HTML"
        )
        return

    # Проверяем, сколько подтвержденных студентов уже есть в этой группе
    verified_count = await get_verified_students_count(user_group)

    if verified_count == 0:
        # СЦЕНАРИЙ: ПЕРВОПРОХОДЕЦ (Первый студент в группе)
        await add_student(user_id, user_group, username, status='pending')
        token = await create_activation_token(user_group, user_id)

        bot_info = await bot.get_me()
        invite_link = f"https://t.me/{bot_info.username}?start={token}"

        await message.answer(
            f"🎓 <b>Ты первый студент из группы {user_group}!</b>\n\n"
            f"Чтобы защитить группу от фейков и активировать её, перешли эту <b>одноразовую ссылку</b> любому реальному одногруппнику:\n\n"
            f"👉 <code>{invite_link}</code>\n\n"
            f"<i>Как только он перейдет по ней — группа активируется для вас обоих!</i>",
            reply_markup=get_main_keyboard(),
            parse_mode="HTML"
        )
    else:
        # СЦЕНАРИЙ: ФЕЙСКОНТРОЛЬ (Группа уже активна, новичок ждет 2 голоса)
        await add_student(user_id, user_group, username, status='pending')

        await message.answer(
            f"✅ Группа <b>{user_group}</b> выбрана!\n\n"
            f"⏳ Твой профиль отправлен на подтверждение твоим одногруппникам.\n"
            f"Как только <b>2 человека</b> подтвердят, что ты из их группы, тебе откроются все функции!",
            reply_markup=get_main_keyboard(),
            parse_mode="HTML"
        )

        # Рассылаем опрос подтвержденным одногруппникам
        verified_members = await get_verified_group_members(user_group, exclude_id=user_id)
        for member_id in verified_members:
            try:
                await bot.send_message(
                    chat_id=member_id,
                    text=f"🔔 <b>В группу {user_group} стучится новый студент!</b>\n"
                         f"Профиль: {username}\n\n"
                         f"<i>Это ваш реальный одногруппник?</i>",
                    reply_markup=get_verification_vote_keyboard(user_id),
                    parse_mode="HTML"
                )
            except TelegramAPIError:
                pass

    await state.clear()


# ================= 3. ОБРАБОТКА ГОЛОСОВАНИЯ =================

@router.callback_query(F.data.startswith("vvote_yes_"))
async def vote_yes_callback(callback: CallbackQuery, bot: Bot):
    candidate_id = int(callback.data.split("_")[2])
    voter_id = callback.from_user.id

    yes_count = await vote_for_student(candidate_id, voter_id, vote=1)
    await callback.message.edit_text("Спасибо! Твой голос «ЗА» учтен. 👍")
    await callback.answer()

    # Если набралось 2 голоса — радуем кандидата!
    if yes_count == 2:
        try:
            await bot.send_message(
                chat_id=candidate_id,
                text="🎉 <b>Поздравляем!</b>\n"
                     "Одногруппники подтвердили твой профиль. Теперь тебе доступно создание дедлайнов и заметок!",
                parse_mode="HTML"
            )
        except TelegramAPIError:
            pass


@router.callback_query(F.data.startswith("vvote_no_"))
async def vote_no_callback(callback: CallbackQuery):
    candidate_id = int(callback.data.split("_")[2])
    voter_id = callback.from_user.id

    await vote_for_student(candidate_id, voter_id, vote=-1)
    await callback.message.edit_text("Твой голос «ПРОТИВ» учтен. 👎")
    await callback.answer()
