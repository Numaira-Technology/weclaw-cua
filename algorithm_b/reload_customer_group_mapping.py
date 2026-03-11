"""Reload the customer-to-group mapping after external updates.

Usage:
    Call this when the mapping can change while the bot is running.

Input spec:
    - `mapping_path`: path to the mapping JSON file.

Output spec:
    - Returns the latest `{customer_name: [group_name, ...]}` mapping.
"""


def reload_customer_group_mapping(mapping_path: str) -> dict[str, list[str]]:
    assert mapping_path
    raise NotImplementedError("Implement mapping hot reload.")
