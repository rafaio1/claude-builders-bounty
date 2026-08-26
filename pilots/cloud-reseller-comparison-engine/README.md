# cloud-reseller-comparison-engine (method_1622)

**Status:** ✅ SCAFFOLD_OK (TIER0)  
**Tipo:** Comparativo Multi-Provider de Revenda Cloud BR  
**Zero-Capital:** Sim (stdlib only, dados públicos, sem auth)  
**Providers:** Locaweb, AWS, Azure, Google Cloud, Huawei Cloud

## Descrição

Engine de comparação estruturada entre programas de revenda cloud relevantes para o mercado brasileiro. Normaliza margens, modelos de billing, disponibilidade de API/sandbox e produtos revendáveis. Base para consultoria B2B ou ferramenta de seleção automatizada.

## Execução

```bash
cd /Agentic/pilots/cloud-reseller-comparison-engine
python3 main.py
```

## Output

Gera `reseller_comparison_index.json` com:
- 5 providers analisados com metadados completos
- Matriz comparativa (API, sandbox, billing BRL, margem máxima)
- Notas técnicas sobre variabilidade de margens e currency conversion
- Próximos passos TIER1

## Notas Técnicas

- **Margens:** Estimativas baseadas em documentação pública; valores reais dependem de tier, volume e negociação.
- **Billing BRL Nativo:** Locaweb, Azure CSP e Huawei Cloud oferecem faturamento direto em BRL.
- **Sandbox:** AWS, Azure e GCP oferecem ambientes de teste gratuitos para validação técnica.
- **Produção:** Requer integração com APIs de billing/provisionamento e atualização periódica de preços.

## Critérios TIER1

- [ ] Scraping/atualização automática de preços via APIs oficiais
- [ ] Calculadora de TCO (Total Cost of Ownership) multi-provider
- [ ] Webhook de alterações de preço/margem
- [ ] Geração de relatórios PDF/HTML para prospects
- [ ] Inclusão de provedores regionais (Hostinger BR, KingHost, UOL Cloud)
- [ ] Conversão USD↔BRL via PTAX do dia
