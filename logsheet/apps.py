from django.apps import AppConfig


class LogsheetConfig(AppConfig):
    name = 'logsheet'

    def ready(self):
        import logsheet.signals
