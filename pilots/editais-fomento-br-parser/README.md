# editais-fomento-br-parser (method_746)

**Status:** ✅ SCAFFOLD_OK (TIER0)  
**Tipo:** Parser de Editais de Fomento à Pesquisa e Inovação  
**Fontes:** FAPESP, FINEP, CNPq  
**Zero-Capital:** Sim (stdlib only, sem auth, sem custo)

## Descrição

Indexador de oportunidades de fomento público brasileiro. Extrai títulos e URLs de chamadas públicas, editais e bolsas diretamente dos portais oficiais.

## Execução

```bash
cd /Agentic/pilots/editais-fomento-br-parser
python3 main.py
```

## Output

Gera `editais_fomento_index.json` com:
- Lista de editais/oportunidades ativas
- Fonte institucional (FAPESP/FINEP/CNPq)
- Status de parse (parsed/metadata_only/empty)
- Timestamp UTC timezone-aware

## Notas Técnicas

- **CNPq:** Endpoint `/assuntos/editais` retornou 404 no scaffold. Fallback para metadata_only. URL correta pode variar; produção deve validar via portal gov.br/cnpq.
- **FAPESP:** Parser funcional. Links normalizados automaticamente.
- **FINEP:** Página de oportunidades acessível. Parser extrai links relevantes.
- **Rate Limit:** Respeita limites naturais (sem concorrência). UA identificável.
- **Produção:** Requer cache, rotação de UA se necessário, e validação periódica de URLs.

## Critérios TIER1

- [ ] Correção da URL CNPq
- [ ] Extração de datas de inscrição e valores de bolsa
- [ ] Deduplicação cross-fonte
- [ ] Cache local com TTL
- [ ] Validação de links ativos (HTTP HEAD)
