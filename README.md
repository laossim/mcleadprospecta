# MCLeadProspecta Web
**Memocash Soluções** · v0.0.0.1 pré-beta · by [@laossim](https://github.com/laossim)

---

## Como colocar no ar (Railway) — passo a passo

### 1. Crie as contas necessárias (grátis)
- **GitHub**: https://github.com — crie uma conta se não tiver
- **Railway**: https://railway.app — entre com sua conta GitHub

---

### 2. Suba o código no GitHub

Abra o terminal (ou Git Bash no Windows) dentro desta pasta e rode:

```bash
git init
git add .
git commit -m "primeiro deploy MCLeadProspecta"
```

Depois vá em https://github.com/new, crie um repositório chamado `mcleadprospecta`, e rode:

```bash
git remote add origin https://github.com/SEU_USUARIO/mcleadprospecta.git
git branch -M main
git push -u origin main
```

---

### 3. Deploy no Railway

1. Entre em https://railway.app
2. Clique em **New Project → Deploy from GitHub Repo**
3. Selecione o repositório `mcleadprospecta`
4. Railway detecta o `Procfile` e instala tudo automaticamente
5. Vá em **Settings → Domains → Generate Domain**
6. Sua URL estará pronta em ~3 minutos ✅

---

### 4. Variáveis de ambiente (opcional mas recomendado)

No Railway, em **Variables**, adicione:

| Variável     | Valor          |
|-------------|----------------|
| SECRET_KEY  | qualquer_senha_segura |

---

### Estrutura do projeto

```
mcleadprospecta-web/
├── app.py              # Backend Flask (rotas, scraping, planilha)
├── templates/
│   └── index.html      # Frontend completo
├── requirements.txt    # Dependências Python
├── Procfile            # Comando de start para Railway/Render
├── nixpacks.toml       # Configuração do ambiente no Railway
└── .gitignore
```

---

### Rodar localmente (para testar antes do deploy)

```bash
# Instalar dependências
pip install -r requirements.txt
playwright install chromium

# Rodar
python app.py
```

Acesse http://localhost:5000

---

### Custo estimado

| Plano          | Custo       | Para quê                     |
|---------------|-------------|------------------------------|
| Railway Hobby  | ~US$5/mês   | Até 10-20 buscas/dia         |
| Railway Pro    | ~US$20/mês  | Uso intenso, múltiplos users |

---

*Desenvolvido por @laossim · Memocash Soluções*
