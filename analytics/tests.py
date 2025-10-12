from django.test import TestCase
from analytics.queries import time_of_day_operations


class TimeOfDayOperationsTestCase(TestCase):
    """Test the time_of_day_operations query function."""

    def test_time_of_day_operations_structure(self):
        """Test that the function returns the expected data structure."""
        result = time_of_day_operations(2025, 2025, finalized_only=False)

        # Verify all expected keys are present
        expected_keys = [
            'takeoff_points',
            'landing_points',
            'mean_earliest_takeoff',
            'mean_latest_landing',
            'total_flight_days'
        ]
        for key in expected_keys:
            self.assertIn(key, result)

        # Verify data types
        self.assertIsInstance(result['takeoff_points'], list)
        self.assertIsInstance(result['landing_points'], list)
        self.assertIsInstance(result['mean_earliest_takeoff'], list)
        self.assertIsInstance(result['mean_latest_landing'], list)
        self.assertIsInstance(result['total_flight_days'], int)

    def test_time_of_day_operations_no_data(self):
        """Test the function works correctly with no flight data."""
        result = time_of_day_operations(2025, 2025, finalized_only=False)

        # With no data, should return empty lists and zero count
        self.assertEqual(result['takeoff_points'], [])
        self.assertEqual(result['landing_points'], [])
        self.assertEqual(result['mean_earliest_takeoff'], [])
        self.assertEqual(result['mean_latest_landing'], [])
        self.assertEqual(result['total_flight_days'], 0)
