from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages


def login_view(request):
    """View de login usando matrícula e senha"""
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
        else:
            messages.error(request, 'Matrícula ou senha inválidos.')
    
    return render(request, 'usuarios/login.html')


@login_required
def logout_view(request):
    """View de logout"""
    logout(request)
    messages.success(request, 'Você saiu do sistema.')
    return redirect('login')


@login_required
def home(request):
    """View da página inicial"""
    return render(request, 'usuarios/home.html')


@login_required
def entregas(request):
    """View da tela de entregas"""
    return render(request, 'usuarios/entregas.html')
