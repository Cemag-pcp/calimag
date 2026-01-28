from django.test import TestCase
from .models import Usuario


class UsuarioModelTest(TestCase):
    def test_create_user(self):
        """Testa a criação de um usuário comum"""
        user = Usuario.objects.create_user(
            matricula='12345',
            nome='João Silva',
            password='senha123'
        )
        self.assertEqual(user.matricula, '12345')
        self.assertEqual(user.nome, 'João Silva')
        self.assertTrue(user.check_password('senha123'))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
    
    def test_create_superuser(self):
        """Testa a criação de um superusuário"""
        user = Usuario.objects.create_superuser(
            matricula='99999',
            nome='Admin',
            password='admin123'
        )
        self.assertEqual(user.matricula, '99999')
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
