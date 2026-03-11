"""Load the customer-specific message context used for question answering.

Usage:
    Call this for each incoming customer question.

Input spec:
    - `customer_name`: customer identifier.
    - `customer_json_path`: path to the customer's JSON file.

Output spec:
    - Returns message dictionaries used as LLM context.
"""


def load_customer_context(
    customer_name: str,
    customer_json_path: str,
) -> list[dict[str, str]]:
    assert customer_name
    assert customer_json_path
    raise NotImplementedError("Implement customer context loading.")
