import json
import sys

from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
    ValidationError
)

from jsonschema import (
    validate,
    ValidationError as SchemaError
)


# ==========================================
# 1. PATH CONFIGURATION
# ==========================================

# Корневая директория проекта QA-06_agent1
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# JSON Schema
SCHEMA_PATH = (
    PROJECT_ROOT / ".opencode/schemas/security-schema.json"
)

# Результат работы Security Guardrail Agent
ARTIFACT_PATH = (
    PROJECT_ROOT / "artifacts/security-review.json"
)


# ==========================================
# 2. PYDANTIC MODELS
# ==========================================

class DetectedItem(BaseModel):

    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "EMAIL",
        "PHONE",
        "PERSON",
        "PASSWORD",
        "API_KEY",
        "TOKEN",
        "OTHER"
    ]

    count: int = Field(ge=1)


class SecurityReviewArtifact(BaseModel):

    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "PASS",
        "MASKED",
        "BLOCKED"
    ]

    pageId: str = Field(min_length=1)

    detected: list[DetectedItem]

    clean_requirements: str


# ==========================================
# 3. READ JSON FILES
# ==========================================

def load_json(path: Path) -> dict:

    if not path.exists():
        raise FileNotFoundError(
            f"Файл не найден: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


# ==========================================
# 4. JSON SCHEMA VALIDATION
# ==========================================

def validate_json_schema(
    data: dict,
    schema: dict
) -> bool:

    try:

        validate(
            instance=data,
            schema=schema
        )

        print("JSON Schema: VALID")

        return True

    except SchemaError as error:

        print("JSON Schema: INVALID")
        print(f"Причина: {error.message}")

        return False


# ==========================================
# 5. PYDANTIC VALIDATION
# ==========================================

def validate_pydantic(data: dict) -> bool:

    try:

        artifact = SecurityReviewArtifact.model_validate(
            data,
            strict=True
        )

        print("Pydantic: VALID")
        print(f"Status: {artifact.status}")

        return True

    except ValidationError as error:

        print("Pydantic: INVALID")

        for item in error.errors():

            field = ".".join(
                str(part)
                for part in item["loc"]
            )

            print(
                f"Поле: {field} | "
                f"Ошибка: {item['msg']}"
            )

        return False


# ==========================================
# 6. MAIN
# ==========================================

def main():

    print("\n=== SECURITY REVIEW VALIDATION ===\n")

    try:

        # Загружаем результат агента
        data = load_json(ARTIFACT_PATH)

        # Загружаем контракт
        schema = load_json(SCHEMA_PATH)

        # Проверяем JSON Schema
        schema_valid = validate_json_schema(
            data,
            schema
        )

        print()

        # Проверяем Pydantic
        pydantic_valid = validate_pydantic(
            data
        )

        print("\n==================================")

        # Общий результат проверки
        if schema_valid and pydantic_valid:

            print("VALIDATION RESULT: PASS")

            return 0

        else:

            print("VALIDATION RESULT: BLOCKED")

            return 1

    except (
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
        ValueError
    ) as error:

        print(f"Ошибка чтения данных: {error}")

        print("VALIDATION RESULT: BLOCKED")

        return 1


# ==========================================
# 7. ENTRY POINT
# ==========================================

if __name__ == "__main__":

    sys.exit(main())