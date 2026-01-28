from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('cadastro', '0010_tipoinstrumento_documento_qualidade'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='instrumento',
            name='setor',
        ),
    ]
