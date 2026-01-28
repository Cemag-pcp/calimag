# Calimag - Sistema de Gerenciamento de Calibração

## Tecnologias Utilizadas
- Django 6.0.1
- PostgreSQL
- Tailwind CSS

## Configuração do Ambiente

### 1. Instalar Dependências

```bash
pip install django psycopg2-binary
```

### 2. Configurar o Banco de Dados PostgreSQL

Certifique-se de que o PostgreSQL está instalado e rodando. Crie o banco de dados:

```sql
CREATE DATABASE calimag_db;
```

Edite as credenciais em `calimag/settings.py` se necessário:
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'calimag_db',
        'USER': 'postgres',
        'PASSWORD': 'postgres',  # Altere para sua senha
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

### 3. Executar Migrações

```bash
cd calimag
python manage.py makemigrations
python manage.py migrate
```

### 4. Criar Superusuário

```bash
python manage.py createsuperuser
```

Você será solicitado a fornecer:
- Matrícula
- Nome
- Senha

### 5. Executar o Servidor

```bash
python manage.py runserver
```

Acesse o sistema em: http://localhost:8000

## Estrutura do Projeto

```
calibracao_v2/
├── app/
│   ├── usuarios/          # App de autenticação
│   │   ├── models.py      # Modelo customizado de usuário
│   │   ├── views.py       # Views de login/logout
│   │   ├── urls.py        # URLs de autenticação
│   │   └── templates/     # Templates com Tailwind
│   └── cadastro/          # App de cadastro
│       ├── models.py      # Models de calibração
│       ├── admin.py       # Interface administrativa
│       └── signals.py     # Validações automáticas
├── calimag/
│   ├── settings.py        # Configurações do projeto
│   └── urls.py            # URLs principais
└── manage.py
```

## Funcionalidades Implementadas

### ✅ Sistema de Autenticação
- Login por matrícula e senha
- Modelo de usuário customizado
- Templates responsivos com Tailwind CSS
- Proteção de rotas com @login_required

### ✅ Sistema de Cadastro de Calibração

#### 1. **Funcionários**
- Matrícula (identificador único)
- Nome completo, cargo, setor
- E-mail e telefone
- Data de admissão
- Status (ativo/inativo)

#### 2. **Padrões de Calibração**
- Código único
- Descrição, fabricante, modelo
- Faixa de medição e resolução
- Incerteza de medição
- Certificado de calibração
- Data de calibração e validade
- Status automático de validade

#### 3. **Instrumentos**
- Código único do instrumento
- Tipo (medição, ensaio, processo)
- Especificações técnicas completas
- Localização e responsável
- Periodicidade de calibração
- Status (ativo, inativo, manutenção, descartado)
- **Obrigatório ter pelo menos 1 ponto de calibração**

#### 4. **Pontos de Calibração**
- Múltiplos pontos por instrumento
- Valor nominal e unidade de medida
- Tolerâncias (+/-)
- **Padrão obrigatório** para cada ponto
- Validação automática do padrão (ativo e calibrado)
- Sequenciamento dos pontos

#### 5. **Histórico de Calibrações**
- Registro de todas as calibrações realizadas
- Valores medidos e desvios calculados automaticamente
- Status (aprovado, reprovado, condicional)
- Executante e certificado
- Rastreabilidade completa

### 🔒 Validações Implementadas
- Instrumento **obrigatoriamente** precisa ter ponto de calibração
- Padrão deve estar ativo e com calibração válida
- Cálculo automático de desvios
- Alertas de vencimento de calibração de padrões

### 📋 Campos do Usuário
- **Matrícula** (identificador único)
- **Nome Completo**
- **E-mail** (opcional)
- **Senha**
- **Permissões** (staff, superuser)
- **Status** (ativo/inativo)

## Próximos Passos

1. Desenvolver módulos de cadastro de equipamentos
2. Implementar controle de calibrações
3. Criar sistema de relatórios
4. Adicionar dashboard com indicadores

## Admin

Acesse o painel administrativo em: http://localhost:8000/admin

Use as credenciais do superusuário criado para fazer login.
"# cailmag" 
