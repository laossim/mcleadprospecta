# MCLeadProspecta Web - Memocash Solucoes - github.com/laossim

import os, re, time, uuid, threading, unicodedata
from datetime import date, datetime
from flask import Flask, render_template, request, jsonify, send_file

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "mcleadprospecta-dev")

JOBS = {}
JOBS_LOCK = threading.Lock()

def normalizar(t):
    return unicodedata.normalize("NFKD", t).encode("ASCII", "ignore").decode().lower().strip()

CORRECOES = {
    "hamburguer":"hamburguer","hamburger":"hamburguer",
    "pizaria":"pizzaria","pizzeria":"pizzaria",
    "padaraia":"padaria","paderia":"padaria",
    "farmacia":"farmacia","farrmacia":"farmacia",
    "acadmia":"academia","mecanica":"mecanica","mecanico":"mecanico",
    "odontolgia":"odontologia","adovgado":"advogado",
    "contabilidde":"contabilidade",
    "restarante":"restaurante","restrurante":"restaurante",
    "supermecado":"supermercado",
    "barberia":"barbearia","barbaria":"barbearia",
    "estetica":"estetica","esthetica":"estetica",
    "petshop":"pet shop","pet shopt":"pet shop",
    "consulotrio":"consultorio","clinika":"clinica","clincia":"clinica",
    "sorvetaria":"sorveteria","lanchinete":"lanchonete",
    "mrecado":"mercado","ofcina":"oficina",
    "eletrica":"eletrica","hidraulica":"hidraulica",
    "imobilaria":"imobiliaria","hotal":"hotel","hotell":"hotel",
    "pousadda":"pousada",
    "sao paulo":"Sao Paulo","san paulo":"Sao Paulo",
    "rio de janerio":"Rio de Janeiro","rio de janiero":"Rio de Janeiro",
    "belo orizonte":"Belo Horizonte",
    "curitba":"Curitiba","curtiba":"Curitiba",
    "forteleza":"Fortaleza","salvaldor":"Salvador","slavador":"Salvador",
    "manuas":"Manaus","manaos":"Manaus","recfie":"Recife","reciife":"Recife",
    "poro alegre":"Porto Alegre","goainia":"Goiania","goinia":"Goiania",
    "camppinas":"Campinas","campinnas":"Campinas",
    "brasilia":"Brasilia","brazilia":"Brasilia",
    "florianpolis":"Florianopolis","vittoria":"Vitoria",
    "macapa":"Macapa","belem":"Belem","bellem":"Belem",
    "treresina":"Teresina","natel":"Natal",
    "maceio":"Maceio","joao pessoa":"Joao Pessoa",
    "poto velho":"Porto Velho","palmaz":"Palmas",
    "campo grand":"Campo Grande","cuiaba":"Cuiaba",
    "uberlandia":"Uberlandia","uberlania":"Uberlandia","sorocba":"Sorocaba",
    "sanots":"Santos","guaruhos":"Guarulhos","ozasco":"Osasco",
    "joinvile":"Joinville","londrinna":"Londrina","maringa":"Maringa",
    "juiz de forra":"Juiz de Fora",
    "niteroi":"Niteroi","nitroi":"Niteroi","nova iguacu":"Nova Iguacu",
}

def corrigir(texto):
    chave = normalizar(texto)
    if chave in CORRECOES:
        return CORRECOES[chave]
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

# ── EXTRAIR DETALHES (roda na thread principal do worker, Playwright-safe) ──────

def extrair_detalhes(page, url):
    """Extrai telefone e endereco de uma pagina do Maps.
    page.set_default_timeout() garante que nenhuma operacao trava mais de 12s.
    """
    dados = {"endereco": "", "telefone": "", "whatsapp": ""}
    try:
        page.goto(url, timeout=12000, wait_until="domcontentloaded")
        page.wait_for_timeout(1800)

        # Tenta pelos botoes ARIA (mais confiavel)
        try:
            botoes = page.locator("button[aria-label]")
            count = botoes.count()
            for i in range(min(count, 30)):
                try:
                    aria = botoes.nth(i).get_attribute("aria-label") or ""
                    al = aria.lower()
                    if not dados["endereco"] and any(k in al for k in ("endereco:", "address:", "endere")):
                        dados["endereco"] = re.sub(r"^[^:]+:\s*", "", aria).strip()
                    if not dados["telefone"] and any(k in al for k in ("telefone:", "phone:", "numero")):
                        tel = re.sub(r"^[^:]+:\s*", "", aria).strip()
                        if tel:
                            dados["telefone"] = tel
                            dados["whatsapp"] = gerar_whatsapp(tel)
                except Exception:
                    pass
                if dados["endereco"] and dados["telefone"]:
                    return dados
        except Exception:
            pass

        # Tenta pelas divs de info
        try:
            for classe in ("Io6YTe", "rogA2c", "AeaXub", "LrzXr"):
                divs = page.locator("div." + classe)
                count = divs.count()
                for i in range(min(count, 20)):
                    try:
                        txt = divs.nth(i).inner_text().strip()
                        if not txt:
                            continue
                        if not dados["endereco"] and len(txt) > 10 and "," in txt and re.search(r"\d{4,}", txt):
                            if not re.search(r"[\+\(].*\d{4}", txt):
                                dados["endereco"] = txt.replace("\n", ", ")
                        if not dados["telefone"] and re.match(r"^[\(\+\d][\d\s\(\)\-\.]{7,}$", txt):
                            dados["telefone"] = txt.strip()
                            dados["whatsapp"] = gerar_whatsapp(txt)
                    except Exception:
                        pass
                if dados["endereco"] and dados["telefone"]:
                    return dados
        except Exception:
            pass

        # Fallback: regex no texto da pagina
        try:
            corpo = page.inner_text("body")[:10000]
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

# ── PLANILHA ──────────────────────────────────────────────────────────────────

def salvar_xlsx(resultados, cidade, nicho, sufixo=""):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    C_H_BG = "1e8a2e"; C_H_FT = "FFFFFF"
    C_PAR = "eaf5eb"; C_IMPAR = "FFFFFF"
    C_BORDA = "a8d4ac"; C_TITU = "0d4f18"

    def brd(cor=C_BORDA):
        s = Side(style="thin", color=cor)
        return Border(left=s, right=s, top=s, bottom=s)

    ws = wb.active; ws.title = "Leads"
    ws.merge_cells("A1:H1")
    c = ws["A1"]
    c.value = "LEADS - " + nicho.upper() + " EM " + cidade.upper()
    c.font = Font(name="Arial", bold=True, size=14, color=C_TITU)
    c.alignment = Alignment(horizontal="center", vertical="center")
    c.fill = PatternFill("solid", fgColor="d4edda")
    ws.row_dimensions[1].height = 32

    ws.merge_cells("A2:H2")
    c2 = ws["A2"]
    c2.value = "Gerado em " + date.today().strftime("%d/%m/%Y") + " - " + str(len(resultados)) + " leads - MCLeadProspecta"
    c2.font = Font(name="Arial", size=9, color="3a7d44", italic=True)
    c2.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 16
    ws.row_dimensions[3].height = 6

    for col, txt in enumerate(["Nome","Endereco","Telefone","WhatsApp","Link Maps","Status","Observacoes","Prioridade"], 1):
        c = ws.cell(row=4, column=col, value=txt)
        c.font = Font(name="Arial", bold=True, size=10, color=C_H_FT)
        c.fill = PatternFill("solid", fgColor=C_H_BG)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = brd()
    ws.row_dimensions[4].height = 24

    for idx, r in enumerate(resultados, 1):
        lin = idx + 4
        cor_bg = C_PAR if idx % 2 == 0 else C_IMPAR
        vals = [r["nome"], r["endereco"] or "-", r["telefone"] or "-",
                r["whatsapp"] or "-", r["url"], "Novo Lead", "", "Media"]
        for col, val in enumerate(vals, 1):
            c = ws.cell(row=lin, column=col, value=val)
            c.font = Font(name="Arial", size=9)
            c.fill = PatternFill("solid", fgColor=cor_bg)
            c.border = brd()
            c.alignment = Alignment(vertical="center")
            if col == 4 and val.startswith("http"):
                c.hyperlink = val; c.value = "Abrir WhatsApp"
                c.font = Font(name="Arial", size=9, color="0d6b1e", underline="single")
            if col == 5 and val.startswith("http"):
                c.hyperlink = val; c.value = "Ver no Maps"
                c.font = Font(name="Arial", size=9, color="1e8a2e", underline="single")
            if col == 6:
                c.font = Font(name="Arial", bold=True, size=9, color="1e8a2e")
                c.alignment = Alignment(horizontal="center", vertical="center")
            if col == 8:
                c.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[lin].height = 17

    total = len(resultados) + 4
    op_s = '"Novo Lead,Tentativa de Contato,Contactado,Em Negociacao,Proposta Enviada,Fechado,Sem Interesse,Inativo"'
    dv = DataValidation(type="list", formula1=op_s, allow_blank=True, showDropDown=False)
    dv.sqref = "F5:F" + str(total); ws.add_data_validation(dv)
    dp = DataValidation(type="list", formula1='"Alta,Media,Baixa,VIP"', allow_blank=True, showDropDown=False)
    dp.sqref = "H5:H" + str(total); ws.add_data_validation(dp)

    for col, w in zip("ABCDEFGH", [34,42,18,16,14,22,38,12]):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A5"

    tag = ("_" + sufixo) if sufixo else ""
    nome = sanitizar(cidade) + "_" + sanitizar(nicho) + "_" + date.today().strftime("%Y%m%d") + tag + "_" + uuid.uuid4().hex[:6] + ".xlsx"
    caminho = os.path.join(pasta_output(), nome)
    wb.save(caminho)
    return caminho, nome

# ── WORKER ────────────────────────────────────────────────────────────────────

MAX_MINUTOS = 25

def worker(job_id, cidade, nicho):
    inicio = time.time()

    def log(msg):
        with JOBS_LOCK:
            JOBS[job_id]["log"].append(msg)

    def set_prog(p):
        with JOBS_LOCK:
            JOBS[job_id]["progress"] = p

    def deve_parar():
        with JOBS_LOCK:
            cancelado = JOBS[job_id].get("cancelado", False)
        expirou = (time.time() - inicio) > (MAX_MINUTOS * 60)
        return cancelado, expirou

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
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-setuid-sandbox", "--single-process", "--lang=pt-BR",
                ]
            )
            ctx = browser.new_context(
                locale="pt-BR", timezone_id="America/Sao_Paulo",
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            )

            # Todas as operacoes Playwright na mesma thread — thread-safe
            page_lista = ctx.new_page()
            page_lista.set_default_timeout(15000)

            url_maps = "https://www.google.com/maps/search/" + busca.replace(" ", "+")
            page_lista.goto(url_maps, timeout=50000, wait_until="domcontentloaded")

            try:
                page_lista.wait_for_selector("div[role='feed']", timeout=14000)
            except Exception:
                log("Google Maps nao respondeu.")
                with JOBS_LOCK: JOBS[job_id]["status"] = "erro"
                browser.close(); return

            log("Carregando lista...")
            painel = page_lista.locator("div[role='feed']")
            for _ in range(14):
                painel.evaluate("el => el.scrollBy(0, 2800)")
                page_lista.wait_for_timeout(900)
                if page_lista.locator("span:has-text('fim da lista')").count() > 0:
                    break

            elementos = page_lista.locator("a[href*='/place/']")
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
                except Exception:
                    pass

            page_lista.close()

            total_enc = len(estabs)
            log(str(total_enc) + " locais. Coletando contatos...")
            with JOBS_LOCK: JOBS[job_id]["total"] = total_enc

            # Pagina unica para detalhes — reaproveitada (sem threading)
            page_det = ctx.new_page()
            page_det.set_default_timeout(12000)  # qualquer op trava -> TimeoutError em 12s

            resultados = []
            for idx, est in enumerate(estabs, 1):
                cancelado, expirou = deve_parar()
                if cancelado:
                    log("Cancelado. Salvando " + str(len(resultados)) + " leads...")
                    break
                if expirou:
                    log("Tempo limite (" + str(MAX_MINUTOS) + "min). Salvando " + str(len(resultados)) + " leads...")
                    break

                log("[" + str(idx) + "/" + str(total_enc) + "] " + est["nome"][:50])
                det = extrair_detalhes(page_det, est["url"])

                tel_ok = "tel:" + det["telefone"] if det["telefone"] else ""
                resultados.append({
                    "nome": est["nome"],
                    "telefone": det["telefone"],
                    "whatsapp": det["whatsapp"],
                    "endereco": det["endereco"],
                    "url": est["url"],
                })
                set_prog(int(idx / total_enc * 100))

                # Salva parcial a cada 15 leads
                if idx % 15 == 0 and resultados:
                    try:
                        cp, _ = salvar_xlsx(resultados, cidade, nicho, "parcial" + str(idx))
                        with JOBS_LOCK: JOBS[job_id]["file_path_parcial"] = cp
                        com_tel_p = sum(1 for r in resultados if r["telefone"])
                        log("Parcial salvo: " + str(idx) + " leads, " + str(com_tel_p) + " com tel")
                    except Exception:
                        pass

            page_det.close()
            browser.close()

            if not resultados:
                log("Nenhum resultado coletado.")
                with JOBS_LOCK: JOBS[job_id]["status"] = "erro"
                return

            caminho, nome_arq = salvar_xlsx(resultados, cidade, nicho)
            com_tel = sum(1 for r in resultados if r["telefone"])
            log("Concluido - " + str(len(resultados)) + " leads - " + str(com_tel) + " com telefone")

            with JOBS_LOCK:
                JOBS[job_id]["status"] = "concluido"
                JOBS[job_id]["file_path"] = caminho
                JOBS[job_id]["file_name"] = nome_arq
                JOBS[job_id]["progress"] = 100

    except Exception as e:
        log("Erro: " + str(e))
        with JOBS_LOCK: JOBS[job_id]["status"] = "erro"

# ── ROTAS ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/corrigir", methods=["POST"])
def rota_corrigir():
    data = request.get_json()
    return jsonify({
        "cidade": corrigir(data.get("cidade","").strip()),
        "nicho":  corrigir(data.get("nicho","").strip()),
    })

@app.route("/iniciar", methods=["POST"])
def rota_iniciar():
    data = request.get_json()
    cidade = corrigir(data.get("cidade","").strip())
    nicho  = corrigir(data.get("nicho","").strip())
    if not cidade or not nicho:
        return jsonify({"erro": "Preencha cidade e nicho"}), 400
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "rodando", "log": [], "progress": 0,
            "file_path": None, "file_name": None, "file_path_parcial": None,
            "total": 0, "cancelado": False,
            "cidade": cidade, "nicho": nicho,
            "criado_em": datetime.now().isoformat(),
        }
    threading.Thread(target=worker, args=(job_id, cidade, nicho), daemon=True).start()
    return jsonify({"job_id": job_id, "cidade": cidade, "nicho": nicho})

@app.route("/cancelar/<job_id>", methods=["POST"])
def rota_cancelar(job_id):
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]["cancelado"] = True
    return jsonify({"ok": True})

@app.route("/status/<job_id>")
def rota_status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"erro": "Job nao encontrado"}), 404
    return jsonify({
        "status":    job["status"],
        "progress":  job["progress"],
        "log":       job["log"],
        "total":     job["total"],
        "file_name": job.get("file_name"),
        "tem_parcial": job.get("file_path_parcial") is not None,
    })

@app.route("/download/<job_id>")
def rota_download(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return "Nao encontrado", 404
    caminho = job.get("file_path") or job.get("file_path_parcial")
    nome    = job.get("file_name") or "leads_parcial.xlsx"
    if not caminho:
        return "Arquivo nao disponivel", 404
    return send_file(caminho, as_attachment=True, download_name=nome,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/historico")
def rota_historico():
    with JOBS_LOCK:
        hist = [{"cidade":j["cidade"],"nicho":j["nicho"],"status":j["status"],
                 "total":j["total"],"criado_em":j["criado_em"],"job_id":jid}
                for jid,j in JOBS.items()]
    hist.sort(key=lambda x: x["criado_em"], reverse=True)
    return jsonify(hist[:30])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)), debug=False)
