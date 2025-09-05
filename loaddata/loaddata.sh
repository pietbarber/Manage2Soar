#!/bin/bash

./manage.py loaddata loaddata/instructors.ClubQualificationType.json
./manage.py loaddata loaddata/instructors.SyllabusDocument.json
./manage.py loaddata loaddata/instructors.TrainingLesson.json
tar xvfz loaddata/icons.tar.gz 
