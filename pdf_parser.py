"""
pdf_parser.py
Extrai a estrutura do posicional diretamente de PDFs.
Suporta PDFs com texto embutido e PDFs baseados em imagem (via OCR automático).
Requer: pdfplumber; pytesseract + pdf2image para PDFs-imagem.
"""

import re
import pdfplumber


def _extrair_linhas_pdf(pdf_file) -> list:
    # Ler bytes uma vez — garante que pdfplumber e pdf2image usam o mesmo conteúdo
    import io as _io
    if hasattr(pdf_file, 'getvalue'):
        raw = pdf_file.getvalue()          # Streamlit UploadedFile
    elif hasattr(pdf_file, 'read'):
        raw = pdf_file.read()
        if hasattr(pdf_file, 'seek'):
            pdf_file.seek(0)
    else:
        with open(pdf_file, 'rb') as fh:
            raw = fh.read()

    # Tentativa 1: extração de texto nativo com pdfplumber
    linhas = []
    try:
        with pdfplumber.open(_io.BytesIO(raw)) as pdf:
            for page in pdf.pages:
                texto = page.extract_text()
                if texto:
                    for linha in texto.split("\n"):
                        l = linha.strip()
                        if l:
                            linhas.append(l)
    except Exception:
        pass

    # Tentativa 2: OCR se o PDF for baseado em imagem (< 3 linhas úteis)
    linhas_uteis = [l for l in linhas if len(l) > 5]
    if len(linhas_uteis) <= 3:
        try:
            from pdf2image import convert_from_bytes
            import pytesseract

            pages = convert_from_bytes(raw, dpi=200)
            linhas = []
            for page in pages:
                texto = pytesseract.image_to_string(page, lang='por')
                for linha in texto.split("\n"):
                    l = linha.strip()
                    if l:
                        linhas.append(l)
        except Exception as e:
            # Log visível no Streamlit Cloud
            import sys
            print(f"[pdf_parser] OCR falhou: {e}", file=sys.stderr)

    return linhas


# ── Padrões globais ──────────────────────────────────────────────────────────
RE_OS       = re.compile(r'^O\.S\.\s+(.+)$', re.IGNORECASE)
RE_OS_SEM   = re.compile(r'^Sem O\.[sS]\.$')
RE_TOTAL_H  = re.compile(r'^Total Horas:?\s*([\d.,]*)$')
RE_PROJ     = re.compile(r'^(SH\d+|SS\d+|PS\d+|SJ\d+|SV\d+|SB\d+|SU\d+|HM\d+)\s+(.+?)\s+([\d.,]+)$')
RE_PROJ_COD = re.compile(r'^(SH\d+|SS\d+|PS\d+|SJ\d+|SV\d+|SB\d+|SU\d+|HM\d+)$')
RE_PROJ_NH  = re.compile(r'^(.+?)\s+([\d]+[.,][\d]+)$')
RE_DEM      = re.compile(r'^(\d{6})\s*-\s*(.+?)\s+(\d{5,6})\s+([\d.,]+)$')
RE_ATIV     = re.compile(r'^(\d{6,7})\s+.+')
RE_NUM      = re.compile(r'^([\d]+[.,][\d]+)$')
RE_SKIP     = re.compile(
    r'^\d+/\d+/\d+.*\d+/\d+$'
    r'|^Total\s+[\d.,]+'
    r'|^Total$'
    r'|^Qtdes\.|^Otdes\.'
    r'|^dez/|^jan/|^fev/|^mar/|^abr/|^mai/|^jun/'
    r'|^jul/|^ago/|^set/|^out/|^nov/'
    r'|^Código\s+Projeto|^Código$'
    r'|^Projeto\s+Demanda'
    r'|^RELATÓRIO'
    r'|^Cliente:|^Contrato:|^Ordem|^Data Iníc|^Data Fim'
    r'|^Tipo Serv|^Período|^De:'
    r'|^prodam|^prociam'
    r'|^\d+/\d+/\d{4}\s+\d+:\d+'  # timestamp
    r'|^\d+$'                        # zeros soltos da tabela Qtdes
    r'|^\d+/\d+$'                    # página "1/3"
)


def parse_posicional_pdf(pdf_file) -> dict:
    linhas = _extrair_linhas_pdf(pdf_file)

    # ── Cabeçalho ────────────────────────────────────────────────────────────
    cliente = contrato = periodo_ref = data_ini = data_fim = ""
    for l in linhas[:40]:
        if l.startswith("Cliente:"):
            cliente = l.replace("Cliente:", "").strip()
        if l.startswith("Contrato:"):
            contrato = l.replace("Contrato:", "").strip()
        m = re.search(r"Período do Referência:\s*(\S+)", l)
        if m:
            periodo_ref = m.group(1)
        m = re.search(r"De:\s*([\d/]+)\s*Até:\s*([\d/]+)", l)
        if m:
            data_ini, data_fim = m.group(1), m.group(2)

    resultado = {
        "cliente": cliente, "contrato": contrato,
        "periodo_ref": periodo_ref, "data_ini": data_ini, "data_fim": data_fim,
        "secretarias": [{"desc": f"{cliente} — {contrato}", "horas": 0, "oss": []}],
    }
    sec = resultado["secretarias"][0]
    os_cur = proj_cur = dem_cur = None

    # Pré-processar: coletar códigos de projeto que aparecem sozinhos ANTES da OS
    # (OCR do cabeçalho da tabela mistura código HM com header)
    # Eles serão usados em ordem quando um projeto sem código aparecer
    codigos_pre = []
    for l in linhas:
        if RE_OS.match(l) or RE_OS_SEM.match(l):
            break
        if RE_PROJ_COD.match(l):
            codigos_pre.append(RE_PROJ_COD.match(l).group(1))

    fila_codigos = list(codigos_pre)  # consumidos na ordem quando proj sem código aparece

    aguardando_total    = False
    aguardando_proj_nome = None

    i = 0
    while i < len(linhas):
        linha = linhas[i]

        if RE_SKIP.match(linha) or linha == "Atividades":
            i += 1
            continue

        # "Sem O.s." linha separada
        if RE_OS_SEM.match(linha):
            os_cur = {"desc": "Sem O.S.", "horas": 0, "projetos": []}
            proj_cur = dem_cur = None
            sec["oss"].append(os_cur)
            aguardando_total = False
            # Próxima linha pode ser o total
            if i+1 < len(linhas):
                prox = linhas[i+1]
                m2 = RE_NUM.match(prox)
                if m2:
                    os_cur["horas"] = float(m2.group(1).replace(",", "."))
                    i += 2
                    continue
            i += 1
            continue

        # OS normal
        m = RE_OS.match(linha)
        if m:
            os_cur = {"desc": m.group(1).strip(), "horas": 0, "projetos": []}
            proj_cur = dem_cur = None
            sec["oss"].append(os_cur)
            aguardando_total = False
            i += 1
            continue

        # Total Horas
        m = RE_TOTAL_H.match(linha)
        if m and os_cur:
            val = m.group(1).strip()
            if val:
                os_cur["horas"] = float(val.replace(",", "."))
                aguardando_total = False
            else:
                aguardando_total = True
            i += 1
            continue

        # Número solto após "Total Horas:" vazio
        if aguardando_total and os_cur:
            m2 = RE_NUM.match(linha)
            if m2:
                os_cur["horas"] = float(m2.group(1).replace(",", "."))
                aguardando_total = False
                i += 1
                continue
            aguardando_total = False

        # Projeto completo: código + nome + horas
        m = RE_PROJ.match(linha)
        if m and os_cur:
            proj_cur = {
                "cod": m.group(1), "nome": m.group(2).strip(),
                "horas": float(m.group(3).replace(",", ".")), "demandas": [],
            }
            os_cur["projetos"].append(proj_cur)
            dem_cur = None
            aguardando_proj_nome = None
            i += 1
            continue

        # Código isolado no corpo (após OS) — aguarda nome na próxima linha
        m = RE_PROJ_COD.match(linha)
        if m and os_cur:
            aguardando_proj_nome = m.group(1)
            i += 1
            continue

        # Nome+horas do projeto quando código veio separado
        if aguardando_proj_nome and os_cur:
            m2 = RE_PROJ_NH.match(linha)
            if m2:
                proj_cur = {
                    "cod": aguardando_proj_nome, "nome": m2.group(1).strip(),
                    "horas": float(m2.group(2).replace(",", ".")), "demandas": [],
                }
                os_cur["projetos"].append(proj_cur)
                dem_cur = None
                aguardando_proj_nome = None
                i += 1
                continue
            aguardando_proj_nome = None

        # Projeto OCR sem código na linha (ex: "SISTEMA SGH 689.55")
        # Usa código da fila pré-coletada
        if os_cur and not proj_cur and fila_codigos:
            m2 = RE_PROJ_NH.match(linha)
            if m2 and not RE_DEM.match(linha) and not RE_ATIV.match(linha):
                cod = fila_codigos.pop(0)
                proj_cur = {
                    "cod": cod, "nome": m2.group(1).strip(),
                    "horas": float(m2.group(2).replace(",", ".")), "demandas": [],
                }
                os_cur["projetos"].append(proj_cur)
                dem_cur = None
                i += 1
                continue

        # Demanda
        m = RE_DEM.match(linha)
        if m and proj_cur:
            titulo = m.group(2).strip()
            j = i + 1
            while j < len(linhas):
                prox = linhas[j]
                if (not RE_DEM.match(prox) and not RE_OS.match(prox) and
                        not RE_OS_SEM.match(prox) and not RE_PROJ.match(prox) and
                        not RE_PROJ_COD.match(prox) and not RE_TOTAL_H.match(prox) and
                        not RE_ATIV.match(prox) and prox != "Atividades" and
                        not RE_SKIP.match(prox)):
                    titulo += " " + prox
                    j += 1
                else:
                    break
            dem_cur = {
                "gdp": m.group(1), "gds": m.group(3),
                "titulo": titulo, "horas": float(m.group(4).replace(",", ".")),
                "atividades": [],
            }
            proj_cur["demandas"].append(dem_cur)
            i = j
            continue

        # Atividade
        m = RE_ATIV.match(linha)
        if m and dem_cur:
            dem_cur["atividades"].append(m.group(1))
            i += 1
            continue

        i += 1

    sec["horas"] = sum(os_["horas"] for os_ in sec["oss"])
    return resultado


def estrutura_para_pos_format(parsed: dict) -> dict:
    return {"secretarias": parsed["secretarias"]}
