# procon-brand-monitor

**Status:** SCAFFOLD_OK (TIER0)
**Method ID:** 1482
**Fonte:** Consumidor.gov.br (SENACON/MJSP)
**Custo:** Zero (dados públicos, scraping ético)

## Descrição
Monitora reputação de marcas via estatísticas públicas de reclamações no portal Consumidor.gov.br. Focado em B2B para e-commerce, varejo e serviços financeiros.

## Uso
```bash
python3 main.py
```

## Output
- `brand_monitor_index.json` — Estrutura de monitoramento com métricas disponíveis e compliance.

## Notas Técnicas
- **Portal:** https://www.consumidor.gov.br (acessível, dados abertos)
- **Métricas:** Total reclamações, índice resposta/solução, nota consumidor, ranking setor
- **Monetização:** R$199/mês por marca monitorada (estimativa TIER0)
- **Compliance:** Dados públicos agregados, LGPD não aplica a PJ, uso comercial permitido
- **Ética:** Delay entre requests, respeita robots.txt

## Próximos Passos (TIER1)
- Implementar parser real das páginas de estatísticas por empresa
- Adicionar alertas via webhook para variações significativas
- Integrar com base CNPJ para enriquecimento automático
- Validar demanda com agências de reputação digital
