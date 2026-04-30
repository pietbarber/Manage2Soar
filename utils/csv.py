"""Shared CSV utilities used across multiple apps."""


def sanitize_csv_cell(value):
    """Neutralize spreadsheet-formula strings in CSV cells.

    Values starting with ``=``, ``+``, ``-``, or ``@`` are prefixed with a
    single quote so they are treated as plain text when opened in Excel or
    Google Sheets (CSV injection / formula injection prevention).
    """
    if not isinstance(value, str):
        return value

    stripped = value.lstrip()
    if stripped.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value
