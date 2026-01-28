# REGRAS DE NEGÓCIO - Sistema Calimag

## 📋 INSTRUMENTOS

### RN001 - Obrigatoriedade de Pontos de Calibração
**Descrição:** Todo instrumento DEVE ter pelo menos 1 ponto de calibração cadastrado.
**Justificativa:** Não faz sentido ter um instrumento sem definir o que será calibrado nele.
**Validação:** Sistema valida ao tentar salvar instrumento sem pontos.
**Implementação:** Model `Instrumento.clean()` e signals

### RN002 - Código Único de Instrumento
**Descrição:** Cada instrumento deve ter um código único no sistema.
**Justificativa:** Garantir identificação inequívoca dos instrumentos.
**Validação:** Campo `codigo` com `unique=True`

---

## 🎯 PONTOS DE CALIBRAÇÃO

### RN003 - Padrão Obrigatório
**Descrição:** Todo ponto de calibração DEVE ter um padrão associado.
**Justificativa:** É necessário saber qual padrão será usado para calibrar aquele ponto.
**Validação:** Campo obrigatório no model
**Implementação:** `PontoCalibracao.padrao` com `on_delete=PROTECT`

### RN004 - Padrão Deve Estar Ativo
**Descrição:** O padrão associado ao ponto de calibração deve estar ativo.
**Justificativa:** Não se pode usar padrões inativos para calibração.
**Validação:** `PontoCalibracao.clean()` valida se `padrao.ativo = True`

### RN005 - Padrão com Calibração Válida
**Descrição:** O padrão associado deve ter calibração válida (não vencida).
**Justificativa:** Padrões com calibração vencida não garantem rastreabilidade.
**Validação:** `PontoCalibracao.clean()` verifica `padrao.calibracao_vencida`
**Observação:** Sistema emite alerta quando faltam 30 dias para vencer

### RN006 - Sequência Única por Instrumento
**Descrição:** Cada instrumento não pode ter dois pontos com a mesma sequência.
**Justificativa:** Organização lógica dos pontos de calibração.
**Validação:** `unique_together = ['instrumento', 'sequencia']`

### RN007 - Valor Nominal Obrigatório
**Descrição:** Todo ponto deve ter um valor nominal definido.
**Justificativa:** É o valor de referência para a calibração.
**Validação:** Campo obrigatório

### RN008 - Unidade de Medida Obrigatória
**Descrição:** Todo ponto deve ter sua unidade de medida definida.
**Justificativa:** Essencial para interpretação correta das medições.
**Validação:** Campo obrigatório com choices pré-definidas

---

## 📊 PADRÕES

### RN009 - Código Único de Padrão
**Descrição:** Cada padrão deve ter um código único no sistema.
**Justificativa:** Identificação inequívoca dos padrões.
**Validação:** Campo `codigo` com `unique=True`

### RN010 - Proteção de Padrão em Uso
**Descrição:** Padrões que estão associados a pontos de calibração não podem ser excluídos.
**Justificativa:** Manter histórico e rastreabilidade.
**Validação:** `on_delete=PROTECT` no relacionamento

### RN011 - Alerta de Vencimento
**Descrição:** Sistema deve alertar quando faltam 30 dias ou menos para vencimento.
**Justificativa:** Planejamento de recalibração dos padrões.
**Implementação:** Property `dias_para_vencimento` no model

---

## 📝 HISTÓRICO DE CALIBRAÇÃO

### RN012 - Cálculo Automático de Desvio
**Descrição:** Desvio é calculado automaticamente (valor_medido - valor_nominal).
**Justificativa:** Evitar erros de cálculo manual.
**Implementação:** `HistoricoCalibracao.save()` override

### RN013 - Rastreabilidade Completa
**Descrição:** Todo registro de calibração deve ter: data, executante, valores e status.
**Justificativa:** Auditoria e conformidade com normas.
**Validação:** Campos obrigatórios no model

---

## 👥 FUNCIONÁRIOS

### RN014 - Matrícula Única
**Descrição:** Cada funcionário deve ter matrícula única.
**Justificativa:** Identificação correta dos responsáveis.
**Validação:** Campo `matricula` com `unique=True`

---

## 🔐 AUTENTICAÇÃO

### RN015 - Login por Matrícula
**Descrição:** Usuários fazem login usando matrícula e senha (não email).
**Justificativa:** Alinhamento com sistema de RH da empresa.
**Implementação:** `USERNAME_FIELD = 'matricula'` no model Usuario

---

## 🔄 FLUXO DE CADASTRO

### Fluxo 1: Cadastro Completo de Instrumento
1. Cadastrar PADRÕES primeiro (com certificados válidos)
2. Cadastrar FUNCIONÁRIOS (responsáveis)
3. Cadastrar INSTRUMENTO (dados básicos + responsável)
4. Cadastrar PONTOS DE CALIBRAÇÃO (mínimo 1, obrigatório)
   - Definir sequência
   - Definir valor nominal e unidade
   - Associar padrão válido
   - Definir tolerâncias (opcional)

### Fluxo 2: Execução de Calibração
1. Selecionar instrumento
2. Para cada ponto de calibração:
   - Usar o padrão definido
   - Registrar valor medido
   - Sistema calcula desvio automaticamente
   - Definir status (aprovado/reprovado/condicional)
3. Registrar executante e certificado
4. Salvar no histórico

---

## ⚠️ VALIDAÇÕES DE INTERFACE

### VI001 - Feedback Visual de Status
**Descrição:** Sistema deve usar cores para indicar status:
- Verde: Ativo, Aprovado, Válido
- Vermelho: Inativo, Reprovado, Vencido
- Amarelo: Em Manutenção, Condicional, Próximo do vencimento
- Cinza: Descartado, Sem informação

### VI002 - Confirmação de Exclusão
**Descrição:** Todas as exclusões devem ter confirmação via modal.
**Justificativa:** Evitar exclusões acidentais.

### VI003 - Salvar sem Reload
**Descrição:** Operações CRUD não devem recarregar a página inteira.
**Justificativa:** Melhor experiência do usuário.
**Implementação:** AJAX + atualização parcial

---

## 📅 PERIODICIDADE

### RN016 - Periodicidade Padrão
**Descrição:** Periodicidade padrão de calibração é 365 dias (1 ano).
**Justificativa:** Padrão mais comum na indústria.
 **Configuração:** Valor default no campo `periodicidade_calibracao` no modelo `PontoCalibracao` (agora a periodicidade é definida por ponto)

---

## 🔍 BUSCA E FILTROS

### RN017 - Busca Multicampo
**Descrição:** Busca deve procurar em múltiplos campos relevantes.
**Implementação:** Busca em código, descrição, fabricante e modelo
**Justificativa:** Facilitar localização de instrumentos

---

## 📊 RELATÓRIOS (Futuro)

### RN018 - Instrumentos Próximos do Vencimento
**Descrição:** Relatório deve listar instrumentos que precisam calibração nos próximos 30 dias.

### RN019 - Padrões a Recalibrar
**Descrição:** Relatório deve listar padrões que precisam ser recalibrados.

### RN020 - Taxa de Aprovação
**Descrição:** Indicador de % de calibrações aprovadas vs reprovadas.

---

**Última Atualização:** 21/01/2026
**Versão:** 1.0
