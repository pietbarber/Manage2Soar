"""
Operational Calendar utilities for duty roster generation.

Handles parsing club operational periods like "First weekend of May" 
and calculating the actual weekend dates for any given year.
"""

import calendar
from datetime import date, timedelta
from typing import Tuple


def find_weekend_for_week(year: int, month: int, week_ordinal: int) -> Tuple[date, date]:
    """
    Find the complete weekend (Saturday + Sunday) for the Nth week of a month.

    Args:
        year: The year
        month: The month (1-12)
        week_ordinal: Which week (1 = first, 2 = second, etc.)

    Returns:
        Tuple of (saturday_date, sunday_date) for that weekend

    Rules:
        - "First week" = the week containing the 1st of the month
        - Weekend = Saturday + Sunday pair  
        - If month starts on Sunday, include the previous Saturday
        - If month starts on Saturday, that Saturday starts the first weekend

    Examples:
        May 2022 (May 1st = Sunday):
        - First week = April 25-May 1
        - First weekend = April 30-May 1 (Sat-Sun)

        May 2021 (May 1st = Saturday):  
        - First week = May 1-7
        - First weekend = May 1-2 (Sat-Sun)
    """
    # Find the first day of the month
    first_of_month = date(year, month, 1)

    # Find what day of the week the 1st falls on (0=Monday, 6=Sunday)
    first_weekday = first_of_month.weekday()

    # Calculate the start of the first week (Monday of the week containing the 1st)
    # If the 1st is a Monday (weekday=0), then start_of_first_week = first_of_month
    # If the 1st is a Tuesday (weekday=1), then start_of_first_week = first_of_month - 1 day
    days_back_to_monday = first_weekday
    start_of_first_week = first_of_month - timedelta(days=days_back_to_monday)

    # Calculate the start of the target week
    start_of_target_week = start_of_first_week + timedelta(weeks=week_ordinal - 1)

    # Find Saturday and Sunday of that week
    # Monday = 0, Tuesday = 1, ..., Saturday = 5, Sunday = 6
    # 5 days after Monday = Saturday
    saturday = start_of_target_week + timedelta(days=5)
    sunday = start_of_target_week + timedelta(days=6)    # 6 days after Monday = Sunday

    return saturday, sunday


def parse_operational_period(period_text: str) -> Tuple[int, int]:
    """
    Parse operational period text like "First weekend of May" into components.

    Args:
        period_text: Text like "First weekend of May", "Second weekend of December", 
                    "1st weekend of Sep", "2nd weekend in December", etc.

    Returns:
        Tuple of (week_ordinal, month_number)

    Raises:
        ValueError: If the period text cannot be parsed
    """
    period_text = period_text.strip().lower()

    # Parse ordinal - support both word and numeric forms
    ordinal_map = {
        # Word forms
        'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'last': -1,
        # Numeric forms
        '1st': 1, '2nd': 2, '3rd': 3, '4th': 4,
        # Alternative spellings
        'one': 1, 'two': 2, 'three': 3, 'four': 4,
        # Common variations
        '1': 1, '2': 2, '3': 3, '4': 4,
    }

    # Parse month - support full names and common abbreviations
    month_map = {
        # Full month names
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12,
        # Common abbreviations
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
        'jun': 6, 'jul': 7, 'aug': 8,
        'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    }

    # Require the word "weekend" to be present
    if 'weekend' not in period_text:
        raise ValueError(
            f"Cannot parse operational period: '{period_text}'\n"
            f"Text must contain the word 'weekend'.\n"
            f"Examples: 'First weekend of May', '2nd weekend Dec'"
        )

    # Clean up the text - remove common connecting words
    cleaned_text = period_text.replace(' of ', ' ').replace(' in ', ' ')
    words = cleaned_text.split()

    ordinal = None
    month = None

    for word in words:
        # Remove punctuation for ordinal matching
        clean_word = word.rstrip('.,!?:;')

        if clean_word in ordinal_map:
            ordinal = ordinal_map[clean_word]
        elif clean_word in month_map:
            month = month_map[clean_word]

    if ordinal is None or month is None:
        # Create a helpful error message with suggestions
        examples = [
            "First weekend of May", "Second weekend of December",
            "1st weekend of Sep", "Last weekend in October",
            "Third weekend of April", "2nd weekend Dec"
        ]
        raise ValueError(
            f"Cannot parse operational period: '{period_text}'\n"
            f"Supported formats include: {', '.join(examples[:3])}, etc.\n"
            f"Ordinals: first/1st, second/2nd, third/3rd, fourth/4th, last\n"
            f"Months: Full names (January) or abbreviations (Jan, Sep, Dec)"
        )

    return ordinal, month


def get_operational_weekend(year: int, period_text: str) -> Tuple[date, date]:
    """
    Get the actual weekend dates for a given year and operational period.

    Args:
        year: The year to calculate for
        period_text: Text like "First weekend of May"

    Returns:
        Tuple of (saturday_date, sunday_date)

    Examples:
        get_operational_weekend(2022, "First weekend of May") 
        # Returns (date(2022, 4, 30), date(2022, 5, 1))

        get_operational_weekend(2021, "First weekend of May")
        # Returns (date(2021, 5, 1), date(2021, 5, 2))
    """
    ordinal, month = parse_operational_period(period_text)

    if ordinal == -1:  # "Last weekend"
        # Handle "last weekend of month" by finding the last Saturday in the month
        # Get the last day of the month
        last_day = calendar.monthrange(year, month)[1]
        last_date = date(year, month, last_day)

        # Find the last Saturday
        # weekday: Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
        days_back_to_saturday = (last_date.weekday() + 2) % 7
        if days_back_to_saturday == 0:  # Last day is already Saturday
            saturday = last_date
        else:
            # This handles all cases including when last day is Sunday (days_back = 1)
            saturday = last_date - timedelta(days=days_back_to_saturday)

        sunday = saturday + timedelta(days=1)
        return saturday, sunday
    else:
        return find_weekend_for_week(year, month, ordinal)


def test_weekend_calculations():
    """Test function to verify our weekend calculation logic."""

    test_cases = [
        # (year, period_text, expected_saturday, expected_sunday)
        (2022, "First weekend of May", date(2022, 4, 30),
         date(2022, 5, 1)),  # May 1st = Sunday
        (2021, "First weekend of May", date(2021, 5, 1),
         date(2021, 5, 2)),   # May 1st = Saturday
        (2023, "First weekend of May", date(2023, 5, 6),
         date(2023, 5, 7)),   # May 1st = Monday
        (2024, "First weekend of May", date(2024, 5, 4),
         date(2024, 5, 5)),   # May 1st = Wednesday
        (2025, "First weekend of May", date(2025, 5, 3),
         date(2025, 5, 4)),   # May 1st = Thursday
        (2025, "Second weekend of December", date(2025, 12, 13), date(2025, 12, 14)),
    ]

    # Test various input format variations
    format_variations = [
        # (input_format, expected_ordinal, expected_month)
        ("First weekend of May", 1, 5),
        ("1st weekend of May", 1, 5),
        ("Second weekend of December", 2, 12),
        ("2nd weekend of Dec", 2, 12),
        ("Third weekend in September", 3, 9),
        ("3rd weekend of Sep", 3, 9),
        ("Last weekend of October", -1, 10),
        ("Last weekend Oct", -1, 10),
        ("Fourth weekend in April", 4, 4),
        ("4th weekend of Apr", 4, 4),
        ("1 weekend of January", 1, 1),
        ("2 weekend in Feb", 2, 2),
    ]

    print("Testing weekend calculation logic:")
    print("=" * 50)

    for year, period_text, expected_sat, expected_sun in test_cases:
        actual_sat, actual_sun = get_operational_weekend(year, period_text)

        # Show what day of the week the 1st falls on for context
        ordinal, month = parse_operational_period(period_text)
        first_of_month = date(year, month, 1)
        first_day_name = first_of_month.strftime('%A')

        status_sat = "✅" if actual_sat == expected_sat else "❌"
        status_sun = "✅" if actual_sun == expected_sun else "❌"

        print(f"\n{year} {period_text}")
        print(f"  {first_of_month.strftime('%B')} 1st = {first_day_name}")
        print(f"  Expected: {expected_sat} - {expected_sun}")
        print(f"  Actual:   {actual_sat} - {actual_sun} {status_sat}{status_sun}")

    print(f"\n\nTesting input format variations:")
    print("=" * 50)

    for input_text, expected_ordinal, expected_month in format_variations:
        try:
            actual_ordinal, actual_month = parse_operational_period(input_text)
            status = "✅" if (
                actual_ordinal == expected_ordinal and actual_month == expected_month) else "❌"
            print(f"'{input_text}' → ordinal={actual_ordinal}, month={actual_month} {status}")
        except ValueError as e:
            print(f"'{input_text}' → ERROR: {e} ❌")


if __name__ == "__main__":
    test_weekend_calculations()
