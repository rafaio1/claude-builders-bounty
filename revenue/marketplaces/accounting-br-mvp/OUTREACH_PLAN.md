# ContábilHub — Outreach & Revenue Activation Plan

## Target: 10 Verified Micro-SaaS Devs (Week 1)

### Ideal Partner Profile
- **Product:** Micro-SaaS para contadores (NF-e, SPED, eSocial, honorários, LGPD)
- **Integração:** Domínio Sistemas OU Contmatic (API ativa ou plugin oficial)
- **Compliance:** CRC ativo do responsável técnico + LGPD básico
- **Preço:** R$ 80–400/mês (ticket ideal para comissão de 15%)
- **Estágio:** MVP funcional com ≥3 clientes pagantes

### Canais de Prospecção (Zero Custo)
1. **LinkedIn Search:** `"domínio sistemas" AND ("api" OR "integração") AND "contabilidade"` → filtrar por desenvolvedores/fundadores
2. **Grupos Facebook:** "Contadores Brasil", "Desenvolvedores Domínio Sistemas", "Contmatic Developers"
3. **GitHub/GitLab:** Buscar repos com `dominio-sistemas`, `contmatic-api`, `sped-contabil`
4. **Marketplaces existentes:** Listar ferramentas no Portal Contábil, Contabilizei parceiros, e fazer outreach direto aos devs listados

### Template de Mensagem (PT-BR)
```
Assunto: Convite — Liste sua ferramenta no ContábilHub (0 custo fixo)

Olá [Nome],

Vi que você desenvolveu o [Ferramenta] com integração ao [Domínio/Contmatic]. 
Estamos lançando o ContábilHub, um marketplace curado exclusivamente para 
micro-SaaS contábeis verificados pelo CRC/CFC.

Modelo transparente:
• 15% comissão sobre assinaturas recorrentes (split automático via Asaas/Pix)
• Sem mensalidade, sem custo de listagem, sem exclusividade
• Verificação CRC + selo de conformidade CFC 1594/2020 incluso

Seu produto se encaixa perfeitamente no perfil. Posso enviar o kit de 
integração e iniciar a verificação hoje?

Abraço,
Equipe ContábilHub
https://rafaio1.github.io/contabilhub/
```

### Pipeline de Conversão
| Etapa | Ação | Prazo | Responsável |
|-------|------|-------|-------------|
| 1 | Identificar 30 leads qualificados | Dia 1-2 | Sub-agente Claude |
| 2 | Enviar mensagem personalizada | Dia 2-3 | Manual (humano) |
| 3 | Receber formulário preenchido | Dia 3-7 | Automático (modal) |
| 4 | Verificar integração sandbox | Dia 7-10 | Sub-agente Claude |
| 5 | Configurar split Asaas | Dia 10-12 | Humano (CNPJ necessário) |
| 6 | Publicar ferramenta + anunciar | Dia 12-14 | Sub-agente Claude |

### Métricas de Sucesso (Mês 1)
- [ ] 10 ferramentas listadas e verificadas
- [ ] 3 splits Asaas configurados e testados
- [ ] ≥ R$ 500 em receita bruta processada
- [ ] ≥ R$ 75 em comissão líquida recebida

### Bloqueios Críticos
⚠️ **Asaas Split exige CNPJ + conta bancária PJ** — sem isso, não há pagamento real.
→ Ação imediata: Verificar se há MEI/CNPJ disponível ou pivotar para modelo manual (Pix direto + nota fiscal avulsa) nos primeiros 3 parceiros.

⚠️ **Verificação CRC requer consulta pública** — automatizar via scraping do site do CFC/CRC regional.
→ Tarefa para sub-agente: Criar script Python que valida número CRC contra API pública.
