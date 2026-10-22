from re import compile
import json
import difflib
from pathlib import Path

GROUP_PATTERN = compile(r"^[А-ЯЁ]{1,4}-\d{1,2}-\d{2}$")
BASE_DIR = Path(__file__).resolve().parent.parent
GROUPS_FILE = BASE_DIR / 'storage' / 'groups.json'


def load_kgeu_groups() -> dict[str, int]:
    """Загружает реальные группы КГЭУ в словарь: {'ЭП-1-23': 14349, ...}"""
    if not GROUPS_FILE.exists():
        print(f"⚠️ Внимание: {GROUPS_FILE} не найден!")
        return {}

    with open(GROUPS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Собираем словарь: название группы -> ID группы
    return {item["name"].upper(): item["id"] for item in data.get("data", [])}


# Загружаем базу групп один раз при старте
KGEU_GROUPS_MAP = load_kgeu_groups()


def change_raw_group(raw_group: str) -> str | None:
    """
    Принимает строку от пользователя (например, '  эп 1 23  ').
    Возвращает идеальное название ('ЭП-1-23'), ТОЛЬКО ЕСЛИ группа есть в КГЭУ.
    Иначе возвращает None.
    """
    if not raw_group:
        return None

    # Чистим пробелы и делаем заглавными: "  эп   1 23  " -> "ЭП-1-23"
    clean_group = "-".join(raw_group.strip().upper().split())

    # Проверяем по официальной базе 651 группы КГЭУ:
    if clean_group in KGEU_GROUPS_MAP:
        return clean_group

    return None


def get_group_id(group_name: str) -> int | None:
    """Возвращает системный ID группы в КГЭУ по её названию"""
    return KGEU_GROUPS_MAP.get(group_name.upper())


def get_similar_groups(raw_group: str, n: int = 3) -> list[str]:
    """Если студент ошибся в букве или цифре, находит похожие существующие группы"""
    clean_group = "-".join(raw_group.strip().upper().split())
    return difflib.get_close_matches(clean_group, KGEU_GROUPS_MAP.keys(), n=n, cutoff=0.5)