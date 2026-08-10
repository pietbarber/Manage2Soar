                try:
                    with transaction.atomic():  # Nested savepoint for save only
                        flight.save()
                except IntegrityError:
                    if client_token and _find_existing_flight_by_client_token(
                        logsheet, client_token
                    ):
                        return _success_response()
                    raise
