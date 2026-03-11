"""Load the customer-to-group mapping configuration.

Usage:
    Call this before customer JSON splitting or question handling.

Input spec:
    - `mapping_path`: path to the mapping JSON file.

Output spec:
    - Returns `{customer_name: [group_name, ...]}`.
"""


def load_customer_group_mapping(mapping_path: str) -> dict[str, list[str]]:
    assert mapping_path
    raise NotImplementedError("Implement customer-group mapping loading.")
