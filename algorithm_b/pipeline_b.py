"""Run the Algorithm B pipeline.

Usage:
    Use `run_single_question()` for one Telegram question and
    `run_telegram_qa_loop()` for a batch of question events.

Input spec:
    - `mapping_path`: path to the customer-to-group mapping JSON.
    - `main_store_path`: path to the full group-message JSON store.
    - `output_dir`: directory for customer-specific JSON files.
    - `customer_name`: one customer identifier.
    - `question`: one Telegram question.
    - `question_events`: ordered `(customer_name, question)` pairs.
    - `reload_mapping`: refresh mapping before handling a question.

Output spec:
    - `prepare_customer_json_paths()` returns `{customer_name: json_path}`.
    - `run_single_question()` returns one answer string.
    - `run_telegram_qa_loop()` returns answer strings in event order.
"""

from algorithm_b.answer_customer_question import answer_customer_question
from algorithm_b.load_customer_context import load_customer_context
from algorithm_b.load_customer_group_mapping import load_customer_group_mapping
from algorithm_b.reload_customer_group_mapping import reload_customer_group_mapping
from algorithm_b.split_customer_json import split_customer_json


def prepare_customer_json_paths(
    mapping_path: str,
    main_store_path: str,
    output_dir: str,
) -> dict[str, str]:
    assert mapping_path
    assert main_store_path
    assert output_dir

    customer_group_mapping = load_customer_group_mapping(mapping_path)
    customer_json_path_by_customer = split_customer_json(
        main_store_path,
        customer_group_mapping,
        output_dir,
    )
    return customer_json_path_by_customer


def reload_customer_json_paths(
    mapping_path: str,
    main_store_path: str,
    output_dir: str,
) -> dict[str, str]:
    assert mapping_path
    assert main_store_path
    assert output_dir

    customer_group_mapping = reload_customer_group_mapping(mapping_path)
    customer_json_path_by_customer = split_customer_json(
        main_store_path,
        customer_group_mapping,
        output_dir,
    )
    return customer_json_path_by_customer


def run_single_question(
    mapping_path: str,
    main_store_path: str,
    output_dir: str,
    customer_name: str,
    question: str,
    reload_mapping: bool = True,
) -> str:
    assert mapping_path
    assert main_store_path
    assert output_dir
    assert customer_name
    assert question

    if reload_mapping:
        customer_json_path_by_customer = reload_customer_json_paths(
            mapping_path,
            main_store_path,
            output_dir,
        )
    else:
        customer_json_path_by_customer = prepare_customer_json_paths(
            mapping_path,
            main_store_path,
            output_dir,
        )

    customer_json_path = customer_json_path_by_customer[customer_name]
    customer_context = load_customer_context(customer_name, customer_json_path)
    answer = answer_customer_question(customer_name, question, customer_context)
    return answer


def run_telegram_qa_loop(
    mapping_path: str,
    main_store_path: str,
    output_dir: str,
    question_events: list[tuple[str, str]],
    reload_mapping_each_question: bool = True,
) -> list[str]:
    assert mapping_path
    assert main_store_path
    assert output_dir
    assert question_events

    answers: list[str] = []

    for customer_name, question in question_events:
        answer = run_single_question(
            mapping_path=mapping_path,
            main_store_path=main_store_path,
            output_dir=output_dir,
            customer_name=customer_name,
            question=question,
            reload_mapping=reload_mapping_each_question,
        )
        answers.append(answer)

    return answers


def run_customer_question_loop(
    mapping_path: str,
    main_store_path: str,
    output_dir: str,
    question_events: list[tuple[str, str]],
    reload_mapping_each_question: bool = True,
) -> list[str]:
    return run_telegram_qa_loop(
        mapping_path=mapping_path,
        main_store_path=main_store_path,
        output_dir=output_dir,
        question_events=question_events,
        reload_mapping_each_question=reload_mapping_each_question,
    )
