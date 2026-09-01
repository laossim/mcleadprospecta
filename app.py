# MCLeadProspecta Web - Memocash Solucoes - github.com/laossim

import os, re, time, uuid, threading, unicodedata, asyncio
from datetime import date, datetime
from flask import Flask, render_template, request, jsonify, send_file

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "mcleadprospecta-dev")

JOBS = {}
JOBS_LOCK = threading.Lock()

BROWSER_ARGS = [
    "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
    "--disable-blink-features=AutomationControlled",
    "--disable-setuid-sandbox", "--single-process", "--lang=pt-BR",
]
CTX_ARGS = {
    "locale": "pt-BR", "timezone_id": "America/Sao_Paulo",
    "viewport": {"width": 1280, "height": 800},
    "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

def normalizar(t):
    return unicodedata.normalize("NFKD", t).encode("ASCII", "ignore").decode().lower().strip()

CORRECOES = {
    "hamburguer":"hamburguer","hamburger":"hamburguer",
    "pizaria":"pizzaria","pizzeria":"pizzaria",
    "padaraia":"padaria","paderia":"padaria",
    "farmacia":"farmacia","farrmacia":"farmacia","acadmia":"academia",
    "mecanica":"mecanica","mecanico":"mecanico",
    "odontolgia":"odontologia","adovgado":"advogado",
    "contabilidde":"contabilidade","restarante":"restaurante","restrurante":"restaurante",
    "supermecado":"supermercado","barberia":"barbearia","barbaria":"barbearia",
    "estetica":"estetica","esthetica":"estetica",
    "petshop":"pet shop","pet shopt":"pet shop",
    "consulotrio":"consultorio","clinika":"clinica","clincia":"clinica",
    "sorvetaria":"sorveteria","lanchinete":"lanchonete",
    "mrecado":"mercado","ofcina":"oficina","eletrica":"eletrica","hidraulica":"hidraulica",
    "imobilaria":"imobiliaria","hotal":"hotel","hotell":"hotel","pousadda":"pousada",
    "sao paulo":"Sao Paulo","san paulo":"Sao Paulo",
    "rio de janerio":"Rio de Janeiro","rio de janiero":"Rio de Janeiro",
    "belo orizonte":"Belo Horizonte","curitba":"Curitiba","curtiba":"Curitiba",
    "forteleza":"Fortaleza","salvaldor":"Salvador","slavador":"Salvador",
    "manuas":"Manaus","manaos":"Manaus","recfie":"Recife","reciife":"Recife",
    "poro alegre":"Porto Alegre","goainia":"Goiania","goinia":"Goiania",
    "camppinas":"Campinas","campinnas":"Campinas",
    "brasilia":"Brasilia","brazilia":"Brasilia","florianpolis":"Florianopolis",
    "vittoria":"Vitoria","macapa":"Macapa","belem":"Belem","bellem":"Belem",
    "treresina":"Teresina","natel":"Natal","maceio":"Maceio",
    "joao pessoa":"Joao Pessoa","poto velho":"Porto Velho","palmaz":"Palmas",
    "campo grand":"Campo Grande","cuiaba":"Cuiaba",
    "uberlandia":"Uberlandia","uberlania":"Uberlandia","sorocba":"Sorocaba",
    "sanots":"Santos","guaruhos":"Guarulhos","ozasco":"Osasco",
    "joinvile":"Joinville","londrinna":"Londrina","maringa":"Maringa",
    "juiz de forra":"Juiz de Fora","niteroi":"Niteroi","nitroi":"Niteroi",
    "nova iguacu":"Nova Iguacu",
}

def corrigir(texto):
    chave = normalizar(texto)
    if chave in CORRECOES: return CORRECOES[chave]
    return " ".join(CORRECOES.get(normalizar(t), t) for t in texto.strip().split())

def sanitizar(t):
    return re.sub(r"[^\w\s-]", "", t).strip().replace(" ", "_")

def pasta_output():
    p = os.path.join(os.path.dirname(__file__), "outputs")
    os.makedirs(p, exist_ok=True)
    return p

def gerar_whatsapp(tel):
    nums = re.sub(r"\D", "", tel)
    if not nums: return ""
    if not nums.startswith("55"): nums = "55" + nums
    return "https://wa.me/" + nums

PADRAO_TEL = re.compile(r"(?:\+?55\s?)?(?:\(?\d{2}\)?[\s\-]?)(?:9\s?)?\d{4}[\s\-]?\d{4}")

# ── EXTRAÇÃO ASYNC (3 paginas em paralelo) ─────────────────────────────────────

async def extrair_async(page, url):
    dados = {"endereco": "", "telefone": "", "whatsapp": ""}
    try:
        await page.goto(url, timeout=11000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1100)

        # Botoes ARIA (mais confiavel para telefone)
        botoes = page.locator("button[aria-label]")
        cnt = await botoes.count()
        for i in range(min(cnt, 25)):
            try:
                aria = await botoes.nth(i).get_attribute("aria-label") or ""
                al = aria.lower()
                if not dados["endereco"] and any(k in al for k in ("endereco:","address:")):
                    dados["endereco"] = re.sub(r"^[^:]+:\s*", "", aria).strip()
                if not dados["telefone"] and any(k in al for k in ("telefone:","phone:","numero")):
                    tel = re.sub(r"^[^:]+:\s*", "", aria).strip()
                    if tel: dados["telefone"] = tel; dados["whatsapp"] = gerar_whatsapp(tel)
            except Exception:
                pass
            if dados["endereco"] and dados["telefone"]: return dados

        # Divs de info
        for classe in ("Io6YTe", "rogA2c", "AeaXub", "LrzXr"):
            divs = page.locator("div." + classe)
            cnt = await divs.count()
            for i in range(min(cnt, 15)):
                try:
                    txt = (await divs.nth(i).inner_text()).strip()
                    if not txt: continue
                    if not dados["endereco"] and len(txt) > 10 and "," in txt and re.search(r"\d{4,}", txt):
                        if not re.search(r"[\+\(].*\d{4}", txt):
                            dados["endereco"] = txt.replace("\n", ", ")
                    if not dados["telefone"] and re.match(r"^[\(\+\d][\d\s\(\)\-\.]{7,}$", txt):
                        dados["telefone"] = txt.strip(); dados["whatsapp"] = gerar_whatsapp(txt)
                except Exception:
                    pass
            if dados["endereco"] and dados["telefone"]: return dados

        # Regex fallback
        try:
            corpo = (await page.inner_text("body"))[:8000]
            if not dados["telefone"]:
                m = PADRAO_TEL.search(corpo)
                if m:
                    dados["telefone"] = m.group().strip()
                    dados["whatsapp"] = gerar_whatsapp(dados["telefone"])
        except Exception:
            pass
    except Exception:
        pass
    return dados


async def coletar_detalhes_async(estabs, job_id, log_fn, prog_fn, stats_fn):
    from playwright.async_api import async_playwright

    N = 3  # paginas paralelas — 3x mais rapido
    total = len(estabs)
    resultados = []
    alock = asyncio.Lock()
    done = [0]
    t_inicio = time.time()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=BROWSER_ARGS)

        # Pool de N paginas
        pool = asyncio.Queue()
        pages_all = []
        for _ in range(N):
            ctx = await browser.new_context(**CTX_ARGS)
            pg = await ctx.new_page()
            await pg.set_default_timeout(12000)
            await pool.put(pg)
            pages_all.append(pg)

        async def processar(est):
            with JOBS_LOCK:
                if JOBS[job_id].get("cancelado"): return

            pg = await pool.get()
            try:
                det = await extrair_async(pg, est["url"])
                r = {"nome": est["nome"], "url": est["url"],
                     "telefone": det["telefone"], "whatsapp": det["whatsapp"],
                     "endereco": det["endereco"]}
                async with alock:
                    resultados.append(r)
                    done[0] += 1
                    n_tel = sum(1 for x in resultados if x["telefone"])
                    elapsed = time.time() - t_inicio
                    rate = done[0] / elapsed if elapsed > 0 else 0
                    eta = int((total - done[0]) / rate) if rate > 0 else 0

                    tag = " [tel]" if det["telefone"] else ""
                    log_fn("[" + str(done[0]) + "/" + str(total) + "] " + est["nome"][:45] + tag)
                    prog_fn(int(done[0] / total * 100))
                    stats_fn(done[0], n_tel, est["nome"], round(rate * 60, 1), eta)
            except Exception:
                pass
            finally:
                await pool.put(pg)

        await asyncio.gather(*[processar(est) for est in estabs], return_exceptions=True)

        for pg in pages_all:
            try: await pg.close()
            except Exception: pass
        await browser.close()

    return resultados

# ── PLANILHA ──────────────────────────────────────────────────────────────────

def salvar_xlsx(resultados, cidade, nicho, tag=""):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    def brd():
        s = Side(style="thin", color="a8d4ac")
        return Border(left=s, right=s, top=s, bottom=s)

    ws = wb.active; ws.title = "Leads"
    ws.merge_cells("A1:H1")
    c = ws["A1"]
    c.value = "LEADS - " + nicho.upper() + " EM " + cidade.upper()
    c.font = Font(name="Arial", bold=True, size=14, color="0d4f18")
    c.alignment = Alignment(horizontal="center", vertical="center")
    c.fill = PatternFill("solid", fgColor="d4edda")
    ws.row_dimensions[1].height = 32

    ws.merge_cells("A2:H2")
    c2 = ws["A2"]
    c2.value = "Gerado em " + date.today().strftime("%d/%m/%Y") + " - " + str(len(resultados)) + " leads - MCLeadProspecta"
    c2.font = Font(name="Arial", size=9, color="3a7d44", italic=True)
    c2.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 16; ws.row_dimensions[3].height = 6

    for col, txt in enumerate(["Nome","Endereco","Telefone","WhatsApp","Link Maps","Status","Observacoes","Prioridade"], 1):
        c = ws.cell(row=4, column=col, value=txt)
        c.font = Font(name="Arial", bold=True, size=10, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1e8a2e")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = brd()
    ws.row_dimensions[4].height = 24

    for idx, r in enumerate(resultados, 1):
        lin = idx + 4
        cor = "eaf5eb" if idx % 2 == 0 else "FFFFFF"
        vals = [r["nome"], r["endereco"] or "-", r["telefone"] or "-",
                r["whatsapp"] or "-", r["url"], "Novo Lead", "", "Media"]
        for col, val in enumerate(vals, 1):
            c = ws.cell(row=lin, column=col, value=val)
            c.font = Font(name="Arial", size=9)
            c.fill = PatternFill("solid", fgColor=cor)
            c.border = brd()
            c.alignment = Alignment(vertical="center")
            if col == 4 and val.startswith("http"):
                c.hyperlink = val; c.value = "WhatsApp"
                c.font = Font(name="Arial", size=9, color="0d6b1e", underline="single")
            if col == 5 and val.startswith("http"):
                c.hyperlink = val; c.value = "Maps"
                c.font = Font(name="Arial", size=9, color="1e8a2e", underline="single")
            if col == 6:
                c.font = Font(name="Arial", bold=True, size=9, color="1e8a2e")
                c.alignment = Alignment(horizontal="center", vertical="center")
            if col == 8:
                c.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[lin].height = 17

    total = len(resultados) + 4
    for sqref, f1 in [
        ("F5:F"+str(total), '"Novo Lead,Tentativa de Contato,Contactado,Em Negociacao,Proposta Enviada,Fechado,Sem Interesse,Inativo"'),
        ("H5:H"+str(total), '"Alta,Media,Baixa,VIP"'),
    ]:
        dv = DataValidation(type="list", formula1=f1, allow_blank=True, showDropDown=False)
        dv.sqref = sqref; ws.add_data_validation(dv)

    for col, w in zip("ABCDEFGH", [34,42,18,16,12,22,36,10]):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A5"

    sfx = ("_" + tag) if tag else ""
    nome = sanitizar(cidade) + "_" + sanitizar(nicho) + "_" + date.today().strftime("%Y%m%d") + sfx + "_" + uuid.uuid4().hex[:6] + ".xlsx"
    caminho = os.path.join(pasta_output(), nome)
    wb.save(caminho)
    return caminho, nome

# ── WORKER (thread principal + asyncio interno) ────────────────────────────────

MAX_MIN = 25

def worker(job_id, cidade, nicho):
    inicio = time.time()

    def log(msg):
        with JOBS_LOCK: JOBS[job_id]["log"].append(msg)

    def set_prog(p):
        with JOBS_LOCK: JOBS[job_id]["progress"] = p

    def set_stats(coletados, com_tel, atual, rate, eta):
        with JOBS_LOCK:
            JOBS[job_id]["coletados"] = coletados
            JOBS[job_id]["com_telefone"] = com_tel
            JOBS[job_id]["atual"] = atual
            JOBS[job_id]["rate"] = rate
            JOBS[job_id]["eta"] = eta

    def deve_parar():
        with JOBS_LOCK: c = JOBS[job_id].get("cancelado", False)
        return c or (time.time() - inicio) > (MAX_MIN * 60)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("Playwright nao instalado.")
        with JOBS_LOCK: JOBS[job_id]["status"] = "erro"
        return

    busca = nicho + " em " + cidade
    log("Iniciando: " + busca)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
            ctx = browser.new_context(**CTX_ARGS)
            page = ctx.new_page()
            page.set_default_timeout(15000)

            url_maps = "https://www.google.com/maps/search/" + busca.replace(" ", "+")
            page.goto(url_maps, timeout=50000, wait_until="domcontentloaded")

            try:
                page.wait_for_selector("div[role='feed']", timeout=14000)
            except Exception:
                log("Google Maps nao respondeu.")
                with JOBS_LOCK: JOBS[job_id]["status"] = "erro"
                browser.close(); return

            log("Carregando lista...")
            SCROLL_JS = "const f=document.querySelector('div[role=\'feed\']');if(f)f.scrollBy(0,2800);"
            for _ in range(14):
                try:
                    page.evaluate(SCROLL_JS)
                except Exception:
                    pass
                page.wait_for_timeout(800)
                if page.locator("span:has-text('fim da lista')").count() > 0: break

            elementos = page.locator("a[href*='/place/']")
            nomes_vistos = set()
            estabs = []
            for i in range(elementos.count()):
                try:
                    el = elementos.nth(i)
                    href = el.get_attribute("href") or ""
                    if "/place/" not in href: continue
                    nome = el.get_attribute("aria-label") or el.inner_text().strip()
                    if nome and len(nome) > 2 and nome not in nomes_vistos and "google" not in nome.lower():
                        nomes_vistos.add(nome)
                        if href.startswith("/"): href = "https://www.google.com" + href
                        estabs.append({"nome": nome, "url": href})
                except Exception: pass

            page.close(); browser.close()

        total_enc = len(estabs)
        log(str(total_enc) + " locais. Coletando com 3 paginas em paralelo...")
        with JOBS_LOCK: JOBS[job_id]["total"] = total_enc

        # Coleta async (3x mais rapido)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            resultados = loop.run_until_complete(
                coletar_detalhes_async(estabs, job_id, log, set_prog, set_stats)
            )
        finally:
            loop.close()

        if not resultados:
            log("Nenhum resultado.")
            with JOBS_LOCK: JOBS[job_id]["status"] = "erro"; return

        caminho, nome_arq = salvar_xlsx(resultados, cidade, nicho)
        com_tel = sum(1 for r in resultados if r["telefone"])
        log("Concluido - " + str(len(resultados)) + " leads - " + str(com_tel) + " com telefone")

        with JOBS_LOCK:
            JOBS[job_id]["status"] = "concluido"
            JOBS[job_id]["file_path"] = caminho
            JOBS[job_id]["file_name"] = nome_arq
            JOBS[job_id]["progress"] = 100
            JOBS[job_id]["com_telefone"] = com_tel
            JOBS[job_id]["coletados"] = len(resultados)

    except Exception as e:
        log("Erro: " + str(e))
        with JOBS_LOCK: JOBS[job_id]["status"] = "erro"

# ── ROTAS ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index(): return render_template("index.html")

@app.route("/corrigir", methods=["POST"])
def rota_corrigir():
    d = request.get_json()
    return jsonify({"cidade": corrigir(d.get("cidade","").strip()), "nicho": corrigir(d.get("nicho","").strip())})

@app.route("/iniciar", methods=["POST"])
def rota_iniciar():
    d = request.get_json()
    cidade = corrigir(d.get("cidade","").strip())
    nicho  = corrigir(d.get("nicho","").strip())
    if not cidade or not nicho: return jsonify({"erro": "Preencha cidade e nicho"}), 400
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status":"rodando","log":[],"progress":0,
            "file_path":None,"file_name":None,"file_path_parcial":None,
            "total":0,"coletados":0,"com_telefone":0,
            "atual":"","rate":0,"eta":0,"cancelado":False,
            "cidade":cidade,"nicho":nicho,"criado_em":datetime.now().isoformat(),
        }
    threading.Thread(target=worker, args=(job_id,cidade,nicho), daemon=True).start()
    return jsonify({"job_id":job_id,"cidade":cidade,"nicho":nicho})

@app.route("/cancelar/<job_id>", methods=["POST"])
def rota_cancelar(job_id):
    with JOBS_LOCK:
        if job_id in JOBS: JOBS[job_id]["cancelado"] = True
    return jsonify({"ok":True})

@app.route("/status/<job_id>")
def rota_status(job_id):
    with JOBS_LOCK: job = JOBS.get(job_id)
    if not job: return jsonify({"erro":"nao encontrado"}), 404
    return jsonify({
        "status":      job["status"],
        "progress":    job["progress"],
        "log":         job["log"][-40:],
        "total":       job["total"],
        "coletados":   job.get("coletados",0),
        "com_telefone":job.get("com_telefone",0),
        "atual":       job.get("atual",""),
        "rate":        job.get("rate",0),
        "eta":         job.get("eta",0),
        "file_name":   job.get("file_name"),
        "tem_parcial": job.get("file_path_parcial") is not None,
    })

@app.route("/download/<job_id>")
def rota_download(job_id):
    with JOBS_LOCK: job = JOBS.get(job_id)
    if not job: return "nao encontrado", 404
    caminho = job.get("file_path") or job.get("file_path_parcial")
    nome    = job.get("file_name") or "leads_parcial.xlsx"
    if not caminho: return "arquivo nao disponivel", 404
    return send_file(caminho, as_attachment=True, download_name=nome,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/historico")
def rota_historico():
    with JOBS_LOCK:
        hist = [{"cidade":j["cidade"],"nicho":j["nicho"],"status":j["status"],
                 "total":j["total"],"criado_em":j["criado_em"],"job_id":jid}
                for jid,j in JOBS.items()]
    hist.sort(key=lambda x:x["criado_em"],reverse=True)
    return jsonify(hist[:30])


@app.route("/reportar", methods=["POST"])
def rota_reportar():
    import urllib.request, json as _json
    d = request.get_json()
    msg = d.get("mensagem", "")
    log_txt = d.get("log", "")
    webhook = os.environ.get("DISCORD_WEBHOOK", "")
    if webhook:
        payload = {
            "content": "**Reporte MCLeadProspecta**",
            "embeds": [{
                "title": "Erro reportado pelo usuario",
                "description": ("**Mensagem:** " + msg[:300] + "\n\n**Log:**\n```" + log_txt[-800:] + "```") if log_txt else msg[:1000],
                "color": 0xe05252
            }]
        }
        try:
            req = urllib.request.Request(webhook,
                data=_json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST")
            urllib.request.urlopen(req, timeout=5)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "erro": str(e)}), 500
    return jsonify({"ok": False, "erro": "Webhook nao configurado"}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)), debug=False)
