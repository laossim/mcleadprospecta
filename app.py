"""
MCLeadProspecta Web — Memocash Soluções
github.com/laossim
"""

import os, re, time, uuid, json, threading, unicodedata
from datetime import date, datetime
from flask import Flask, render_template, request, jsonify, send_file

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "mcleadprospecta-dev")

# ── Jobs em memória ───────────────────────────────────────────────────────────
JOBS      = {}
JOBS_LOCK = threading.Lock()

# ── Caminho do Playwright (definido no nixpacks.toml e Procfile) ──────────────
PLAYWRIGHT_BROWSERS_PATH = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/app/.playwright")

# ──────────────────────────────────────────────────────────────────────────────
# CORREÇÃO DE DIGITAÇÃO
# ──────────────────────────────────────────────────────────────────────────────

def normalizar(t):
    return unicodedata.normalize("NFKD", t).encode("ASCII", "ignore").decode().lower().strip()

CORRECOES = {
    "hamburguer":"hambúrguer","hamb´rguer":"hambúrguer","hamburger":"hambúrguer",
    "hamburgueria":"hamburgueria","hamburgeria":"hamburgueria",
    "pizaria":"pizzaria","pizzeria":"pizzaria",
    "padaraia":"padaria","paderia":"padaria","pandaria":"padaria",
    "farmacia":"farmácia","farrmacia":"farmácia",
    "academia":"academia","acadmia":"academia",
    "mecanica":"mecânica","mecanico":"mecânico",
    "odontologia":"odontologia","odontolgia":"odontologia",
    "advocacia":"advocacia","adovgado":"advogado",
    "contabilidade":"contabilidade","contabilidde":"contabilidade",
    "restaurante":"restaurante","restarante":"restaurante",
    "supermercado":"supermercado","supermecado":"supermercado",
    "barbearia":"barbearia","barberia":"barbearia",
    "estetica":"estética","esthetica":"estética",
    "petshop":"pet shop","pet shopt":"pet shop",
    "consultorio":"consultório","consulotrio":"consultório",
    "clinica":"clínica","clinika":"clínica",
    "sorveteria":"sorveteria","sorvetaria":"sorveteria",
    "lanchonete":"lanchonete","lanchinete":"lanchonete",
    "oficina":"oficina","ofcina":"oficina",
    "eletrica":"elétrica","hidraulica":"hidráulica",
    "imobiliaria":"imobiliária","imobilaria":"imobiliária",
    "hotel":"hotel","hotal":"hotel",
    "pousada":"pousada","pousadda":"pousada",
    "sao paulo":"São Paulo","san paulo":"São Paulo",
    "rio de janerio":"Rio de Janeiro","rio de janiero":"Rio de Janeiro",
    "belo horizonte":"Belo Horizonte","belo orizonte":"Belo Horizonte",
    "curitba":"Curitiba","curtiba":"Curitiba",
    "fortaleza":"Fortaleza","forteleza":"Fortaleza",
    "salvador":"Salvador","salvaldor":"Salvador",
    "manaus":"Manaus","manuas":"Manaus",
    "recife":"Recife","recfie":"Recife",
    "porto alegre":"Porto Alegre","poro alegre":"Porto Alegre",
    "goiania":"Goiânia","goainia":"Goiânia",
    "campos do jordao":"Campos do Jordão",
    "campinas":"Campinas","camppinas":"Campinas",
    "brasilia":"Brasília","brazilia":"Brasília",
    "florianopolis":"Florianópolis","florianpolis":"Florianópolis",
    "vitoria":"Vitória","belem":"Belém","bellem":"Belém",
    "teresina":"Teresina","treresina":"Teresina",
    "natal":"Natal","natel":"Natal",
    "maceio":"Maceió","joao pessoa":"João Pessoa",
    "porto velho":"Porto Velho","boa vista":"Boa Vista",
    "palmas":"Palmas","sao luis":"São Luís","sao luiz":"São Luís",
    "campo grande":"Campo Grande","cuiaba":"Cuiabá",
    "ribeirao preto":"Ribeirão Preto","riberao preto":"Ribeirão Preto",
    "uberlandia":"Uberlândia","sorocaba":"Sorocaba",
    "sao jose dos campos":"São José dos Campos",
    "guarulhos":"Guarulhos","osasco":"Osasco",
    "joinville":"Joinville","londrina":"Londrina",
    "maringa":"Maringá","juiz de fora":"Juiz de Fora",
    "niteroi":"Niterói","duque de caxias":"Duque de Caxias",
    "nova iguacu":"Nova Iguaçu",
}

def corrigir(texto):
    chave = normalizar(texto)
    if chave in CORRECOES:
        return CORRECOES[chave]
    return " ".join(CORRECOES.get(normalizar(t), t) for t in texto.strip().split())

# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def sanitizar(t):
    return re.sub(r"[^\w\s-]", "", t).strip().replace(" ", "_")

def pasta_output():
    p = os.path.join(os.path.dirname(__file__), "outputs")
    os.makedirs(p, exist_ok=True)
    return p

def gerar_whatsapp(tel):
    nums = re.sub(r"\D", "", tel)
    if not nums:
        return ""
    if not nums.startswith("55"):
        nums = "55" + nums
    return f"https://wa.me/{nums}"

PADRAO_TEL = re.compile(r"(?:\+?55\s?)?(?:\(?\d{2}\)?[\s\-]?)(?:9\s?)?\d{4}[\s\-]?\d{4}")

# ──────────────────────────────────────────────────────────────────────────────
# SCRAPING
# ──────────────────────────────────────────────────────────────────────────────

def extrair_detalhes(page, url):
    dados = {"endereco": "", "telefone": "", "whatsapp": ""}
    try:
        page.goto(url, timeout=18000, wait_until="domcontentloaded")
        page.wait_for_timeout(1400)
        botoes = page.locator("button[aria-label]")
        for i in range(botoes.count()):
            try:
                aria = botoes.nth(i).get_attribute("aria-label") or ""
                al   = aria.lower()
                if not dados["endereco"] and any(p in al for p in ("endereço:", "endereco:", "address:")):
                    dados["endereco"] = re.sub(r"^[^:]+:\s*", "", aria).strip()
                if not dados["telefone"] and any(p in al for p in ("telefone:", "phone:", "número de telefone")):
                    tel = re.sub(r"^[^:]+:\s*", "", aria).strip()
                    dados["telefone"] = tel
                    dados["whatsapp"] = gerar_whatsapp(tel)
            except Exception:
                pass
            if dados["endereco"] and dados["telefone"]:
                return dados
        for classe in ("Io6YTe", "rogA2c", "AeaXub"):
            divs = page.locator(f"div.{classe}")
            for i in range(divs.count()):
                try:
                    txt = divs.nth(i).inner_text().strip()
                    if not txt:
                        continue
                    if not dados["endereco"] and re.search(r"\d{4,}", txt) and "," in txt and len(txt) > 10:
                        if not re.search(r"[\+\(\)]{1}.*\d{4}", txt):
                            dados["endereco"] = txt.replace("\n", ", ")
                    if not dados["telefone"] and re.match(r"^[\+\(\d][\d\s\(\)\-\.]{6,}$", txt):
                        dados["telefone"] = txt.strip()
                        dados["whatsapp"] = gerar_whatsapp(txt)
                except Exception:
                    pass
            if dados["endereco"] and dados["telefone"]:
                return dados
        corpo = page.inner_text("body")[:12000]
        if not dados["telefone"]:
            m = PADRAO_TEL.search(corpo)
            if m:
                tel = m.group().strip()
                dados["telefone"] = tel
                dados["whatsapp"] = gerar_whatsapp(tel)
        if not dados["endereco"]:
            pads = re.findall(r"[A-Za-zÀ-ú][^\n]{5,80}(?:\d{5}-\d{3}|\d{8})", corpo)
            if pads:
                dados["endereco"] = pads[0].strip()
    except Exception:
        pass
    return dados

# ──────────────────────────────────────────────────────────────────────────────
# PLANILHA
# ──────────────────────────────────────────────────────────────────────────────

def salvar_xlsx(resultados, cidade, nicho):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    C_H_BG  = "1e8a2e"; C_H_FT  = "FFFFFF"
    C_PAR   = "eaf5eb"; C_IMPAR = "FFFFFF"
    C_BORDA = "a8d4ac"; C_TITU  = "0d4f18"

    def brd(cor=C_BORDA):
        s = Side(style="thin", color=cor)
        return Border(left=s, right=s, top=s, bottom=s)

    ws = wb.active
    ws.title = "Leads"
    ws.merge_cells("A1:H1")
    c = ws["A1"]
    c.value     = f"LEADS — {nicho.upper()} EM {cidade.upper()}"
    c.font      = Font(name="Arial", bold=True, size=14, color=C_TITU)
    c.alignment = Alignment(horizontal="center", vertical="center")
    c.fill      = PatternFill("solid", fgColor="d4edda")
    ws.row_dimensions[1].height = 32

    ws.merge_cells("A2:H2")
    c2 = ws["A2"]
    c2.value     = (f"Gerado em {date.today().strftime('%d/%m/%Y')} · "
                    f"{len(resultados)} estabelecimentos · MCLeadProspecta — Memocash Soluções")
    c2.font      = Font(name="Arial", size=9, color="3a7d44", italic=True)
    c2.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 16
    ws.row_dimensions[3].height = 6

    for col, txt in enumerate(["Nome", "Endereço", "Telefone", "WhatsApp",
                                "Link Maps", "Status", "Observações", "Prioridade"], 1):
        c = ws.cell(row=4, column=col, value=txt)
        c.font      = Font(name="Arial", bold=True, size=10, color=C_H_FT)
        c.fill      = PatternFill("solid", fgColor=C_H_BG)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border    = brd()
    ws.row_dimensions[4].height = 24

    for idx, r in enumerate(resultados, 1):
        lin    = idx + 4
        cor_bg = C_PAR if idx % 2 == 0 else C_IMPAR
        vals   = [r["nome"], r["endereco"] or "—", r["telefone"] or "—",
                  r["whatsapp"] or "—", r["url"], "Novo Lead", "", "Média"]
        for col, val in enumerate(vals, 1):
            c = ws.cell(row=lin, column=col, value=val)
            c.font      = Font(name="Arial", size=9)
            c.fill      = PatternFill("solid", fgColor=cor_bg)
            c.border    = brd()
            c.alignment = Alignment(vertical="center")
            if col == 4 and val.startswith("http"):
                c.hyperlink = val; c.value = "Abrir WhatsApp"
                c.font = Font(name="Arial", size=9, color="0d6b1e", underline="single")
            if col == 5 and val.startswith("http"):
                c.hyperlink = val; c.value = "Ver no Maps"
                c.font = Font(name="Arial", size=9, color="1e8a2e", underline="single")
            if col == 6:
                c.font      = Font(name="Arial", bold=True, size=9, color="1e8a2e")
                c.alignment = Alignment(horizontal="center", vertical="center")
            if col == 8:
                c.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[lin].height = 17

    total = len(resultados) + 4
    op_s  = ('"Novo Lead,Tentativa de Contato,Contactado,Interesse Confirmado,'
             'Em Negociação,Proposta Enviada,Aguardando Retorno,'
             'Fechado ✅,Sem Interesse ❌,Inativo"')
    dv = DataValidation(type="list", formula1=op_s, allow_blank=True, showDropDown=False)
    dv.sqref = f"F5:F{total}"
    ws.add_data_validation(dv)

    dp = DataValidation(type="list", formula1='"Alta 🔴,Média 🟡,Baixa 🟢,VIP ⭐"',
                        allow_blank=True, showDropDown=False)
    dp.sqref = f"H5:H{total}"
    ws.add_data_validation(dp)

    for col, w in zip("ABCDEFGH", [34, 42, 18, 16, 14, 22, 38, 12]):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A5"

    ws3 = wb.create_sheet("Resumo")
    ws3.merge_cells("A1:C1")
    c = ws3["A1"]
    c.value     = "RESUMO DO FUNIL DE VENDAS"
    c.font      = Font(name="Arial", bold=True, size=13, color="FFFFFF")
    c.fill      = PatternFill("solid", fgColor="1e8a2e")
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws3.row_dimensions[1].height = 28

    metricas = [
        ("Total de Leads",    f"=COUNTA('Leads'!A5:A{total})"),
        ("Novo Lead",         f"=COUNTIF('Leads'!F5:F{total},\"Novo Lead\")"),
        ("Contactados",       f"=COUNTIF('Leads'!F5:F{total},\"Contactado\")"),
        ("Em Negociação",     f"=COUNTIF('Leads'!F5:F{total},\"Em Negociação\")"),
        ("Fechados ✅",       f"=COUNTIF('Leads'!F5:F{total},\"Fechado ✅\")"),
        ("Sem Interesse ❌",  f"=COUNTIF('Leads'!F5:F{total},\"Sem Interesse ❌\")"),
        ("Com Telefone",      f"=COUNTIF('Leads'!C5:C{total},\"<>—\")"),
        ("Alta Prioridade",   f"=COUNTIF('Leads'!H5:H{total},\"Alta 🔴\")"),
    ]
    cores_r = ["1e8a2e","27ae3f","2ecc71","145c1f","4CAF50","F44336","00BCD4","f39c12"]
    for i, ((label, formula), cor) in enumerate(zip(metricas, cores_r), 2):
        ws3.row_dimensions[i].height = 26
        cl = ws3.cell(row=i, column=1, value=label)
        cl.font      = Font(name="Arial", bold=True, size=10, color="FFFFFF")
        cl.fill      = PatternFill("solid", fgColor=cor)
        cl.alignment = Alignment(vertical="center", indent=1)
        cv = ws3.cell(row=i, column=2, value=formula)
        cv.font      = Font(name="Arial", bold=True, size=14, color=cor)
        cv.alignment = Alignment(horizontal="center", vertical="center")
    ws3.column_dimensions["A"].width = 28
    ws3.column_dimensions["B"].width = 12

    nome    = f"{sanitizar(cidade)}_{sanitizar(nicho)}_{date.today().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}.xlsx"
    caminho = os.path.join(pasta_output(), nome)
    wb.save(caminho)
    return caminho, nome

# ──────────────────────────────────────────────────────────────────────────────
# WORKER
# ──────────────────────────────────────────────────────────────────────────────

def worker(job_id, cidade, nicho):
    def log(msg):
        with JOBS_LOCK:
            JOBS[job_id]["log"].append(msg)

    def set_prog(p):
        with JOBS_LOCK:
            JOBS[job_id]["progress"] = p

    # Garante que o Playwright encontre o Chromium instalado no build
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", PLAYWRIGHT_BROWSERS_PATH)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("Playwright não instalado no servidor.")
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "erro"
        return

    busca    = f"{nicho} em {cidade}"
    url_maps = f"https://www.google.com/maps/search/{busca.replace(' ', '+')}"
    log(f"Iniciando: {busca}")

    # Usa o Chromium do sistema (Nix) se disponível, caso contrário deixa o Playwright decidir
    chromium_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH") or None

    try:
        with sync_playwright() as p:
            launch_kwargs = dict(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-setuid-sandbox",
                    "--single-process",
                    "--lang=pt-BR",
                ]
            )
            if chromium_path:
                launch_kwargs["executable_path"] = chromium_path

            browser = p.chromium.launch(**launch_kwargs)
            ctx = browser.new_context(
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page_lista = ctx.new_page()
            page_det   = ctx.new_page()

            page_lista.goto(url_maps, timeout=55000, wait_until="domcontentloaded")
            page_det.goto("about:blank")

            try:
                page_lista.wait_for_selector("div[role='feed']", timeout=14000)
            except Exception:
                log("Google Maps não respondeu.")
                with JOBS_LOCK:
                    JOBS[job_id]["status"] = "erro"
                browser.close()
                return

            log("Carregando resultados...")
            painel = page_lista.locator("div[role='feed']")
            for _ in range(14):
                painel.evaluate("el => el.scrollBy(0, 2800)")
                page_lista.wait_for_timeout(1100)
                if page_lista.locator("span:has-text('Você chegou ao fim da lista')").count() > 0:
                    break

            elementos    = page_lista.locator("a[href*='/place/']")
            nomes_vistos = set()
            estabs       = []
            for i in range(elementos.count()):
                try:
                    el   = elementos.nth(i)
                    href = el.get_attribute("href") or ""
                    if "/place/" not in href:
                        continue
                    nome = el.get_attribute("aria-label") or el.inner_text().strip()
                    if nome and len(nome) > 2 and nome not in nomes_vistos and "google" not in nome.lower():
                        nomes_vistos.add(nome)
                        if href.startswith("/"):
                            href = "https://www.google.com" + href
                        estabs.append({"nome": nome, "url": href})
                except Exception:
                    pass

            total_enc = len(estabs)
            log(f"{total_enc} locais encontrados.")
            with JOBS_LOCK:
                JOBS[job_id]["total"] = total_enc

            resultados = []
            for idx, est in enumerate(estabs, 1):
                log(f"[{idx}/{total_enc}] {est['nome'][:50]}")
                det = extrair_detalhes(page_det, est["url"])
                resultados.append({
                    "nome":     est["nome"],
                    "telefone": det["telefone"],
                    "whatsapp": det["whatsapp"],
                    "endereco": det["endereco"],
                    "url":      est["url"],
                })
                set_prog(int(idx / total_enc * 100))
                time.sleep(0.55)

            browser.close()

            caminho, nome_arq = salvar_xlsx(resultados, cidade, nicho)
            com_tel = sum(1 for r in resultados if r["telefone"])
            log(f"Concluído — {len(resultados)} leads · {com_tel} com telefone")

            with JOBS_LOCK:
                JOBS[job_id]["status"]    = "concluido"
                JOBS[job_id]["file_path"] = caminho
                JOBS[job_id]["file_name"] = nome_arq
                JOBS[job_id]["progress"]  = 100

    except Exception as e:
        log(f"Erro: {e}")
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "erro"

# ──────────────────────────────────────────────────────────────────────────────
# ROTAS
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/corrigir", methods=["POST"])
def rota_corrigir():
    data   = request.get_json()
    cidade = corrigir(data.get("cidade", "").strip())
    nicho  = corrigir(data.get("nicho",  "").strip())
    return jsonify({"cidade": cidade, "nicho": nicho})

@app.route("/iniciar", methods=["POST"])
def rota_iniciar():
    data   = request.get_json()
    cidade = corrigir(data.get("cidade", "").strip())
    nicho  = corrigir(data.get("nicho",  "").strip())

    if not cidade or not nicho:
        return jsonify({"erro": "Preencha cidade e nicho"}), 400

    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status":     "rodando",
            "log":        [],
            "progress":   0,
            "file_path":  None,
            "file_name":  None,
            "total":      0,
            "cidade":     cidade,
            "nicho":      nicho,
            "criado_em":  datetime.now().isoformat(),
        }

    threading.Thread(target=worker, args=(job_id, cidade, nicho), daemon=True).start()
    return jsonify({"job_id": job_id, "cidade": cidade, "nicho": nicho})

@app.route("/status/<job_id>")
def rota_status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"erro": "Job não encontrado"}), 404
    return jsonify({
        "status":    job["status"],
        "progress":  job["progress"],
        "log":       job["log"],
        "total":     job["total"],
        "file_name": job.get("file_name"),
    })

@app.route("/download/<job_id>")
def rota_download(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job or job["status"] != "concluido":
        return "Arquivo não disponível", 404
    return send_file(
        job["file_path"],
        as_attachment=True,
        download_name=job["file_name"],
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

@app.route("/historico")
def rota_historico():
    with JOBS_LOCK:
        hist = [
            {
                "cidade":    j["cidade"],
                "nicho":     j["nicho"],
                "status":    j["status"],
                "total":     j["total"],
                "criado_em": j["criado_em"],
                "job_id":    jid,
            }
            for jid, j in JOBS.items()
        ]
    hist.sort(key=lambda x: x["criado_em"], reverse=True)
    return jsonify(hist[:30])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
