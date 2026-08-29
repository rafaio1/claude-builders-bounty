# Revenue Control Plane v2 — handoff operacional

Host exclusivo de execução: `179.198.117.31`. Repositório: `/Agentic`. Remoto: `rafaio1/agentic-integration` (privado).

## Estado confirmado em 2026-08-28

- Commit implantado e enviado: `a1adc8d1` (`feat: enforce evidence-gated revenue workflow`).
- Revisão independente: nenhum P0/P1 restante.
- Suíte: `87 passed` para revenue, quarentena, reconciler e budget governor.
- `agentic-revenue-control-plane-v2.service`: habilitado, ativo e sem reinícios.
- `agentic-codex-role-supervisor.service`: habilitado, ativo e carregando o predicado canônico.
- Banco canônico: `/Agentic/data/aro/revenue_control_plane_v2.db`.
- Backup anterior ao cutover: `/Agentic/data/aro/backups/revenue_control_plane_v2-pre-a1adc8d1.db` (modo 0600, integrity check ok).
- `agentic-revenue-reconciler.service`: inativo e desabilitado.
- `bounty-hunter.timer` e `bounty-hunter.service`: inativos; o timer legado está desabilitado.
- O operador de segurança válido é `bughunter-loop.service`, separado do Revenue v2.
- Receita realizada confirmada: `USD 0`.
- Work orders/settlements canônicos atuais: `0/0`.

## Fonte única e significado dos estados

SQLite v2 é a única fonte financeira. JSONL, emails, Telegram, issues, PRs, labels, comentários, dashboards, valores nominais, estimativas e arquivos dos scanners legados nunca habilitam receita ou orçamento.

Uma build segue, no máximo um checkpoint por ciclo:

1. `claim_confirmed`: issue oficial aberta e atribuída a `rafaio1`.
2. `tests_passed`: GitHub Actions oficial concluído com sucesso para o SHA exato.
3. `pr_published`: PR aberto, não draft, do SHA testado e ligado à issue.
4. `review_approved`: review externo `APPROVED` por `OWNER`, `MEMBER` ou `COLLABORATOR`, diferente de `rafaio1`.
5. `delivery_accepted`: merge feito por terceiro.

Merge conclui a build, mas **não** cria recebível. Depois do merge, a plataforma oficial deve ser revalidada para provar obrigação atual de pagamento.

Receita realizada só existe quando `verify-settlement` confirma pela API Stripe, em modo live:

- transfer `tr_*` atribuído ao work order/reward/payer corretos;
- destino exatamente igual a `STRIPE_DESTINATION_ACCOUNT_ID` configurado;
- payment e balance transactions oficiais encadeados;
- saldo do destino disponível;
- `gross - fee = net`;
- evidência renovada em até 24 horas.

Transferência parcial ou totalmente revertida remove a receita de forma idempotente e reabre a cobrança. Sem credencial/destino Stripe dedicados, o gate falha fechado e o valor permanece zero.

## Papéis

- `revenue_generator`: somente `claim_confirmed` e `tests_passed`.
- `integrator`: revisão interna read-only; pode publicar um PR já testado e registrar somente `pr_published`.
- `reviewer`: identidade derivada exclusivamente do review oficial externo; não é autoaprovação de IA.
- `contador`: observa aprovação/merge externos e verifica settlement; nunca declara pagamento.

Todos usam `revenue_control_plane.py verify-evidence` seguido de `workflow-once --apply`. As APIs legadas `create_settlement` e `confirm_settlement` estão desabilitadas.

## Loop contínuo e orçamento

Quando a fila paga está vazia:

1. descoberta limitada e barata produz somente `lead`;
2. revalidar fonte oficial da plataforma e issue/repo oficial;
3. rejeitar stale/closed/rewarded, competição ativa, payer inativo, payout não suportado, KYC/captcha/gasto e EV insuficiente;
4. promover somente após todos os gates;
5. se não houver trabalho pago válido, no máximo uma tarefa de reputação separada, sem registrar receita.

O budget governor está em `zero_revenue` e impede novo consumo após o teto diário. Em 2026-08-28 o teto já foi excedido por sessões anteriores; os chats permanecem vivos/idle e voltam a ser elegíveis no reset UTC. Não aumente o teto para mascarar ausência de receita.

## Última decisão externa

`sipyourdrink-ltd/bernstein#4673` foi rejeitada sem branch/commit/PR: o método pedido não tem chamador de produção e a mudança sugerida seria código morto, incapaz de satisfazer a aceitação. Esse resultado é aprendizado negativo, não falha operacional.

## Próximo passo

Continuar `discover -> validar plataforma/issue -> claim -> implementar/testar -> revisão -> PR -> aprovação/merge externo -> revalidar obrigação -> settlement -> revalidar reversões`. Nunca marcar complete/blocked apenas porque uma rodada retornou `NONE`; aguardar o intervalo configurado e rotacionar. Nunca fabricar uma oportunidade para demonstrar o fluxo.
