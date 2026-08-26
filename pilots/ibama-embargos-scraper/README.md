# ibama-embargos-scraper

**Status:** SCAFFOLD_OK (TIER0)
**Method ID:** 1480
**Fonte:** IBAMA CTF — Consulta Pública de Áreas Embargadas
**Custo:** Zero (endpoint público, sem auth)

## Descrição
Indexa áreas embargadas pelo IBAMA para due diligence ambiental B2B. Focado em construtoras, mineradoras, agroindústrias e instituições financeiras que precisam verificar compliance ambiental de fornecedores e terrenos.

## Uso
```bash
python3 main.py
```

## Output
- `embargos_index.json` — Registros de áreas embargadas com município, UF, área, data, motivo e status.

## Notas Técnicas
- **Endpoint:** https://servicos.ibama.gov.br/ctf/publico/areasembargadas/ConsultaPublicaAreasEmbargadas.php
- **Acesso:** Público, sem autenticação
- **Scraping Ético:** Delay 3-5s entre requests, respeita robots.txt
- **Dados:** Públicos ambientais, LGPD não aplica (não contém PII sensível)
- **Atualização:** Irregular pelo IBAMA; cache local recomendado

## Monetização (Estimativa TIER0)
- **Modelo:** B2B API subscription / pay-per-query
- **Payout:** R$2k-20k/projeto ou R$500-5k/mês SaaS
- **Clientes-Alvo:** Construtoras, mineradoras, agroindústrias, bancos, seguradoras

## Próximos Passos (TIER1)
- Implementar parser real do formulário de consulta por CPF/CNPJ/município
- Adicionar georreferenciamento das áreas embargadas
- Integrar com base CNPJ para enriquecimento automático de fornecedores
- Validar demanda com consultorias ambientais e bancos
