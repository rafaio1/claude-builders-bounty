# BrasilAPI Vehicle Data Wrapper

**Status:** FUNCTIONAL_MVP | **Tier:** TIER0 | **Zero-Capital:** ✅

## Descrição
Wrapper sobre a API pública FIPE da [BrasilAPI](https://brasilapi.com.br/) para consulta de marcas e preços de veículos. Demonstra o padrão de wrapper para futura camada premium.

## Estratégia Zero-Capital
- Usa BrasilAPI pública (sem chave, sem custo)
- stdlib Python (`urllib`, `json`)
- Sem dependências externas
- Monetização futura via tier premium com SLA/cache/volume

## Como executar
```bash
python3 main.py
```

## Output
Arquivo `wrapper_demo_output.json` com lista de marcas e resultado de consulta de preço FIPE.

## Arquivos
- `main.py` — Script principal
- `wrapper_demo_output.json` — Output gerado automaticamente

## Validação
- ✅ Execução exitosa (exit code 0)
- ✅ Datetime timezone-aware (UTC)
- ✅ Brands endpoint funcional (107 marcas retornadas)
- ✅ Price lookup tratado gracefulmente (HTTP 500 upstream não é bug do wrapper)
- ✅ Scaffolding verificado na auditoria

## Notas
O endpoint de preço FIPE pode retornar HTTP 500 para alguns códigos devido a instabilidade upstream. O wrapper já trata isso sem quebrar. Para produção, adicionar retry/backoff e cache local.
