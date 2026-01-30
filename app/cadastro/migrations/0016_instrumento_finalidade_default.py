from django.db import migrations
from django.db.models import Q


def set_default_finalidade(apps, schema_editor):
    Instrumento = apps.get_model('cadastro', 'Instrumento')
    Instrumento.objects.filter(Q(finalidade__isnull=True) | Q(finalidade='')).update(
        finalidade='instrumento de medicao'
    )


def unset_default_finalidade(apps, schema_editor):
    Instrumento = apps.get_model('cadastro', 'Instrumento')
    Instrumento.objects.filter(finalidade='instrumento de medicao').update(finalidade='')


class Migration(migrations.Migration):
    dependencies = [
        ('cadastro', '0015_instrumento_finalidade'),
    ]

    operations = [
        migrations.RunPython(set_default_finalidade, unset_default_finalidade),
    ]
