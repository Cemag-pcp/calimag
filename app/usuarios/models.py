from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UsuarioManager(BaseUserManager):
    """Manager customizado para o modelo Usuario"""
    
    def create_user(self, matricula, nome, password=None, **extra_fields):
        """Cria e salva um usuário comum"""
        if not matricula:
            raise ValueError('O campo matrícula é obrigatório')
        if not nome:
            raise ValueError('O campo nome é obrigatório')
        
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        
        user = self.model(
            matricula=matricula,
            nome=nome,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, matricula, nome, password=None, **extra_fields):
        """Cria e salva um superusuário"""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superusuário deve ter is_staff=True')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superusuário deve ter is_superuser=True')
        
        return self.create_user(matricula, nome, password, **extra_fields)


class Usuario(AbstractBaseUser, PermissionsMixin):
    """Modelo customizado de usuário usando matrícula como identificador"""
    
    matricula = models.CharField(
        'Matrícula',
        max_length=20,
        unique=True,
        help_text='Matrícula do funcionário'
    )
    nome = models.CharField('Nome Completo', max_length=200)
    email = models.EmailField('E-mail', blank=True, null=True)
    
    is_staff = models.BooleanField(
        'Membro da equipe',
        default=False,
        help_text='Define se o usuário pode acessar o admin'
    )
    is_active = models.BooleanField(
        'Ativo',
        default=True,
        help_text='Define se o usuário está ativo no sistema'
    )
    date_joined = models.DateTimeField('Data de Cadastro', default=timezone.now)
    
    objects = UsuarioManager()
    
    USERNAME_FIELD = 'matricula'
    REQUIRED_FIELDS = ['nome']
    
    class Meta:
        verbose_name = 'Usuário'
        verbose_name_plural = 'Usuários'
        ordering = ['matricula']
    
    def __str__(self):
        return f"{self.matricula} - {self.nome}"
    
    def get_full_name(self):
        return self.nome
    
    def get_short_name(self):
        return self.nome.split()[0] if self.nome else self.matricula
