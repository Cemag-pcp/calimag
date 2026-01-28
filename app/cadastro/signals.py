from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from .models import Instrumento


@receiver(pre_save, sender=Instrumento)
def validar_instrumento_antes_salvar(sender, instance, **kwargs):
    """
    Signal para validar que um instrumento tem pelo menos um ponto de calibração
    antes de ser salvo (apenas em updates, não em criação inicial)
    """
    if instance.pk:  # Só valida em updates
        instance.clean()
