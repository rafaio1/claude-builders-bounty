# Acordo de Split Manual via Pix — ContábilHub (Fase Beta)

**Versão:** 1.0  
**Data:** 2026-08-30  
**Status:** Ativo para parceiros beta

## 1. Objetivo
Este documento estabelece o fluxo operacional para repasse de comissões aos desenvolvedores parceiros do ContábilHub durante a fase beta, antes da integração automática com Asaas.

## 2. Modelo de Comissão
- **Percentual:** 15% sobre o valor líquido de cada assinatura recorrente gerada através do marketplace.
- **Base de Cálculo:** Valor pago pelo cliente final, descontados impostos diretos e taxas de gateway (se houver).
- **Recorrência:** A comissão é devida mensalmente enquanto a assinatura estiver ativa.

## 3. Fluxo de Pagamento Manual

### Passo 1: Cobrança ao Cliente
O desenvolvedor parceiro emite boleto, link de pagamento ou Pix diretamente ao cliente final, mantendo o controle total da cobrança.

### Passo 2: Apuração Mensal
No dia 5 de cada mês, o parceiro envia ao time ContábilHub um relatório simples contendo:
- Nome/Razão Social do cliente
- Valor da assinatura no mês anterior
- Data de pagamento

### Passo 3: Repasse via Pix
Após validação (até 48h), o parceiro realiza o Pix de 15% do valor apurado para a chave abaixo:

```
Chave Pix (EVP): [INSERIR_CHAVE_EVP_WISE]
Nome: ContábilHub Admin
Banco: Wise Brasil
```

### Passo 4: Comprovante
Enviar comprovante do Pix para `parcerias@contabilhub.dev` ou responder à issue de onboarding com o anexo.

## 4. Transparência e Auditoria
- O ContábilHub pode solicitar acesso somente-leitura ao sistema de cobranças do parceiro para validação.
- Em caso de divergência, ambas as partes têm 7 dias para conciliação.

## 5. Transição para Split Automático
Assim que o ContábilHub obtiver CNPJ e integração Asaas, todos os parceiros serão migrados para split automático sem alteração de percentual. Este acordo será substituído por termo digital na plataforma.

## 6. Rescisão
Qualquer parte pode encerrar este acordo com aviso prévio de 30 dias. Comissões pendentes serão liquidadas no ciclo seguinte.

---

**Aceite:** Ao listar sua ferramenta no ContábilHub e realizar o primeiro repasse, o parceiro declara concordância com estes termos.
