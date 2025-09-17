#!/usr/bin/env python3

import os
import sys
import django
from datetime import date, time, timedelta
import random

# Setup Django
sys.path.append('/home/runner/work/Manage2Soar/Manage2Soar')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manage2soar.settings')
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-for-development'
os.environ['DJANGO_DEBUG'] = 'True'

django.setup()

from logsheet.models import Glider, Towplane, Airfield, Logsheet, Flight
from members.models import Member

def create_test_data():
    print("Creating test data...")
    
    # Create a test airfield
    airfield, created = Airfield.objects.get_or_create(
        identifier="KTES",
        defaults={'name': "Test Airport"}
    )
    
    # Create a test glider
    glider, created = Glider.objects.get_or_create(
        n_number="N123TEST",
        defaults={
            'make': 'Schleicher',
            'model': 'ASK-21',
            'competition_number': 'TG',
            'is_active': True,
            'club_owned': True
        }
    )
    
    # Create a test towplane 
    towplane, created = Towplane.objects.get_or_create(
        n_number="N456TOW",
        defaults={
            'name': 'Test Towplane',
            'is_active': True,
            'club_owned': True
        }
    )
    
    # Create a test member
    member, created = Member.objects.get_or_create(
        username="testpilot",
        defaults={
            'first_name': 'Test',
            'last_name': 'Pilot',
            'email': 'test@example.com',
            'membership_status': 'Full Member'
        }
    )
    
    # Create test flights for the year 2024 with varied times throughout the year
    start_date = date(2024, 1, 1)
    
    for day_offset in range(0, 365, 7):  # Every 7 days
        log_date = start_date + timedelta(days=day_offset)
        
        # Create a logsheet for this date
        logsheet, created = Logsheet.objects.get_or_create(
            log_date=log_date,
            airfield=airfield,
            defaults={
                'created_by': member,
                'finalized': True
            }
        )
        
        # Calculate seasonal time variations
        # Earlier takeoffs and later landings in summer
        month = log_date.month
        
        if month in [12, 1, 2]:  # Winter
            earliest_takeoff = time(9, 0)  # 9:00 AM
            latest_landing = time(16, 30)  # 4:30 PM
        elif month in [3, 4, 5]:  # Spring
            earliest_takeoff = time(8, 30)  # 8:30 AM
            latest_landing = time(18, 0)   # 6:00 PM
        elif month in [6, 7, 8]:  # Summer
            earliest_takeoff = time(8, 0)  # 8:00 AM
            latest_landing = time(19, 30)  # 7:30 PM
        else:  # Fall
            earliest_takeoff = time(8, 30)  # 8:30 AM
            latest_landing = time(17, 30)  # 5:30 PM
        
        # Add some random variation
        takeoff_minutes = earliest_takeoff.hour * 60 + earliest_takeoff.minute
        takeoff_minutes += random.randint(-30, 60)  # +/- 30 min to + 1 hour
        takeoff_hour = takeoff_minutes // 60
        takeoff_min = takeoff_minutes % 60
        
        landing_minutes = latest_landing.hour * 60 + latest_landing.minute  
        landing_minutes += random.randint(-60, 30)  # -1 hour to +30 min
        landing_hour = landing_minutes // 60
        landing_min = landing_minutes % 60
        
        # Ensure times are within reasonable bounds
        takeoff_hour = max(7, min(12, takeoff_hour))
        landing_hour = max(15, min(20, landing_hour))
        
        # Create a few flights for this day
        for i in range(random.randint(1, 5)):
            flight_takeoff = time(takeoff_hour, takeoff_min)
            flight_landing = time(landing_hour, landing_min)
            
            Flight.objects.get_or_create(
                logsheet=logsheet,
                launch_time=flight_takeoff,
                landing_time=flight_landing,
                defaults={
                    'pilot': member,
                    'glider': glider,
                    'tow_pilot': member,
                    'towplane': towplane,
                    'flight_type': 'Solo',
                    'release_altitude': 2000,
                    'duration': timedelta(hours=1)
                }
            )
            
            # Vary times for additional flights
            takeoff_minutes += random.randint(30, 120)
            takeoff_hour = takeoff_minutes // 60
            takeoff_min = takeoff_minutes % 60
            
            landing_minutes -= random.randint(30, 60)
            landing_hour = landing_minutes // 60
            landing_min = landing_minutes % 60
    
    print(f"Created test data with flights from {start_date} to {start_date + timedelta(days=364)}")
    print(f"Total flights: {Flight.objects.count()}")
    
if __name__ == "__main__":
    create_test_data()