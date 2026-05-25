"""
pdf_parser.py
Extrai a estrutura do posicional diretamente de PDFs.
Requer: pdfplumber
"""

import re
import pdfplumber


def parse_posicional_pdf(pdf_file) -> dict:
    """
    Extrai estrutura do posicional de um arquivo PDF.
    pdf_file: path (str) ou file-like object
    Retorna dict com cliente, contrato, periodo, secretarias/oss/projetos/demandas/atividades
    """
    with pdfplumber.open(pdf_file) as pdf:
        linhas = []
        for page in pdf.pages:
            texto = page.extract_text()
            if texto:
                for linha in texto.split("\n"):
                    l = linha.strip()
                    if l:
                        linhas.append(l)

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
        "cliente":     cliente,
        "contrato":    contrato,
        "periodo_ref": periodo_ref,
        "data_ini":    data_ini,
        "data_fim":    data_fim,
        "secretarias": [{
            "desc":  f"{cliente} — {contrato}",
            "horas": 0,
            "oss":   [],
        }],
    }
    sec = resultado["secretarias"][0]
    os_cur = proj_cur = dem_cur = None

    # ── Padrões ───────────────────────────────────────────────────────────────
    RE_OS      = re.compile(r'^O\.S\.\s+(.+)$')
    RE_TOTAL_H = re.compile(r'^Total Horas:\s*([\d.,]+)$')
    RE_PROJ    = re.compile(r'^(SH\d+|SS\d+|PS\d+|SJ\d+|SV\d+)\s+(.+?)\s+([\d.,]+)$')
    RE_DEM     = re.compile(r'^(\d{6})\s*-\s*(.+?)\s+(\d{5,6})\s+([\d.,]+)$')
    RE_ATIV    = re.compile(r'^(\d{6})\s+.+')
    RE_SKIP    = re.compile(
        r'^\d+/\d+/\d+.*\d+/\d+$'
        r'|^Total\s+[\d.,]+'
        r'|^Qtdes\.'
        r'|^dez/|^jan/|^fev/|^mar/|^abr/|^mai/|^jun/'
        r'|^jul/|^ago/|^set/|^out/|^nov/'
        r'|^Código\s+Projeto'
        r'|^RELATÓRIO'
        r'|^Cliente:|^Contrato:|^Ordem|^Data Iníc|^Data Fim'
        r'|^Tipo Serv|^Período|^De:'
    )

    # ── Parse linha a linha ───────────────────────────────────────────────────
    i = 0
    while i < len(linhas):
        linha = linhas[i]

        if RE_SKIP.match(linha) or linha == "Atividades":
            i += 1
            continue

        # OS
        m = RE_OS.match(linha)
        if m:
            os_cur  = {"desc": m.group(1).strip(), "horas": 0, "projetos": []}
            proj_cur = dem_cur = None
            sec["oss"].append(os_cur)
            i += 1
            continue

        # Total Horas
        m = RE_TOTAL_H.match(linha)
        if m and os_cur:
            os_cur["horas"] = float(m.group(1).replace(",", "."))
            i += 1
            continue

        # Projeto
        m = RE_PROJ.match(linha)
        if m and os_cur:
            proj_cur = {
                "cod":      m.group(1),
                "nome":     m.group(2).strip(),
                "horas":    float(m.group(3).replace(",", ".")),
                "demandas": [],
            }
            os_cur["projetos"].append(proj_cur)
            dem_cur = None
            i += 1
            continue

        # Demanda
        m = RE_DEM.match(linha)
        if m and proj_cur:
            # Título pode quebrar em linhas seguintes
            titulo = m.group(2).strip()
            j = i + 1
            while j < len(linhas):
                prox = linhas[j]
                if (not RE_DEM.match(prox) and not RE_OS.match(prox) and
                        not RE_PROJ.match(prox) and not RE_TOTAL_H.match(prox) and
                        not RE_ATIV.match(prox) and prox != "Atividades" and
                        not RE_SKIP.match(prox)):
                    titulo += " " + prox
                    j += 1
                else:
                    break
            dem_cur = {
                "gdp":        m.group(1),
                "gds":        m.group(3),
                "titulo":     titulo,
                "horas":      float(m.group(4).replace(",", ".")),
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
    """
    Converte o resultado do parser para o formato usado pelo processamento.py:
    {"secretarias": [{desc, horas, oss: [{desc, projetos: [{cod, nome, demandas: [{gdp, gds, titulo, horas, atividades}]}]}]}]}
    """
    return {"secretarias": parsed["secretarias"]}
