"""Answer a customer question with customer-specific message context.

Usage:
    Call this after loading the customer context for one question.

Input spec:
    - `customer_name`: customer identifier.
    - `question`: question received from Telegram.
    - `customer_context`: customer-specific message dictionaries.

Output spec:
    - Returns the final answer string sent back to the customer.
"""


def answer_customer_question(
    customer_name: str,
    question: str,
    customer_context: list[dict[str, str]],
) -> str:
    assert customer_name
    assert question
    assert customer_context
    raise NotImplementedError("Implement customer question answering.")
