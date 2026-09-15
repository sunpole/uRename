import argparse
import json
import os
import re
import sys


MASK_FILE_NAME = "mask.txt"
FILES_FILE_NAME = "files.txt"

# Популярная таблица транслитерации: буква -> латинская замена
TRANSLIT_MAP = {
    "А": "A", "а": "a", "Б": "B", "б": "b", "В": "V", "в": "v",
    "Г": "G", "г": "g", "Д": "D", "д": "d", "Е": "E", "е": "e",
    "Ё": "Yo", "ё": "yo", "Ж": "Zh", "ж": "zh", "З": "Z", "з": "z",
    "И": "I", "и": "i", "Й": "Y", "й": "y", "К": "K", "к": "k",
    "Л": "L", "л": "l", "М": "M", "м": "m", "Н": "N", "н": "n",
    "О": "O", "о": "o", "П": "P", "п": "p", "Р": "R", "р": "r",
    "С": "S", "с": "s", "Т": "T", "т": "t", "У": "U", "у": "u",
    "Ф": "F", "ф": "f", "Х": "Kh", "х": "kh", "Ц": "Ts", "ц": "ts",
    "Ч": "Ch", "ч": "ch", "Ш": "Sh", "ш": "sh", "Щ": "Shch", "щ": "shch",
    "Ъ": "", "ъ": "", "Ы": "Y", "ы": "y", "Ь": "", "ь": "",
    "Э": "E", "э": "e", "Ю": "Yu", "ю": "yu", "Я": "Ya", "я": "ya",
}

VALID_MASK_RE = re.compile(r"^[9Aa_]+$")
INVALID_FILENAME_CHARS_RE = re.compile(r"[^A-Za-z0-9]+")
SOURCE_TOKEN_RE = re.compile(r"[0-9]+|[A-Za-z]+")
MASK_PART_RE = re.compile(r"9+|[Aa]+|_+")
# Границы слова допускают подчёркивания, но не удаление внутри другого слова.
INSTRUCTION_RE = re.compile(
    r"(?<![^\W_])инструкци(?:я|и|ю|ей|ею|ям|ями|ях|й)(?![^\W_])",
    re.IGNORECASE,
)


def transliterate(text: str) -> str:
    """Переводит русские буквы в латиницу."""
    return "".join(TRANSLIT_MAP.get(char, char) for char in text)


def normalize_stem(stem: str) -> str:
    """Оставляет в имени только латинские буквы, цифры и подчёркивания."""
    latin_stem = transliterate(stem)
    normalized = INVALID_FILENAME_CHARS_RE.sub("_", latin_stem)
    return normalized.strip("_")


def load_config(mask_path: str) -> tuple[str, bool]:
    """Читает маску и необязательную команду !инструкция."""
    if not os.path.exists(mask_path):
        raise ValueError(f"Файл маски не найден: {mask_path}")

    with open(mask_path, "r", encoding="utf-8-sig") as mask_file:
        masks = [
            line.strip()
            for line in mask_file
            if line.strip() and not line.lstrip().startswith("#")
        ]

    drop_instruction = any(line.casefold() == "!инструкция" for line in masks)
    masks = [line for line in masks if line.casefold() != "!инструкция"]
    for line in masks:
        if line.startswith("!"):
            raise ValueError(f"Неизвестная команда {line}. Доступна команда !инструкция.")

    if not masks:
        raise ValueError("В mask.txt нет строки с маской.")
    if len(masks) > 1:
        raise ValueError("В mask.txt должна быть только одна строка с маской.")

    mask = masks[0]
    if not VALID_MASK_RE.fullmatch(mask):
        raise ValueError(
            "Маска может содержать только символы 9, A, a и подчёркивание (_)."
        )
    if not any(symbol in mask for symbol in "9Aa"):
        raise ValueError("В маске должен быть хотя бы один символ 9, A или a.")

    return mask, drop_instruction


def load_mask(mask_path: str) -> str:
    return load_config(mask_path)[0]


def format_token(source_token: str, mask_part: str) -> str:
    """Обрезает часть имени по маске, задаёт регистр или добавляет нули."""
    width = len(mask_part)
    if mask_part.startswith("9"):
        if len(source_token) > width:
            raise ValueError(
                f"Номер {source_token} не помещается в блок {mask_part}. "
                "Добавьте символы 9 в mask.txt."
            )
        return source_token.zfill(width)

    source_token = source_token[:width]
    return "".join(
        char.upper() if placeholder == "A" else char.lower()
        for char, placeholder in zip(source_token, mask_part)
    )


def apply_mask(stem: str, mask: str, drop_instruction: bool = False) -> str:
    """Собирает новое имя из цифровых и буквенных частей исходного имени."""
    if drop_instruction:
        stem = INSTRUCTION_RE.sub(" ", stem)
    source_tokens = SOURCE_TOKEN_RE.findall(normalize_stem(stem))
    mask_parts = MASK_PART_RE.findall(mask)
    values = [None] * len(mask_parts)

    # Номера в начале имени выравниваются по последним числовым блокам маски.
    # Поэтому один номер при маске 99_999_A... попадает в блок 999, а 99 пропускается.
    first_letter_mask_index = next(
        (index for index, part in enumerate(mask_parts) if part.startswith(("A", "a"))),
        len(mask_parts),
    )
    leading_number_mask_indices = [
        index
        for index, part in enumerate(mask_parts[:first_letter_mask_index])
        if part.startswith("9")
    ]

    first_letter_source_index = next(
        (index for index, token in enumerate(source_tokens) if token.isalpha()),
        len(source_tokens),
    )
    leading_source_numbers = source_tokens[:first_letter_source_index]
    matched_count = min(len(leading_number_mask_indices), len(leading_source_numbers))

    if matched_count:
        for mask_index, source_token in zip(
            leading_number_mask_indices[-matched_count:],
            leading_source_numbers[-matched_count:],
        ):
            values[mask_index] = format_token(source_token, mask_parts[mask_index])

    token_index = first_letter_source_index
    leading_number_mask_indices = set(leading_number_mask_indices)

    # Остальные буквенные и числовые блоки сопоставляются частям исходного имени по порядку.
    for mask_index, mask_part in enumerate(mask_parts):
        if mask_part.startswith("_") or mask_index in leading_number_mask_indices:
            continue

        need_digits = mask_part.startswith("9")
        for source_index in range(token_index, len(source_tokens)):
            source_token = source_tokens[source_index]
            if source_token.isdigit() == need_digits:
                values[mask_index] = format_token(source_token, mask_part)
                token_index = source_index + 1
                break

    # Разделители добавляются только между реально найденными частями.
    result = []
    pending_separator = ""
    for mask_part, value in zip(mask_parts, values):
        if mask_part.startswith("_"):
            if result:
                pending_separator = mask_part
        elif value:
            if result and pending_separator:
                result.append(pending_separator)
            result.append(value)
            pending_separator = ""

    return "".join(result)


def shorten_filename(full_path: str, mask: str, drop_instruction: bool = False) -> str:
    """Формирует новое имя по маске и сохраняет исходное расширение."""
    directory = os.path.dirname(full_path)
    base_name = os.path.basename(full_path)
    stem, extension = os.path.splitext(base_name)
    masked_stem = apply_mask(stem, mask, drop_instruction)

    if not masked_stem:
        raise ValueError(f"После обработки имя стало пустым: {base_name}")
    if re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", masked_stem, re.IGNORECASE):
        raise ValueError(f"Имя {masked_stem} зарезервировано Windows. Измените маску.")
    if len((masked_stem + extension).encode("utf-16-le")) // 2 > 255:
        raise ValueError("Новое имя слишком длинное для Windows. Укоротите маску.")

    return os.path.join(directory, masked_stem + extension)


def read_file_list(list_path: str) -> list[str]:
    """Читает пути, в том числе пути в обычных двойных или одинарных кавычках."""
    if not os.path.exists(list_path):
        raise ValueError(f"Файл со списком не найден: {list_path}")

    result = []
    with open(list_path, "r", encoding="utf-8-sig") as list_file:
        for raw_line in list_file:
            path = raw_line.strip()
            if not path:
                continue
            if len(path) >= 2 and path[0] == path[-1] and path[0] in {'"', "'"}:
                path = path[1:-1].strip()
            if path:
                if not os.path.isabs(path):
                    path = os.path.join(os.path.dirname(os.path.abspath(list_path)), path)
                result.append(os.path.normpath(path))
    return result


def same_path(first: str, second: str) -> bool:
    return os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second))


def initialize_config(script_dir: str) -> list[str]:
    """Создаёт только отсутствующие настройки; личные файлы не перезаписываются."""
    created = []
    for name, fallback in [(FILES_FILE_NAME, ""), (MASK_FILE_NAME, "99_999_Aaaaaaaaaa\n!инструкция\n")]:
        target = os.path.join(script_dir, name)
        if os.path.exists(target):
            continue
        example = os.path.join(script_dir, name.replace(".txt", ".example.txt"))
        if os.path.isfile(example):
            with open(example, encoding="utf-8-sig") as source:
                content = source.read()
        else:
            content = fallback
        try:
            with open(target, "x", encoding="utf-8") as destination:
                destination.write(content)
        except FileExistsError:
            continue
        created.append(name)
    return created


def build_plan(file_list: list[str], mask: str, drop_instruction: bool = False) -> list[tuple[str, str]]:
    """Проверяет весь список до первого переименования."""
    plan = []
    sources = set()
    targets = {}
    errors = []
    for old_path in file_list:
        source_key = os.path.normcase(os.path.abspath(old_path))
        if source_key in sources:
            continue
        sources.add(source_key)
        try:
            if os.path.islink(old_path):
                raise ValueError("символические ссылки не поддерживаются; укажите обычный файл")
            if not os.path.isfile(old_path):
                raise ValueError("файл не найден или путь указывает на папку")
            new_path = shorten_filename(old_path, mask, drop_instruction)
            target_key = os.path.normcase(os.path.abspath(new_path))
            if target_key in targets:
                raise ValueError(
                    f"то же новое имя, что у {targets[target_key]}: {os.path.basename(new_path)}"
                )
            targets[target_key] = old_path
            if os.path.lexists(new_path) and not same_path(old_path, new_path):
                raise ValueError(f"новое имя уже занято: {os.path.basename(new_path)}")
            plan.append((old_path, new_path))
        except (OSError, ValueError) as error:
            errors.append(f"{old_path}: {error}")
    if errors:
        raise ValueError("\n".join(errors))
    return plan


def main(argv=None, script_dir=None) -> int:
    parser = argparse.ArgumentParser(description="Переименование файлов по маске из mask.txt")
    parser.add_argument("--preview", action="store_true", help="показать новые имена без переименования")
    parser.add_argument("--version", action="store_true", help="показать версию")
    parser.add_argument("--init", action="store_true", help="создать отсутствующие настройки")
    args = parser.parse_args(argv)
    script_dir = script_dir or os.path.dirname(os.path.abspath(__file__))
    list_path = os.path.join(script_dir, FILES_FILE_NAME)
    mask_path = os.path.join(script_dir, MASK_FILE_NAME)

    try:
        if args.version:
            with open(os.path.join(script_dir, "version.json"), encoding="utf-8") as source:
                print("uRename " + json.load(source)["version"])
            return 0
        created = initialize_config(script_dir)
        if created or args.init:
            print("Настройки: " + (", ".join(created) + " созданы." if created else "уже существуют."))
            print("Заполните files.txt, проверьте mask.txt и запустите preview_rename.bat.")
            return 0
        if os.name != "nt" and not args.preview:
            raise ValueError("Переименование поддерживается только в Windows. Для просмотра используйте --preview.")
        mask, drop_instruction = load_config(mask_path)
        file_list = read_file_list(list_path)
        plan = build_plan(file_list, mask, drop_instruction)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        print(f"ОШИБКА: {error}")
        return 1

    if not file_list:
        print("ОШИБКА: в files.txt нет путей к файлам.")
        return 1

    print(f"\nИспользуется маска: {mask}")
    if drop_instruction:
        print("Удаление слова «инструкция» и его падежных форм: включено.")
    if args.preview:
        for old_path, new_path in plan:
            print(f"{os.path.basename(old_path)} -> {os.path.basename(new_path)}")
        print(f"\nПроверено файлов: {len(plan)}. Это только просмотр.")
        return 0

    print("Начинаем переименование...")
    error_count = 0

    for old_path, new_path in plan:
        try:
            if not os.path.isfile(old_path):
                raise FileNotFoundError("исходный файл не найден")
            if os.path.abspath(old_path) == os.path.abspath(new_path):
                print(f"БЕЗ ИЗМЕНЕНИЙ: {os.path.basename(old_path)}")
                continue
            if os.path.lexists(new_path) and not same_path(old_path, new_path):
                raise FileExistsError(
                    f"файл с новым именем уже существует: {os.path.basename(new_path)}"
                )

            os.rename(old_path, new_path)
            print(f"OK: {os.path.basename(old_path)} -> {os.path.basename(new_path)}")
        except (OSError, ValueError) as error:
            error_count += 1
            print(f"ОШИБКА: {old_path}: {error}")

    if error_count:
        print(f"\nГотово с ошибками: {error_count}.")
        return 1

    print("\nГотово без ошибок.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
