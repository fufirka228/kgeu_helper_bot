import re
import json
import aiohttp
from aiosqlite import connect
from pathlib import Path
from kgeu_info.group_checking import get_group_id

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / 'storage' / 'bot.db'
STORAGE_DIR = BASE_DIR / 'storage'

PREFIX_REGEX = re.compile(r"^(лек\.?|лаб\.?|пр\.?)\s+", re.IGNORECASE)

def clean_discipline_name(raw_name: str) -> str:
    cleaned = PREFIX_REGEX.sub("", raw_name.strip())
    return cleaned[:1].upper() + cleaned[1:]


async def parse_and_save_schedule_subjects(schedule_data: dict, target_group: str) -> int:
    """Извлекает предметы и преподов из JSON расписания и сохраняет в базу"""
    days = schedule_data.get("schedule", [])
    if not days:
        return 0

    subjects_map = {}

    for day in days:
        for lesson in day.get("lessons", []):
            raw_discipline = lesson.get("discipline", "")
            clean_subject = clean_discipline_name(raw_discipline)
            teacher = lesson.get("teacher_name", "").strip()

            if not clean_subject:
                continue

            if clean_subject not in subjects_map:
                subjects_map[clean_subject] = set()

            if teacher and "вакансия" not in teacher.lower():
                subjects_map[clean_subject].add(teacher)

    if not subjects_map:
        return 0

    records_to_insert = []
    for subject, teachers in subjects_map.items():
        teachers_str = ", ".join(sorted(teachers)) if teachers else "Преподаватель не указан"
        default_exam = "Зачет" if "физическ" in subject.lower() else "Экзамен / Зачет"

        records_to_insert.append((
            target_group,
            subject,
            teachers_str,
            default_exam,
            "Не указано (нажми кнопку ниже, чтобы добавить)",
            f"Предмет автоматически импортирован для группы {target_group}.",
            "Система КГЭУ"
        ))

    async with connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS group_subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT NOT NULL,
                subject_name TEXT NOT NULL,
                teacher_name TEXT,
                exam_type TEXT DEFAULT 'Не указано',
                conspect TEXT DEFAULT 'Не указано',
                group_notes TEXT DEFAULT 'Заметок пока нет. Нажми кнопку ниже, чтобы добавить первую!',
                updated_by TEXT DEFAULT 'Система',
                UNIQUE(group_name, subject_name)
            );
        """)

        await db.executemany("""
            INSERT INTO group_subjects (
                group_name, subject_name, teacher_name, exam_type, conspect, group_notes, updated_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(group_name, subject_name) DO UPDATE SET 
                teacher_name = excluded.teacher_name
        """, records_to_insert)
        await db.commit()

    return len(records_to_insert)


async def fetch_and_import_group_subjects(group_name: str) -> bool:
    """
    1. Пробует загрузить из локального файла storage/schedule_test.json (если есть)
    2. Если нет — запрашивает открытый сервер kabinet.kgeu.ru по ID группы!
    """
    # ВАРИАНТ А: Если в папке storage есть файл schedule_test.json
    local_file = STORAGE_DIR / "schedule_test.json"
    if local_file.exists():
        try:
            with open(local_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            count = await parse_and_save_schedule_subjects(data, group_name)
            if count > 0:
                print(f"✅ Из локального файла успешно импортировано {count} предметов для {group_name}!")
                return True
        except Exception as e:
            print(f"⚠️ Ошибка чтения локального файла: {e}")

    # ВАРИАНТ Б: Публичный сервер kabinet.kgeu.ru (без авторизации!)
    group_id = get_group_id(group_name)  # Достаем ID группы из groups.json (например 14515)
    if not group_id:
        return False

    url = f"https://kabinet.kgeu.ru/api/Rasp?idGroup={group_id}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    count = await parse_and_save_schedule_subjects(data, group_name)
                    return count > 0
    except Exception as e:
        print(f"⚠️ Открытый сервер kabinet.kgeu.ru недоступен: {e}")

    return False