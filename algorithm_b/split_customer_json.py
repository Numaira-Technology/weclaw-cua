"""Build customer-specific JSON views from the main group store.

Usage:
    Call this after loading the customer-to-group mapping.

Input spec:
    - `main_store_path`: path to the main group-message JSON store.
    - `customer_group_mapping`: mapping from customer to group names.
    - `output_dir`: directory for customer-specific JSON files.

Output spec:
    - Returns `{customer_name: customer_json_path}`.
"""


def split_customer_json(
    main_store_path: str,
    customer_group_mapping: dict[str, list[str]],
    output_dir: str,
) -> dict[str, str]:
    assert main_store_path
    assert customer_group_mapping
    assert output_dir
    raise NotImplementedError("Implement customer JSON splitting.")
