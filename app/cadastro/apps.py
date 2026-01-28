from django.apps import AppConfig


class CadastroConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.cadastro'
    verbose_name = 'Cadastro'
    
    def ready(self):
        import app.cadastro.signals  # noqa
