# edtech-privado-br-indexer

**Status:** SCAFFOLD_OK (TIER0)
**Method ID:** 745
**Fonte:** INEP Censo Superior + ReceitaWS (Cruzamento de Dados Públicos)
**Custo:** Zero (dados abertos federais, sem auth)

## Descrição
Dataset de instituições de ensino privado BR para prospecção B2B EdTech. Cruza dados do Censo da Educação Superior (INEP) com situação cadastral CNPJ (ReceitaWS) para gerar leads qualificados.

## Uso
```bash
python3 main.py
```

## Output
- `edtech_privado_index.json` — Registros de IES privadas com CNPJ, município, categoria e campos de enriquecimento.

## Notas Técnicas
- **INEP Catálogo XML:** Endpoint `dados.inep.gov.br/dados/catalogo.xml` retornou erro no scaffold; usar download direto dos microdados CSV em produção.
- **ReceitaWS:** API gratuita com rate limit de 3 req/min; batch processing com delay obrigatório.
- **Dados:** Públicos educacionais e fiscais de PJ; LGPD não aplica.
- **Atualização:** Anual (censo) + tempo real (status CNPJ).

## Monetização (Estimativa TIER0)
- **Modelo:** Data Product licenciado ou API pay-per-query
- **Payout:** R$2k-10k/mês por cliente
- **Clientes-Alvo:** Vendors LMS, editoras educacionais, consultorias MEC, fintechs estudantis

## Próximos Passos (TIER1)
- Implementar parser real dos microdados CSV do INEP
- Adicionar integração batch com ReceitaWS para enriquecimento
- Filtrar por cursos ativos e modalidade EAD
- Validar demanda com vendors EdTech nacionais
