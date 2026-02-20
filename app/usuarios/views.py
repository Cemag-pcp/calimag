from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages


def _render_pmc_page(request, scope, title, subtitle):
    return render(request, 'usuarios/home.html', {
        'pmc_scope': scope,
        'pmc_title': title,
        'pmc_subtitle': subtitle,
    })


def login_view(request):
    """View de login usando matricula e senha"""
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        matricula = request.POST.get('matricula')
        password = request.POST.get('password')

        user = authenticate(request, username=matricula, password=password)

        if user is not None:
            login(request, user)
            next_url = request.GET.get('next', 'home')
            return redirect(next_url)
        messages.error(request, 'Matricula ou senha invalidos.')

    return render(request, 'usuarios/login.html')


@login_required
def logout_view(request):
    """View de logout"""
    logout(request)
    messages.success(request, 'Voce saiu do sistema.')
    return redirect('login')


@login_required
def home(request):
    """Redireciona para a visao padrao do PMC."""
    return redirect('pmc_instrumentos')


@login_required
def pmc_instrumentos(request):
    """View PMC para instrumentos (exceto gabaritos e maquinas de solda)."""
    return _render_pmc_page(
        request,
        scope='instrumentos',
        title='Plano mestre de calibracao - Instrumentos',
        subtitle='Exibe instrumentos gerais (exclui gabaritos e maquinas de solda).',
    )


@login_required
def pmc_maquinas_solda(request):
    """View PMC para maquinas de solda."""
    return _render_pmc_page(
        request,
        scope='maquinas_solda',
        title='Plano mestre de calibracao - Maquinas de solda',
        subtitle='Exibe apenas maquinas de solda (laser e digital).',
    )


@login_required
def pmc_gabaritos(request):
    """View PMC para gabaritos."""
    return _render_pmc_page(
        request,
        scope='gabaritos',
        title='Plano mestre de calibracao - Gabaritos',
        subtitle='Exibe apenas itens do tipo gabarito.',
    )


@login_required
def entregas(request):
    """View da tela de entregas"""
    return render(request, 'usuarios/entregas.html')
