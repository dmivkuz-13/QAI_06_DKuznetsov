import json
import subprocess
import sys
from pathlib import Path


# =============================================================
# PATHS
# =============================================================

# Корень проекта QAI-05_adv1
project_path = Path(__file__).resolve().parent.parent


# Допуск на расхождение mtime файлов и времени старта прогона.
ARTIFACT_FRESHNESS_TOLERANCE_SECONDS = 2.0


# =============================================================
# ПРОВЕРКИ АРТЕФАКТОВ
# =============================================================

def _check_artifact(artifact_name, run_started_at, required):
    """
    Проверяет, что артефакт существует и обновлён в текущем прогоне.

    Проверка детерминированная (по mtime файлов) и не передаётся
    LLM-судье. Для обязательного артефакта отсутствие или устаревание
    делает Eval Case FAIL; для опционального — только фиксируется.
    """

    result = {
        "property": (
            f"Артефакт artifacts/{artifact_name} создан или обновлён "
            f"в текущем прогоне"
        ),
        "passed": True,
        "reason": ""
    }

    artifact_dir = project_path / "artifacts" / artifact_name

    files = []

    if artifact_dir.is_dir():

        files = sorted(
            artifact_dir.glob("*.md"),
            key=lambda path: path.stat().st_mtime
        )


    if not files:

        result["passed"] = not required

        result["reason"] = (
            f"артефакт artifacts/{artifact_name} не найден"
            if required
            else f"опциональный артефакт artifacts/{artifact_name} отсутствует"
        )

        return result


    newest_file = files[-1]

    newest_mtime = newest_file.stat().st_mtime


    if run_started_at is None:

        result["reason"] = (
            f"актуальность не проверялась; "
            f"последний файл: {newest_file.name}"
        )

        return result


    if newest_mtime + ARTIFACT_FRESHNESS_TOLERANCE_SECONDS < run_started_at:

        result["passed"] = not required

        result["reason"] = (
            f"{newest_file.name} не обновлялся в текущем прогоне"
            if required
            else f"опциональный {newest_file.name} не обновлялся в текущем прогоне"
        )

        return result


    result["reason"] = (
        f"{newest_file.name} обновлён в текущем прогоне"
    )

    return result


def _check_artifacts(artifact_checks, run_started_at):
    """
    Выполняет проверки артефактов из Eval Case.

    artifact_checks имеет вид:
    {
        "required": ["requirement-review", "jira-tasks", "test-model"],
        "optional": ["pipeline-report"]
    }

    Возвращает (results, blocking_failures).
    """

    results = []

    blocking_failures = []


    for artifact_name in artifact_checks.get("required", []):

        result = _check_artifact(
            artifact_name,
            run_started_at,
            required=True
        )

        results.append(result)

        if not result["passed"]:

            blocking_failures.append(result)


    for artifact_name in artifact_checks.get("optional", []):

        result = _check_artifact(
            artifact_name,
            run_started_at,
            required=False
        )

        results.append(result)


    return results, blocking_failures


# =============================================================
# EVALUATOR
# =============================================================

def evaluate_response(
        eval_case,
        agent_response,
        page_id=None,
        run_started_at=None
):

    # ---------------------------------------------------------
    # INPUT EVAL CASE
    # ---------------------------------------------------------

    eval_input = eval_case["input"]

    source = eval_input.get("source")


    # ---------------------------------------------------------
    # ОПИСАНИЕ ИСТОЧНИКА
    # ---------------------------------------------------------

    if source == "inline":

        input_description = eval_input["requirements"]

    elif source == "confluence":

        # Для универсальных E2E-кейсов в eval_case может быть
        # placeholder (ANY), а фактический pageId приходит из Runner.
        effective_page_id = page_id or eval_input.get("page_id")

        input_description = (
            f"Требования находятся в Confluence. "
            f"pageId={effective_page_id}."
        )

    else:

        input_description = str(eval_input)


    # ---------------------------------------------------------
    # ПРОВЕРКИ, ВЫПОЛНЯЕМЫЕ КОДОМ (без LLM)
    # ---------------------------------------------------------

    artifact_checks = eval_case.get("artifact_checks")

    artifact_results = []

    blocking_artifact_failures = []


    if artifact_checks:

        artifact_results, blocking_artifact_failures = _check_artifacts(
            artifact_checks,
            run_started_at
        )


    # =========================================================
    # PROMPT ДЛЯ LLM-AS-A-JUDGE
    # =========================================================

    judge_prompt = f"""
Ты — независимый Evaluator результатов AI QA Agent.
Твоя задача — оценить фактический ответ агента
относительно заданного Eval Case.
ПРАВИЛА ОЦЕНКИ:
1. Оценивай смысл ответа, а не точное совпадение формулировок.
2. Не добавляй собственные требования.
3. Каждое Expected Property оцени отдельно.
4. Каждое Forbidden Behavior оцени отдельно.
5. Expected Property считается выполненным,
если ответ агента явно или семантически подтверждает
требуемое поведение.
6. Forbidden Behavior считается нарушенным только тогда,
когда агент действительно совершил запрещённое действие.
7. Итоговый статус PASS возможен только если:
- выполнены ВСЕ Expected Properties;
- не нарушено НИ ОДНО Forbidden Behavior.
8. Если хотя бы одно Expected Property не выполнено,
итоговый статус должен быть FAIL.
9. Если хотя бы одно Forbidden Behavior нарушено,
итоговый статус должен быть FAIL.
EVAL CASE ID:
{eval_case["id"]}
INPUT SOURCE:
{source}
INPUT:
{input_description}
EXPECTED PROPERTIES:
{json.dumps(
        eval_case["expected_properties"],
        ensure_ascii=False,
        indent=2
    )}
FORBIDDEN BEHAVIOR:
{json.dumps(
        eval_case["forbidden_behavior"],
        ensure_ascii=False,
        indent=2
    )}
ACTUAL AGENT RESPONSE:
{agent_response}
Верни ТОЛЬКО валидный JSON следующей структуры:
{{
  "eval_case_id": "{eval_case["id"]}",
  "expected_properties": [
    {{
      "property": "текст проверяемого Expected Property",
      "passed": true,
      "reason": "краткое объяснение решения"
    }}
  ],
  "forbidden_behavior": [
    {{
      "rule": "текст проверяемого Forbidden Behavior",
      "violated": false,
      "reason": "краткое объяснение решения"
    }}
  ],
  "status": "PASS",
  "score": 1.0
}}
ПРАВИЛА SCORE:
1.0 — PASS.
0.0 — FAIL.
ВАЖНО:
Не используй Markdown.
Не используй ```json.
Не используй ```.
Не добавляй пояснения до JSON.
Не добавляй пояснения после JSON.
Ответ должен содержать только один JSON-объект.
"""


    # =========================================================
    # ЗАПУСК EVALUATOR
    # =========================================================

    prompt_file = project_path / "evals" / ".tmp_judge_prompt.txt"
    prompt_file.write_text(judge_prompt, encoding="utf-8")

    process = subprocess.Popen(
        [
            "opencode",
            "run",
            "-m",
            # "cloudru/deepseek-ai/DeepSeek-V4-Flash",
            "llm-router-org/deepseek-v4-flash",
            "--format",
            "json",
            str(prompt_file)
        ],
        cwd=project_path,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        shell=(sys.platform == "win32")
    )


    # Здесь собираем текстовый ответ Evaluator.
    text_parts = []


    print("Evaluator запущен...")


    # =========================================================
    # ЧТЕНИЕ JSON EVENTS
    # =========================================================

    if process.stdout:

        for line in process.stdout:

            line = line.strip()

            if not line:
                continue

            try:

                event = json.loads(line)

                event_type = event.get("type")

                print(
                    "EVALUATOR EVENT:",
                    event_type,
                    flush=True
                )


                # Забираем только текстовые события.
                if event_type == "text":

                    part = event.get("part", {})

                    text = part.get("text")

                    if text:
                        text_parts.append(text)


                elif event_type == "error":

                    error_msg = event.get("message", str(event))
                    print(
                        "EVALUATOR ERROR DETAILS:",
                        error_msg,
                        flush=True
                    )


            except json.JSONDecodeError:

                print(
                    "Не удалось разобрать событие Evaluator",
                    flush=True
                )


    # =========================================================
    # ЗАВЕРШЕНИЕ EVALUATOR
    # =========================================================

    return_code = process.wait()

    # Удаляем временный файл
    try:
        prompt_file.unlink()
    except Exception:
        pass


    print(
        "EVALUATOR RETURN CODE:",
        return_code
    )


    # ---------------------------------------------------------
    # ПРОВЕРКА RETURN CODE
    # ---------------------------------------------------------

    if return_code != 0:

        stderr = ""

        if process.stderr:
            stderr = process.stderr.read()

        raise RuntimeError(
            f"Evaluator завершился с ошибкой. "
            f"Return code: {return_code}. "
            f"STDERR: {stderr}"
        )


    # =========================================================
    # СБОРКА ОТВЕТА
    # =========================================================

    judge_response = "\n".join(
        text_parts
    ).strip()


    if not judge_response:

        raise RuntimeError(
            "Evaluator не вернул текстовый ответ."
        )


    # =========================================================
    # ИЗВЛЕЧЕНИЕ JSON ИЗ ОТВЕТА
    # =========================================================

    # Модель может добавить пояснения до/после JSON.
    # Находим первый '{' и последний '}' и берём подстроку.
    start = judge_response.find("{")
    end = judge_response.rfind("}")

    if start != -1 and end != -1 and end > start:
        judge_response = judge_response[start:end + 1]

    # На случай, если модель вернула ```json ... ```
    if judge_response.startswith("```json"):
        judge_response = judge_response[7:]
    elif judge_response.startswith("```"):
        judge_response = judge_response[3:]

    if judge_response.endswith("```"):
        judge_response = judge_response[:-3]

    judge_response = judge_response.strip()


    # =========================================================
    # JSON PARSING
    # =========================================================

    try:

        evaluation_result = json.loads(
            judge_response
        )

    except json.JSONDecodeError as error:

        print()
        print(
            "Не удалось разобрать ответ "
            "Evaluator как JSON."
        )

        print()
        print("Фактический ответ Evaluator:")

        print(judge_response)

        raise RuntimeError(
            "Evaluator вернул невалидный JSON."
        ) from error


    # =========================================================
    # ПРОВЕРКА СТРУКТУРЫ (с поддержкой обоих написаний)
    # =========================================================

    # Нормализация: если модель вернула британское "behaviour",
    # приводим к американскому "behavior", которое ожидает Runner.
    for brit, amer in [
        ("forbidden_behaviour", "forbidden_behavior"),
        ("expected_properties", "expected_properties"),
    ]:
        if brit != amer and brit in evaluation_result and amer not in evaluation_result:
            evaluation_result[amer] = evaluation_result.pop(brit)

    required_fields = [
        "eval_case_id",
        "expected_properties",
        "forbidden_behavior",
        "status",
        "score"
    ]


    for field in required_fields:

        if field not in evaluation_result:

            raise RuntimeError(
                f"В ответе Evaluator отсутствует "
                f"обязательное поле: {field}"
            )


    # =========================================================
    # ДЕТЕРМИНИРОВАННЫЕ ПРОВЕРКИ АРТЕФАКТОВ
    # =========================================================

    # Результаты проверки артефактов добавляются к Expected Properties.
    # Для обязательных артефактов любое нарушение переводит кейс в FAIL,
    # независимо от оценки LLM-судьи.

    if artifact_results:

        evaluation_result["expected_properties"].extend(
            artifact_results
        )


    if blocking_artifact_failures:

        evaluation_result["status"] = "FAIL"

        evaluation_result["score"] = 0.0


    # =========================================================
    # RETURN
    # =========================================================

    return evaluation_result