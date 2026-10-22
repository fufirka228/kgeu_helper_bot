from datetime import datetime, date
import html
import re


def make_progress_bar(completed: int, total: int, length: int = 10) -> str:
    if total == 0:
        return f'[{'□' * length}] 0%'

    percent = completed / total
    filled_count = int(round(length * percent))
    empty_count = length - filled_count

    bar = '■' * filled_count + '□' * empty_count
    return f'[{bar}] {int(percent * 100)}%'


def get_urgency_info(due_date_str: str) -> tuple[str, str]:
    try:
        if '-' in due_date_str:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
        else:
            due_date = datetime.strptime(due_date_str, "%d.%m.%Y").date()
    except ValueError:
        return "⚪️", due_date_str

    today = date.today()
    days_left = (due_date - today).days

    if days_left < 0:
        return "💀", f"просрочено на {abs(days_left)} дн."
    elif days_left == 0:
        return "🔴", "<b>сегодня!</b>"
    elif days_left == 1:
        return "🔴", "<b>завтра!</b>"
    elif 2 <= days_left <= 4:
        return "🟡", f"осталось {days_left} дн."
    else:
        return "🟢", f"осталось {days_left} дн."

def format_deadlines_dashboard(group_name: str, deadlines: list, completed_ids: set[int]) -> tuple[str, list]:
    total = len(deadlines)
    completed_count = len([d for d in deadlines if d[0] in completed_ids])
    progress_bar = make_progress_bar(completed_count, total)

    text = (
        f"⚡️ <b>УЧЕБНЫЙ ДАШБОРД</b> • <code>{group_name}</code>\n\n"
        f"<b>ПРОГРЕСС:</b> <code>{progress_bar}</code>\n"
        f"<i>Закрыто {completed_count} из {total} заданий</i>\n\n"
    )

    active_deadlines = [d for d in deadlines if d[0] not in completed_ids]

    if not active_deadlines:
        text += "<blockquote>🎉 <b>Все дедлайны закрыты!</b>\nТы всё сдал, можно отдыхать.</blockquote>"
        return text, []

    for d in active_deadlines:
        d_id, subject, title, due_date, created_by = d[0], d[1], d[2], d[3], d[4]
        # Достаем юзернейм автора (6-й элемент):
        author_username = d[5] if len(d) > 5 and d[5] else f"ID: {created_by}"
        if author_username and not author_username.startswith("@") and not author_username.startswith("ID:"):
            author_username = f"@{author_username}"

        badge, urgency_text = get_urgency_info(due_date)
        subject = html.escape(subject)
        title = html.escape(title)

        text += (
            f"<blockquote>"
            f"{badge} <b>{subject.upper()}</b> — {title}\n"
            f"├ 📅 <code>{due_date}</code> • {urgency_text}\n"
            f"├ 👤 <i>Добавил:</i> {author_username}\n"
            f"└ ⏳ <i>Статус:</i> <b>Не сдано</b>"
            f"</blockquote>\n"
        )

    return text, active_deadlines

def normalize_date(raw_date: str) -> str | None:
    raw_date = raw_date.strip()
    current_year = date.today().year

    if re.match(r"^\d{1,2}\.\d{1,2}$", raw_date):
        raw_date = f"{raw_date}.{current_year}"

    try:
        parsed_date = datetime.strptime(raw_date, "%d.%m.%Y").date()
        return parsed_date.strftime("%Y-%m-%d")
    except ValueError:
        return None