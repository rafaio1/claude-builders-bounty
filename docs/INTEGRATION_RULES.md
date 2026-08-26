 # Regras Permanentes de Integração e Operação
 
 ## Meta Aspiracional
 - **Objetivo:** 20.000.000 USDT em receita efetivamente liquidada e reconciliada.
 - **Natureza:** Meta contínua e aspiracional. O goal de integração NUNCA deve ser marcado como `complete` apenas por ausência de ação imediata.
 
 ## Estados de Espera e Monitoramento
 - Em casos de delay, CI pendente, resposta de mantenedor, triagem, email, payout, janela de mercado ou dependência externa:
   - Registre estado como `waiting_monitoring`.
   - Documente evidência do bloqueio temporário.
   - Defina prazo para nova verificação (backoff).
   - Liste próxima ação planejada.
 - Use auditorias periódicas para retomar quando houver mudança de estado.
 - Continue buscando trabalho útil dentro do escopo durante períodos de espera.
 
 ## Critério de Bloqueio (`blocked`)
 - Somente para impedimento real repetido (3+ ciclos) que não permita NENHUMA ação útil.
 - Mesmo bloqueado, preserve plano de monitoramento e recuperação.
 - Não use `blocked` por falta de tarefas imediatas se houver backlog ou manutenção possível.
 
 ## Integridade Financeira e Risco
 - **Nunca invente receita.** Potencial ≠ ganho.
 - **Nunca prometa retorno.**
 - **Nunca relaxe controles** de risco, regras de plataforma, autorização, escopo ou qualidade para perseguir a meta.
 - Acompanhe o ciclo completo: descoberta → qualificação → execução → revisão → follow-up → aceite → pagamento → conciliação.
 
 ## Coordenação e Contabilidade
 - Coordene com CONTADOR para registro de receita por processo.
 - Impedir dupla contagem via reconciliação cruzada.
 - Todo commit financeiro deve ter rastro auditável no repositório.
 
 ## Aplicação
 Esta regra é permanente e sobrevive a mudanças de contexto. Deve ser lida por qualquer agente integrador ao iniciar sessão.
