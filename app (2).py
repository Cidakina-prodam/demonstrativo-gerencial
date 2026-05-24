"""
app_gerador.py — Gerador de Demonstrativo Gerencial
Você sobe os arquivos → clica Gerar → baixa o HTML pronto.
"""

import streamlit as st
import pandas as pd
import json
import re
import io
from collections import defaultdict
from pathlib import Path

from processamento import (
    carregar_csv,
    carregar_colaboradores,
    carregar_status,
    processar_posicional,
    construir_fat_map,
    PERIODOS,
    san,
    fmt_h,
    STATUS_CORES,
)

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


# ── CONFIGURAÇÃO ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Gerador Demonstrativo Gerencial",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Gerador de Demonstrativo Gerencial")
st.caption("Suba os arquivos do mês → clique Gerar → baixe o HTML")

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Configuração")

    mes_ref = st.selectbox("Mês de Referência", list(PERIODOS.keys()), index=4)
    ini_str, fim_str = PERIODOS[mes_ref]
    ini = pd.Timestamp(ini_str)
    fim = pd.Timestamp(fim_str)
    st.caption(f"📌 {ini.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}")

    st.markdown("---")
    st.markdown("## 📂 Arquivos")

    csv_files   = st.file_uploader("CSV de Lançamentos", type=["csv"],
                                    accept_multiple_files=True)
    colab_file  = st.file_uploader("Colaboradores (xlsx)", type=["xlsx"])
    status_file = st.file_uploader("Status GDPs (csv) — opcional", type=["csv"])
    pdf_files   = st.file_uploader("PDFs Posicionais", type=["pdf"],
                                    accept_multiple_files=True,
                                    help="Suba os PDFs de todos os contratos do mês")

# ── VERIFICAR UPLOADS ─────────────────────────────────────────────────────────
if not csv_files or not colab_file:
    st.info(
        "👈 **Para gerar o demonstrativo:**\n\n"
        "1. Selecione o mês de referência\n"
        "2. Suba o(s) CSV(s) de lançamentos\n"
        "3. Suba o arquivo de colaboradores\n"
        "4. Suba os PDFs dos posicionais\n"
        "5. Clique em **Gerar HTML**"
    )
    st.stop()

# ── CARREGAR DADOS ─────────────────────────────────────────────────────────────
with st.spinner("Carregando dados..."):
    lanc_df   = carregar_csv(csv_files)
    colab_df  = carregar_colaboradores(colab_file)
    status_map= carregar_status(status_file) if status_file else {}

# ── PARSEAR PDFs ──────────────────────────────────────────────────────────────
posicionais_raw = []   # lista de dicts parsed
if pdf_files:
    st.markdown("### 📄 PDFs detectados")
    cols = st.columns(len(pdf_files))
    for i, pdf_f in enumerate(pdf_files):
        try:
            parsed = parse_posicional_pdf(pdf_f)
            posicionais_raw.append(parsed)
            with cols[i]:
                st.success(
                    f"✅ **{parsed['cliente']}**\n\n"
                    f"{parsed['periodo_ref']} — "
                    f"{parsed['secretarias'][0]['horas']:.2f}h"
                )
        except Exception as e:
            with cols[i]:
                st.error(f"❌ Erro no PDF: {e}")

# ── ASSOCIAR PDF A NÚCLEO ─────────────────────────────────────────────────────
# Mapa OS → núcleo
OS_NUCLEO_MAP = {
    "GDS-1 - Operação Assistida":    "NSS1",
    "NSS-1 - Manutenção e Melhorias":"NSS1",
    "NSS-2 - Manutenção e Melhorias":"NSS2",
    "NSS-3 - Manutenção e Melhorias":"NSS3",
}

# Agrupar demandas por núcleo a partir dos PDFs
pos_por_nucleo = defaultdict(lambda: {"secretarias": []})

for parsed in posicionais_raw:
    for sec_raw in parsed["secretarias"]:
        for os_raw in sec_raw["oss"]:
            # Descobrir núcleo pela descrição da OS
            nucleo = "NSS1"  # default
            for key, nuc in OS_NUCLEO_MAP.items():
                if key in os_raw["desc"]:
                    nucleo = nuc
                    break

            # Agrupar por secretaria dentro do núcleo
            # Encontrar secretaria existente ou criar nova
            sec_desc = sec_raw["desc"]
            sec_existente = next(
                (s for s in pos_por_nucleo[nucleo]["secretarias"]
                 if s["desc"] == sec_desc),
                None
            )
            if sec_existente is None:
                sec_existente = {"desc": sec_desc, "horas": sec_raw["horas"], "oss": []}
                pos_por_nucleo[nucleo]["secretarias"].append(sec_existente)

            sec_existente["oss"].append(os_raw)

# Processar posicional por núcleo
pos_processado = {}
fat_map_global = {}

if posicionais_raw:
    with st.spinner("Cruzando posicional com CSV..."):
        for nucleo, estrutura in pos_por_nucleo.items():
            pos_proc = processar_posicional(estrutura, lanc_df, ini, fim, status_map)
            pos_processado[nucleo] = pos_proc
            fat_map_parcial = construir_fat_map(pos_proc)
            for rf, h in fat_map_parcial.items():
                if rf == "_gds_faturados":
                    fat_map_global.setdefault("_gds_faturados", set()).update(h)
                else:
                    fat_map_global[rf] = round(fat_map_global.get(rf, 0) + h, 2)

# ── BOTÃO GERAR ───────────────────────────────────────────────────────────────
st.markdown("---")
col_btn, col_info = st.columns([1, 3])

with col_btn:
    gerar = st.button("🚀 Gerar HTML", type="primary", use_container_width=True)

with col_info:
    nucleos_com_pos = list(pos_processado.keys())
    if nucleos_com_pos:
        st.info(f"Posicional disponível para: {', '.join(nucleos_com_pos)}")
    else:
        st.warning("Nenhum PDF de posicional carregado — aba Posicional ficará vazia.")

if not gerar:
    st.stop()

# ── GERAR HTML ────────────────────────────────────────────────────────────────
with st.spinner("Gerando HTML..."):

    # Montar LANC por núcleo
    AUSENCIAS = [
        "FÉRIAS","LICENÇA","FALTAS E ATRASOS",
        "Ausência Compensável em Banco de Horas",
        "Problemas técnicos no teletrabalho",
    ]
    lanc_df["eh_prodam"]   = lanc_df["cliente"].fillna("").str.upper().str.strip() == "PRODAM"
    lanc_df["eh_ausencia"] = lanc_df["nome_projeto"].isin(AUSENCIAS)

    periodo = lanc_df[
        (lanc_df["data_dt"] >= ini) & (lanc_df["data_dt"] <= fim)
    ]

    NUCLEOS = ["NSS1","NSS2","NSS3","NC"]
    lanc_por_nucleo = {}
    CAT_MAP = {"Faturável":"fat","Não faturável":"nfat","Interno PRODAM":"int"}

    for nucleo in NUCLEOS:
        cn = colab_df[colab_df["Núcleo"] == nucleo]
        eh_prodam_tipo = cn["Tipo"].fillna("").str.strip().str.upper() == "PRODAM"
        grupos = []
        for tipo_lbl, grp in [("Prodam", cn[eh_prodam_tipo]),
                               ("Fabricas Externas", cn[~eh_prodam_tipo])]:
            if grp.empty: continue
            colabs = []
            for _, cr in grp.sort_values("Nome").iterrows():
                rf = cr["RF_norm"]
                lc = periodo[periodo["rf_norm"] == rf]
                cats = []
                for categ, key in [("Faturável","fat"),("Não faturável","nfat"),("Interno PRODAM","int")]:
                    if categ == "Faturável":
                        lcat = lc[(~lc["eh_prodam"]) & (~lc["eh_ausencia"])]
                    elif categ == "Não faturável":
                        lcat = lc[lc["eh_ausencia"]]
                    else:
                        lcat = lc[lc["eh_prodam"] & ~lc["eh_ausencia"]]
                    if lcat.empty: continue
                    projs = []
                    for pn, lp in lcat.groupby("nome_projeto", sort=False):
                        gdps = []
                        for gds_v, lgds in lp.groupby("gds_csv", sort=False):
                            ativs = []
                            for _, ar in lgds.iterrows():
                                ativs.append({
                                    "id": san(ar.get("atividade","")),
                                    "titulo": san(ar.get("titulo_atividade","")),
                                    "tipo": san(ar.get("tipo_demanda","")),
                                    "data": ar["data_dt"].strftime("%d/%m") if pd.notna(ar["data_dt"]) else "",
                                    "horas": round(ar["horas_num"],2),
                                })
                            gdps.append({
                                "gdp": san(lgds["gdp_csv"].iloc[0]),
                                "gds": san(str(gds_v)),
                                "tipo": san(lgds["tipo_demanda"].iloc[0]) if "tipo_demanda" in lgds.columns else "",
                                "horas": round(lgds["horas_num"].sum(),2),
                                "atividades": ativs,
                            })
                        projs.append({"nome": san(str(pn)), "cliente": san(lp["cliente"].iloc[0]), "gdps": gdps})
                    cats.append({"nome": categ, "key": key, "horas": round(lcat["horas_num"].sum(),2), "projetos": projs})
                colabs.append({
                    "nome": san(cr["Nome"]).title(),
                    "rf": san(cr["RF"]),
                    "especializacao": san(str(cr.get("Especialização",""))),
                    "horas": round(lc["horas_num"].sum(),2),
                    "categorias": cats,
                })
            grupos.append({"tipo": tipo_lbl, "colaboradores": colabs})
        lanc_por_nucleo[nucleo] = {"nome": nucleo, "grupos": grupos}

    # Montar cruzamento
    ativ_faturada = {}
    gds_faturados = set()
    for nucleo, pos_proc in pos_processado.items():
        for sec in pos_proc.get("secretarias", []):
            for os_ in sec["oss"]:
                for proj in os_["projetos"]:
                    for dem in proj["demandas"]:
                        gds = dem.get("gdp_id","")
                        if gds: gds_faturados.add(gds)
                        for col in dem.get("colaboradores",[]):
                            for l in col["lancamentos"]:
                                atv = l.get("atividade","")
                                if atv:
                                    ativ_faturada[atv] = {
                                        "gds": gds,
                                        "gdp": dem.get("gdp_real",""),
                                        "status": dem.get("status",""),
                                        "cor": dem.get("status_cor","#888"),
                                    }

    fat_per = periodo[(~periodo["eh_prodam"]) & (~periodo["eh_ausencia"])]

    def get_drill(rf_norm):
        lc = fat_per[fat_per["rf_norm"] == rf_norm]
        if lc.empty: return []
        projetos = []
        for pn, lp in lc.groupby("nome_projeto", sort=False):
            gdp_map = {}
            for _, row in lp.iterrows():
                atv     = row["atividade"]
                gds_v   = row["gds_csv"]
                gdp_v   = row["gdp_csv"]
                horas   = row["horas_num"]
                tipo    = san(str(row.get("tipo_demanda","") or ""))
                if atv in ativ_faturada:
                    fi = ativ_faturada[atv]
                    faturado = True
                    gds_r, gdp_r = fi["gds"] or gds_v, fi["gdp"] or gdp_v
                    status, cor  = fi["status"], fi["cor"]
                else:
                    faturado = gds_v in gds_faturados
                    gds_r, gdp_r = gds_v, gdp_v
                    hit = (status_map or {}).get(gds_v, (status_map or {}).get(gdp_v, {}))
                    status = hit.get("status","") if isinstance(hit,dict) else ""
                    cor    = STATUS_CORES.get(status,"#888")
                chave = gds_r or gdp_r or atv
                if chave not in gdp_map:
                    gdp_map[chave] = {"gds":gds_r,"gdp":gdp_r,"tipo":tipo,"horas":0,
                                      "faturado":faturado,"status":status,"cor":cor}
                gdp_map[chave]["horas"] = round(gdp_map[chave]["horas"]+horas, 2)
                if faturado:
                    gdp_map[chave]["faturado"] = True
                    gdp_map[chave]["status"]   = status
                    gdp_map[chave]["cor"]       = cor
            projetos.append({"nome":san(str(pn)),"cliente":san(lp["cliente"].iloc[0]),"gdps":list(gdp_map.values())})
        return projetos

    mapa_per = {}
    for rf, grp in periodo.groupby("rf_norm"):
        mapa_per[rf] = round(grp["horas_num"].sum(), 2)

    cruzamento_mes = {"label": mes_ref, "tem_posicional": bool(pos_processado), "nucleos": []}
    for nucleo in NUCLEOS:
        cn = colab_df[colab_df["Núcleo"] == nucleo]
        colab_list = []
        for _, cr in cn.iterrows():
            rf    = cr["RF_norm"]
            nome  = san(cr["Nome"]).title()
            tipo  = cr["Tipo"]
            espec = san(str(cr.get("Especialização","")))
            hlanc = mapa_per.get(rf, 0)
            hfat  = round(fat_map_global.get(rf, 0), 2)
            hnfat = round(max(hlanc-hfat,0), 2)
            pct   = round(hfat/hlanc*100,1) if hlanc>0 else 0
            drill = get_drill(rf) if pos_processado else []
            colab_list.append({
                "nome":nome,"rf":san(cr["RF"]),"tipo":tipo,"espec":espec,
                "lancado":hlanc,"faturado":hfat,"nao_faturado":hnfat,
                "pct_fat":pct,"tem_pos":bool(pos_processado),"externo":tipo!="Prodam","drill":drill
            })
        colab_list.sort(key=lambda x: (0 if x["tipo"]=="Prodam" else 1, x["tipo"], x["nome"]))
        tot_lanc = round(sum(c["lancado"] for c in colab_list), 2)
        tot_fat  = round(sum(c["faturado"] for c in colab_list), 2)
        for c in colab_list:
            c["pct_contrib"] = round(c["faturado"]/tot_fat*100,1) if tot_fat>0 else 0
        cruzamento_mes["nucleos"].append({
            "nome":nucleo,"total_lancado":tot_lanc,"total_faturado":tot_fat,
            "cobertura":round(tot_fat/tot_lanc*100,1) if tot_lanc>0 else 0,
            "colaboradores":colab_list,
        })

    CRUZ = [cruzamento_mes]

    # ── Serializar dados para injetar no HTML template ─────────────────────
    COLORS = ["#2E75B6","#FFD966","#70AD47","#FF6B6B","#9B59B6","#E07B39","#1ABC9C",
              "#E74C3C","#3498DB","#F39C12","#27AE60","#8E44AD","#16A085","#D35400","#2980B9"]

    # Converter pos_processado para formato POS (dict por núcleo)
    pos_json_dict = {k.lower(): v for k, v in pos_processado.items()}

    dados_js = (
        "var POS="     + json.dumps(pos_json_dict,    ensure_ascii=True).replace("'","'") + ";\n"
        "var LANC="    + json.dumps(lanc_por_nucleo,  ensure_ascii=True) + ";\n"
        "var CRUZ="    + json.dumps(CRUZ,              ensure_ascii=True) + ";\n"
        "var CORES="   + json.dumps(COLORS) + ";\n"
        "var STATUS_MAP=" + json.dumps(status_map,    ensure_ascii=True) + ";\n"
    )

    # ── Ler template HTML e injetar dados ─────────────────────────────────
    template_path = Path(__file__).parent / "template.html"
    if not template_path.exists():
        st.error("❌ Arquivo template.html não encontrado! Coloque o HTML base na pasta do app.")
        st.stop()

    with open(template_path, encoding="utf-8") as f:
        html_template = f.read()

    # Substituir bloco de dados
    marker_start = "var POS="
    marker_end   = "var BADGES="
    if marker_start not in html_template or marker_end not in html_template:
        st.error("❌ Template HTML não tem os marcadores esperados (var POS= e var BADGES=).")
        st.stop()

    idx_s = html_template.index(marker_start)
    idx_e = html_template.index(marker_end)
    html_final = html_template[:idx_s] + dados_js + html_template[idx_e:]

    # Atualizar título com mês e período
    html_final = html_final.replace(
        "<title>Demonstrativo Gerencial</title>",
        f"<title>Demonstrativo Gerencial — {mes_ref}</title>"
    )

# ── DOWNLOAD ──────────────────────────────────────────────────────────────────
nome_arquivo = f"Demonstrativo_{mes_ref.replace(' ','_')}.html"
html_bytes   = html_final.encode("utf-8")

st.success(f"✅ HTML gerado! **{len(html_bytes)/1024:.0f} KB**")

st.download_button(
    label    = f"⬇️ Baixar {nome_arquivo}",
    data     = html_bytes,
    file_name= nome_arquivo,
    mime     = "text/html",
    type     = "primary",
    use_container_width=True,
)

st.info(
    "💡 **Como usar o HTML:**\n\n"
    "1. Clique em Baixar\n"
    "2. Abra o arquivo no navegador (Chrome, Edge, Firefox)\n"
    "3. Todas as 3 abas funcionam offline — não precisa de internet"
)
