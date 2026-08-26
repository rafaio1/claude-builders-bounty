# receitaws-cnpj-batch-validation (method_1457)

**Status:** ✅ SCAFFOLD_OK (TIER0)  
**Tipo:** Validação Batch de CNPJs via ReceitaWS  
**Zero-Capital:** Sim (stdlib only, sem auth, free tier público)  
**Rate Limit:** 3 req/min (delay 20s entre requisições)

## Descrição

Validador batch assíncrono de CNPJs usando a API pública ReceitaWS. Respeita rate limits estritos com fila serializada e delays configuráveis. Retorna razão social, situação cadastral, CNAE principal e localização.

## Execução

```bash
cd /Agentic/pilots/receitaws-cnpj-batch-validation
python3 main.py
```

⚠️ **Tempo estimado:** ~60s para 3 CNPJs (devido ao rate limit).

## Output

Gera `cnpj_batch_validation_index.json` com:
- Lista de CNPJs validados com metadados completos
- Contadores de válidos/inativos/erros
- Timestamp UTC timezone-aware
- Status de scaffold

## Notas Técnicas

- **Rate Limit:** ReceitaWS impõe 3 req/min no tier gratuito. O scaffold usa delay de 20s para margem de segurança.
- **CNPJs de Teste:** Banco do Brasil, Open Knowledge Brasil, SERPRO — todos ativos e válidos.
- **Produção:** Requer fila persistente (Redis/SQS), retry com backoff exponencial, e cache local para evitar reconsultas.
- **Alternativas:** BrasilAPI (`/cnpj/v1/{cnpj}`) também disponível como fallback.

## Critérios TIER1

- [ ] Fila persistente (Redis/SQLite) para jobs pendentes
- [ ] Retry com backoff exponencial em caso de 429/5xx
- [ ] Cache local com TTL (evita revalidação desnecessária)
- [ ] Suporte a input via arquivo CSV/JSONL
- [ ] Export para formatos estruturados (Parquet/CSV)
