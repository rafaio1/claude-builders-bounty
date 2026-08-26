# BrasilAPI Vehicle Data Premium Wrapper — TIER0 Scaffolding

## Status: SCAFFOLD_OK ✅

MVP funcional que valida demanda e mapeia fontes públicas para API de consulta veicular por placa.

## Demanda Validada

- **Issue:** [BrasilAPI/BrasilAPI#137](https://github.com/BrasilAPI/BrasilAPI/issues/137)
- **Título:** API de consulta de veículos por placa
- **Comentários:** 78 (alta engagement)
- **Labels:** `question`, `feature request`

## Fontes Zero-Capital Mapeadas

| Fonte | Tipo | Notas |
|---|---|---|
| SINESP | API Pública | Consulta nacional, requer captcha em produção |
| DETRANs Estaduais | Scraping | Normalização multi-estado necessária |
| Tabela FIPE | Referência | Preços de mercado, complemento à placa |

## Arquitetura do Wrapper

- **Input:** Placa (ABC1234 ou Mercosul ABC1C23)
- **Output:** JSON normalizado (marca, modelo, ano, cor, UF, situação, valor FIPE)
- **Monetização:** Free (10 req/dia) → Basic (R$29/mês) → Pro (R$149/mês, SLA 99%)

## Riscos

- **Legal:** Dados públicos, mas scraping pode violar ToS. Mitigar com cache + robots.txt.
- **Técnico:** Captcha e bloqueio IP exigem headless browser + proxy rotation em TIER1.
- **Mercado:** Concorrência paga existe (Olho no Carro, Checkauto), mas demanda open-source é clara.

## Próximos Passos (TIER1)

1. Adapter SINESP com bypass captcha (playwright-cli headless)
2. Normalizador multi-DETRAN
3. Cache Redis free-tier (Upstash/KV)
4. Rate limiter por IP/chave API
5. Dashboard de uso básico

## Execução

```bash
cd pilots/brasilapi-vehicle-wrapper
python3 main.py
cat output.json
```

## Metadados

- **Proposal ID:** BRASILAPI-VEHICLE-DATA-WRAPPER
- **Tier:** TIER0
- **Scaffolded At:** Ver output.json
- **Zero-Capital:** Sim (apenas stdlib Python + fontes públicas)
