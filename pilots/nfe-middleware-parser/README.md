# nfe-middleware-parser (method_1620)

**Status:** ✅ SCAFFOLD_OK (TIER0)  
**Tipo:** Parser de Metadados NF-e / Middleware SEFAZ  
**Zero-Capital:** Sim (stdlib only, sem auth para discovery)  
**Auth Produção:** Certificado Digital A1/A3 obrigatório

## Descrição

Scaffolding para middleware de Nota Fiscal Eletrônica. Valida estrutura do Portal Nacional NF-e, mapeia serviços públicos (consulta, manifestação, download) e documenta endpoints WSDL. O portal principal retornou redirect loop no scaffold (comportamento esperado para bots sem cookie/session), mas os endpoints de serviço são válidos e documentados.

## Execução

```bash
cd /Agentic/pilots/nfe-middleware-parser
python3 main.py
```

## Output

Gera `nfe_portal_index.json` com:
- 4 serviços mapeados (Consulta, Manifestação, Download, Status)
- Links extraídos do portal (ou metadata_only se bloqueado)
- Notas técnicas sobre auth e ambiente de homologação
- Timestamp UTC timezone-aware

## Notas Técnicas

- **Redirect Loop:** Portal nacional usa cookies de sessão e proteção anti-bot. Scaffold valida estrutura via metadata; produção exige browser headless com cookie jar ou biblioteca de assinatura XML.
- **WSDL Público:** Endpoint de homologação `hom.nfe.fazenda.gov.br` acessível sem cert para verificação de schema.
- **Certificado Digital:** Operações reais (emitir, consultar chave, manifestar) exigem certificado ICP-Brasil A1 ou A3.
- **Rate Limit SEFAZ:** Variável por UF. Middleware deve implementar fila com backoff e controle de concorrência.

## Critérios TIER1

- [ ] Implementar assinatura XML (lxml + signxml)
- [ ] Integração com certificado digital (PFX/PEM)
- [ ] Fila assíncrona para processamento de notas
- [ ] Parser de XML de retorno (autorização/rejeição)
- [ ] Suporte a múltiplas UFs (tabelas de endpoint por estado)
- [ ] Validação de schema XSD antes do envio
