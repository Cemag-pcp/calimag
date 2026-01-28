# Diagrama de Relacionamento dos Models

## Estrutura de Dados - Sistema de Calibração

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        ESTRUTURA DO SISTEMA                               │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────────┐
│   Funcionário    │
├──────────────────┤
│ • matricula (PK) │──────┐
│ • nome           │      │
│ • email          │      │ Responsável
│ • cargo          │      │
│ • setor          │      │
│ • telefone       │      │
│ • ativo          │      │
└──────────────────┘      │
                          │
                          ↓
                   ┌──────────────────┐
                   │   Instrumento    │
                   ├──────────────────┤
                   │ • codigo (PK)    │
                   │ • descricao      │
                   │ • tipo           │
                   │ • fabricante     │
                   │ • modelo         │
                   │ • localizacao    │
                   │ • setor          │
                   │ • periodicidade  │
                   │ • status         │
                   └──────────────────┘
                          │
                          │ 1:N (Obrigatório ≥1)
                          │
                          ↓
                   ┌──────────────────┐
                   │ PontoCalibracao  │
                   ├──────────────────┤
                   │ • sequencia      │
                   │ • descricao      │
                   │ • valor_nominal  │
                   │ • unidade        │
                   │ • tolerancia_+   │
                   │ • tolerancia_-   │
                   │ • observacoes    │
                   └──────────────────┘
                          │
                          │ N:1 (Obrigatório)
                          │
                          ↓
┌──────────────────┐      │
│     Padrão       │◄─────┘
├──────────────────┤
│ • codigo (PK)    │
│ • descricao      │
│ • fabricante     │
│ • modelo         │
│ • faixa_medicao  │
│ • resolucao      │
│ • incerteza      │
│ • certificado    │
│ • data_calibracao│
│ • data_validade  │
│ • ativo          │
└──────────────────┘

                   ┌──────────────────┐
                   │ PontoCalibracao  │
                   └──────────────────┘
                          │
                          │ 1:N
                          │
                          ↓
                   ┌──────────────────────┐
                   │ HistoricoCalibracao  │
                   ├──────────────────────┤
                   │ • data_calibracao    │
                   │ • valor_medido       │
                   │ • desvio (calc auto) │
                   │ • incerteza          │
                   │ • status             │
                   │ • executado_por (FK) │
                   │ • certificado        │
                   │ • observacoes        │
                   └──────────────────────┘


═══════════════════════════════════════════════════════════════════════════
                            REGRAS DE NEGÓCIO
═══════════════════════════════════════════════════════════════════════════

1. ✅ OBRIGATÓRIO: Todo Instrumento DEVE ter pelo menos 1 Ponto de Calibração
   
2. ✅ OBRIGATÓRIO: Todo Ponto de Calibração DEVE ter um Padrão associado

3. ✅ VALIDAÇÃO: O Padrão deve estar ATIVO

4. ✅ VALIDAÇÃO: O Padrão deve ter calibração VÁLIDA (não vencida)

5. ✅ AUTOMÁTICO: Desvio é calculado automaticamente (valor_medido - valor_nominal)

6. ✅ ALERTAS: Sistema alerta quando padrão está próximo do vencimento (≤30 dias)

7. ✅ UNIQUE: Cada instrumento não pode ter pontos duplicados na mesma sequência


═══════════════════════════════════════════════════════════════════════════
                           FLUXO DE CADASTRO
═══════════════════════════════════════════════════════════════════════════

PASSO 1: Cadastrar PADRÕES
└─ Certificado de calibração válido

PASSO 2: Cadastrar FUNCIONÁRIOS
└─ Responsáveis e executantes

PASSO 3: Cadastrar INSTRUMENTO
├─ Dados básicos do instrumento
└─ Atribuir responsável

PASSO 4: Cadastrar PONTOS DE CALIBRAÇÃO (Obrigatório!)
├─ Definir pontos a serem calibrados
├─ Atribuir padrão para cada ponto
└─ Definir tolerâncias

PASSO 5: Executar CALIBRAÇÕES
├─ Registrar valores medidos
├─ Sistema calcula desvios
└─ Definir status (aprovado/reprovado/condicional)


═══════════════════════════════════════════════════════════════════════════
                           EXEMPLO PRÁTICO
═══════════════════════════════════════════════════════════════════════════

INSTRUMENTO: Paquímetro Digital 150mm (Código: PAQ-001)
│
├─ PONTO 1: 50mm
│  └─ Padrão: Bloco Padrão 50mm (Cert: BP-2025-001)
│  └─ Tolerância: ±0.02mm
│
├─ PONTO 2: 100mm
│  └─ Padrão: Bloco Padrão 100mm (Cert: BP-2025-002)
│  └─ Tolerância: ±0.02mm
│
└─ PONTO 3: 150mm
   └─ Padrão: Bloco Padrão 150mm (Cert: BP-2025-003)
   └─ Tolerância: ±0.03mm


CALIBRAÇÃO REALIZADA:
├─ Ponto 50mm: Medido 50.01mm → Desvio: +0.01mm → APROVADO ✓
├─ Ponto 100mm: Medido 100.00mm → Desvio: 0.00mm → APROVADO ✓
└─ Ponto 150mm: Medido 150.04mm → Desvio: +0.04mm → REPROVADO ✗
                                                    (Fora da tolerância)
```
