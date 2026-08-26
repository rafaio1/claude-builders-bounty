# Checklist de Pré-Validação TIER0 (Anti-Rejeição)

Baseado na análise dos últimos 100 vereditos ADIAR do Conselho.
**Regra:** Se o método falhar em qualquer item OBRIGATÓRIO, não submeter proposta.

## 1. Filtro Geográfico e Monetização BR (CRÍTICO)
- [ ] **Pricing em BRL?** A fonte oficial possui página de preços em Reais ou gateway de pagamento local (Pix, boleto)?
- [ ] **Parceria/Integração Local?** Existe integração nativa com plataformas BR (Hotmart, Eduzz, Kiwify, Mercado Livre, Shopee, RD Station, Pipedrive BR)?
- [ ] **Demanda Local Comprovada?** Os `notes` citam volume de busca BR, comunidades locais ativas ou casos de uso específicos do mercado brasileiro?
- [ ] **Evitar Proxy Global Genérico:** Se a única fonte é GitHub Search API global sem menção explícita a "Brasil", "BR", "LGPD" ou "BRL", o método será rejeitado.

## 2. Compliance e Regulamentação Local
- [ ] **LGPD Mencionada?** Para métodos que lidam com dados pessoais, CRM, saúde ou educação, a conformidade com a LGPD está explicitada nos `notes`?
- [ ] **Direitos Autorais/Autoral BR?** Para conteúdo (música, vídeo, imagens), há validação de compliance com a lei de direitos autorais brasileira (Lei 9.610/98)?
- [ ] **Regulamentação Setorial?** Educação (MEC), Financeiro (BCB/CVM), Saúde (ANVISA) possuem selo de conformidade local se aplicável?

## 3. Não-Duplicação e Infraestrutura Horizontal
- [ ] **Verificar Métodos Existentes:** O método é redundante com infra horizontal já aprovada/pilotada?
    - Templates/Geral: Method_37
    - Paywall/Membros: Method_25
    - Relatórios B2B: Method_31
    - Stock AI Geral: Method_43 (ADIAR, mas bloqueia nichos similares sem diferencial forte)
    - Documentação/API Docs: Method_325
    - Hotmart/Infra Creator: Method_19
    - Dependabot/Renovate: Method_343
- [ ] **Diferencial Claro:** Se for variação de método existente, o `notes` explica por que este nicho específico JUSTIFICA um novo method_id (ex: regulação diferente, público-alvo incompatível)?

## 4. Modelo de Receita Zero-Capital Real
- [ ] **Sem Custo Inicial:** Confirmação absoluta de que não exige gas fees, signup pago, licença comercial USD obrigatória ou hardware dedicado?
- [ ] **Monetização Direta Validada:** O campo `monetization_model` descreve fluxo de receita real (venda, comissão, adsense local) e não apenas atributos técnicos (`free_tier`, `open_source`, `donationware`)?
- [ ] **Atributos Técnicos ≠ Prova de Mercado:** Campos como `latency_ms`, `format_support`, `bulk_discount=true` sem contexto BR são insuficientes. Devem ser acompanhados de evidência de demanda pagante local.

## 5. Qualidade dos Metadados
- [ ] **Notes Robustos:** Mínimo 3 frases contextualizando viabilidade BR. Evitar notas genéricas como "ferramenta útil para X".
- [ ] **Fonte Oficial Documentada:** URL da plataforma/alvo + parâmetros de busca usados. Se for proxy, justificar por que a fonte primária não foi acessível e como o proxy mitiga risco de falso positivo.
- [ ] **Categoria Correta:** Verificar balanceamento atual antes de submeter. Categorias saturadas (>220) exigem justificativa excepcional.

---
*Gerado automaticamente em 2026-08-26 via análise de padrões de rejeição. Atualizar periodicamente conforme novos vereditos.*
