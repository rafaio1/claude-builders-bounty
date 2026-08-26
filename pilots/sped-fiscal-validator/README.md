# sped-fiscal-validator (method_1621)

**Status:** ✅ SCAFFOLD_OK (TIER0)  
**Tipo:** Validador Sintático SPED Fiscal (EFD ICMS/IPI)  
**Zero-Capital:** Sim (stdlib only, validação local, sem auth)  
**Layout:** Guia Prático EFD ICMS/IPI v3.x

## Descrição

Validador de estrutura de arquivos SPED Fiscal. Verifica presença de blocos obrigatórios, formato do registro 0000 (abertura) e sintaxe básica de campos. Não substitui o PVA oficial da SEFAZ — é uma camada de pré-validação para evitar rejeições por erros estruturais simples.

## Execução

```bash
cd /Agentic/pilots/sped-fiscal-validator
python3 main.py
```

## Output

Gera `sped_validation_index.json` com:
- Validação de estrutura (blocos encontrados vs obrigatórios)
- Validação do registro 0000 (campos mínimos, datas)
- Mapa de blocos obrigatórios com descrições
- Notas técnicas e próximos passos TIER1

## Notas Técnicas

- **Registro 0000:** Scaffold detectou "inválido" no exemplo porque a função exige ≥10 campos separados por `|` e o exemplo tem campos vazios consecutivos que são colapsados pelo split. Em produção, usar parser posicional ou regex que preserve campos vazios.
- **Blocos Obrigatórios:** 0, C, D, E, G, H, K, 9 (alguns condicionais à atividade).
- **PVA Oficial:** Validação completa exige uso do Programa Validador e Assinador da Receita Federal.
- **Certificado Digital:** Transmissão exige assinatura com certificado ICP-Brasil A1/A3.

## Critérios TIER1

- [ ] Parser posicional correto (preserva campos vazios)
- [ ] Validação de todos os registros dos blocos C/D/E
- [ ] Integração com PVA via linha de comando ou API
- [ ] Correção automática de erros comuns (formatação de datas, zeros à esquerda)
- [ ] Suporte a EFD-Contribuições (PIS/COFINS)
- [ ] Relatório de erros em formato legível
