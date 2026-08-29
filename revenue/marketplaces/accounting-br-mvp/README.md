# ContábilHub — MVP Landing Page

## Deploy Gratuito (GitHub Pages)

1. Crie repo no GitHub: `contabilhub-marketplace`
2. Copie esta pasta (`revenue/marketplaces/accounting-br-mvp/`) para a raiz do repo
3. Settings → Pages → Source: `main` branch, folder `/ (root)`
4. Acesse em `https://rafaio1.github.io/contabilhub-marketplace/`

## Deploy Alternativo (Vercel Free Tier)

```bash
npm i -g vercel
cd revenue/marketplaces/accounting-br-mvp
vercel --prod
```

## Estrutura de Arquivos

- `index.html` — Landing page estática completa (vanilla HTML/CSS, zero build)
- `tools_template.json` — Schema para cadastro de novas ferramentas
- `README.md` — Este arquivo

## Próximos Passos Pós-Deploy

1. Validar integração Domínio/Contmatic sandbox via API
2. Configurar Asaas split commission para cada tool listada
3. Substituir placeholders por ferramentas reais verificadas
4. Adicionar formulário de contato/listagem funcional
5. SEO: submeter sitemap ao Google Search Console

## Conformidade

- CFC Resolução 1594/2020 (curadoria de ferramentas contábeis)
- LGPD Lei 13.709/2018 (dados pessoais e consentimento)
- Termos de uso isentam responsabilidade sobre ferramentas terceiras
