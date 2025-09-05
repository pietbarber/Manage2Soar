#!/bin/bash

./manage.py loaddata loaddata/members.Badge.json
./manage.py loaddata loaddata/instructors.ClubQualificationType.json
./manage.py loaddata loaddata/instructors.TrainingPhase.json
./manage.py loaddata loaddata/instructors.TrainingLesson.json
./manage.py loaddata loaddata/instructors.SyllabusDocument.json
tar xvfz loaddata/icons.tar.gz 
