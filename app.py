"""
app.py — Gerador de Demonstrativo Gerencial PRODAM
Versão consolidada com todas as funcionalidades:
- Acumulação de meses (HTML anterior)
- Remoção/reprocessamento de meses históricos
- Mapeamento correto de núcleos por cliente+contrato
- Aba Op. Assistida
"""

import streamlit as st
import pandas as pd
import json
import re as _re
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
from pdf_parser import parse_posicional_pdf

# ── CONFIGURAÇÃO ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Gerador Demonstrativo Gerencial",
    page_icon="📊",
    layout="wide",
)
st.title("📊 Gerador de Demonstrativo Gerencial")
st.caption("Suba os arquivos do mês → clique Gerar → baixe o HTML")

# ── EXTRAIR DADOS HISTÓRICOS DO HTML ANTERIOR ─────────────────────────────────
def extrair_dados_html(html_file) -> dict:
    try:
        texto = html_file.read().decode("utf-8")
    except Exception:
        return {}

    def _extrair_var(nome, txt):
        pat = "var " + nome + r"=(.+?);\n"
        m = _re.search(pat, txt)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                return None
        return None

    return {
        "pos":    _extrair_var("POS",        texto) or {},
        "lanc":   _extrair_var("LANC",       texto) or {},
        "cruz":   _extrair_var("CRUZ",       texto) or [],
        "oa":     _extrair_var("OA",         texto) or {},
        "status": _extrair_var("STATUS_MAP", texto) or {},
    }

# ── MAPEAMENTO CLIENTE+CONTRATO → NÚCLEO ──────────────────────────────────────
# Regras avaliadas em ordem; a primeira que bater vence.
REGRAS_NUCLEO = [
    # NSS2 — dois contratos HSPM distintos (várias grafias)
    ("HSPM", "TC 094",  "NSS2"),
    ("HSPM", "TC094",   "NSS2"),
    ("HSPM", "TC-094",  "NSS2"),
    ("HSPM", "TC 273",  "NSS2"),
    ("HSPM", "TC273",   "NSS2"),
    ("HSPM", "TC-273",  "NSS2"),
    ("HSPM", "",        "NSS2"),  # fallback: qualquer PDF com HSPM é NSS2
    # NSS1
    ("SMS",  "",        "NSS1"),
    # NSS3
    ("SEME", "",        "NSS3"),
    ("SMDET","",        "NSS3"),
    # NC
    ("SMADS","",        "NC"),
    ("SMDHC","",        "NC"),
    ("SMC",  "",        "NC"),
    ("SPCINE","",       "NC"),
    ("FTM",  "",        "NC"),
    ("SMPED","",        "NC"),
]

def _nucleo_do_parsed(parsed: dict) -> str:
    cliente  = (parsed.get("cliente")  or "").upper()
    contrato = (parsed.get("contrato") or "").upper()
    for trecho_cli, trecho_cont, nucleo in REGRAS_NUCLEO:
        if trecho_cli.upper() in cliente:
            if not trecho_cont or trecho_cont.upper() in contrato:
                return nucleo
    return "NSS1"  # fallback

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

    html_anterior = st.file_uploader(
        "📄 HTML anterior (opcional — acumula histórico)",
        type=["html"],
        help="Suba o HTML do mês anterior para manter histórico acumulado"
    )

    # Gerenciamento de meses históricos
    meses_remover = []
    if html_anterior:
        html_anterior.seek(0)
        _dados_prev = extrair_dados_html(html_anterior)
        html_anterior.seek(0)
        _cruz_prev = _dados_prev.get("cruz") or []
        _labels_prev = [m.get("label","") for m in _cruz_prev if m.get("label")]
        if _labels_prev:
            st.markdown("**📅 Meses no arquivo anterior:**")
            meses_remover = st.multiselect(
                "Remover meses (opcional):",
                options=_labels_prev,
                help="Selecione meses para remover do histórico antes de gerar"
            )
            if meses_remover:
                st.warning(f"⚠️ {len(meses_remover)} mês(es) será(ão) removido(s): {', '.join(meses_remover)}")

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

# ── CARREGAR DADOS ────────────────────────────────────────────────────────────
with st.spinner("Carregando dados..."):
    lanc_df    = carregar_csv(csv_files)
    colab_df   = carregar_colaboradores(colab_file)
    status_map = carregar_status(status_file) if status_file else {}

# ── PARSEAR PDFs ──────────────────────────────────────────────────────────────
posicionais_raw = []
if pdf_files:
    st.markdown("### 📄 PDFs detectados")
    cols = st.columns(min(len(pdf_files), 4))
    for i, pdf_f in enumerate(pdf_files):
        try:
            parsed = parse_posicional_pdf(pdf_f)
            posicionais_raw.append(parsed)
            with cols[i % len(cols)]:
                nucleo_det = _nucleo_do_parsed(parsed)
                st.success(
                    f"✅ **{parsed['cliente']}**\n\n"
                    f"{parsed['periodo_ref']} — "
                    f"{parsed['secretarias'][0]['horas']:.2f}h\n\n"
                    f"Núcleo: **{nucleo_det}**"
                )
        except Exception as e:
            with cols[i % len(cols)]:
                st.error(f"❌ Erro no PDF: {e}")

# ── ASSOCIAR PDF A NÚCLEO ─────────────────────────────────────────────────────
pos_por_nucleo = defaultdict(lambda: {"secretarias": []})

for parsed in posicionais_raw:
    nucleo = _nucleo_do_parsed(parsed)
    for sec_raw in parsed["secretarias"]:
        sec_desc = sec_raw["desc"]
        sec_existente = next(
            (s for s in pos_por_nucleo[nucleo]["secretarias"]
             if s["desc"] == sec_desc), None
        )
        if sec_existente is None:
            sec_existente = {"desc": sec_desc, "horas": sec_raw["horas"], "oss": []}
            pos_por_nucleo[nucleo]["secretarias"].append(sec_existente)
        for os_raw in sec_raw["oss"]:
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
                                    "id":    san(ar.get("atividade","")),
                                    "titulo":san(ar.get("titulo_atividade","")),
                                    "tipo":  san(ar.get("tipo_demanda","")),
                                    "data":  ar["data_dt"].strftime("%d/%m") if pd.notna(ar["data_dt"]) else "",
                                    "horas": round(ar["horas_num"],2),
                                })
                            gdps.append({
                                "gdp":      san(lgds["gdp_csv"].iloc[0]),
                                "gds":      san(str(gds_v)),
                                "tipo":     san(lgds["tipo_demanda"].iloc[0]) if "tipo_demanda" in lgds.columns else "",
                                "horas":    round(lgds["horas_num"].sum(),2),
                                "atividades": ativs,
                            })
                        projs.append({"nome": san(str(pn)), "cliente": san(lp["cliente"].iloc[0]), "gdps": gdps})
                    cats.append({"nome": categ, "key": key, "horas": round(lcat["horas_num"].sum(),2), "projetos": projs})
                colabs.append({
                    "nome":          san(cr["Nome"]).title(),
                    "rf":            san(cr["RF"]),
                    "rf_norm":       rf,
                    "especializacao":san(str(cr.get("Especialização",""))),
                    "horas":         round(lc["horas_num"].sum(),2),
                    "categorias":    cats,
                })
            grupos.append({"tipo": tipo_lbl, "colaboradores": colabs})
        lanc_por_nucleo[nucleo] = {"nome": nucleo, "grupos": grupos}

    # ── Montar cruzamento ─────────────────────────────────────────────────────
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
                                        "gds":    gds,
                                        "gdp":    dem.get("gdp_real",""),
                                        "status": dem.get("status",""),
                                        "cor":    dem.get("status_cor","#888"),
                                    }

    fat_per = periodo[(~periodo["eh_prodam"]) & (~periodo["eh_ausencia"])]

    def get_drill(rf_norm):
        lc = fat_per[fat_per["rf_norm"] == rf_norm]
        if lc.empty: return []
        projetos = []
        for pn, lp in lc.groupby("nome_projeto", sort=False):
            gdp_map = {}
            for _, row in lp.iterrows():
                atv   = row["atividade"]
                gds_v = row["gds_csv"]
                gdp_v = row["gdp_csv"]
                horas = row["horas_num"]
                tipo  = san(str(row.get("tipo_demanda","") or ""))
                if atv in ativ_faturada:
                    fi = ativ_faturada[atv]
                    faturado = True
                    gds_r, gdp_r = fi["gds"] or gds_v, fi["gdp"] or gdp_v
                    status, cor  = fi["status"], fi["cor"]
                else:
                    faturado = gds_v in gds_faturados
                    gds_r, gdp_r = gds_v, gdp_v
                    hit    = (status_map or {}).get(gds_v, (status_map or {}).get(gdp_v, {}))
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
                "pct_fat":pct,"tem_pos":bool(pos_processado),"externo":tipo!="Prodam","drill":drill,
                "pct_contrib":0,
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

    # ── OPERAÇÃO ASSISTIDA ────────────────────────────────────────────────────
    _td = periodo["tipo_demanda"].fillna("").str.upper()
    _os = periodo["ordem_servico"].fillna("").str.upper() if "ordem_servico" in periodo.columns else _td
    eh_oa = _td.str.contains("ASSISTIDA", na=False) | _os.str.contains("ASSISTIDA", na=False)
    periodo_oa = periodo[eh_oa]

    oa_por_nucleo = {}
    for nucleo in NUCLEOS:
        cn = colab_df[colab_df["Núcleo"] == nucleo]
        colabs_oa = []
        total_oa = 0.0
        for _, cr in cn.iterrows():
            rf = cr["RF_norm"]
            lc_oa = periodo_oa[periodo_oa["rf_norm"] == rf]
            if lc_oa.empty:
                continue
            h_oa = round(lc_oa["horas_num"].sum(), 2)
            total_oa += h_oa
            projs = []
            for pn, lp in lc_oa.groupby("nome_projeto", sort=False):
                gdps = []
                for gds_v, lgds in lp.groupby("gds_csv", sort=False):
                    ativs = []
                    for _, ar in lgds.iterrows():
                        ativs.append({
                            "id":    san(ar.get("atividade", "")),
                            "titulo":san(ar.get("titulo_atividade", "")),
                            "data":  ar["data_dt"].strftime("%d/%m") if pd.notna(ar["data_dt"]) else "",
                            "horas": round(ar["horas_num"], 2),
                        })
                    # Descrição da demanda/GDP: pegar do titulo_atividade mais comum ou nome_projeto
                    _desc_gdp = ""
                    if "titulo_atividade" in lgds.columns:
                        # Filtrar linhas que contêm "assistida" no tipo para pegar a descrição real
                        _desc_gdp = san(lgds["titulo_atividade"].iloc[0]) if not lgds.empty else ""
                    gdps.append({
                        "gdp":        san(lgds["gdp_csv"].iloc[0]),
                        "gds":        san(str(gds_v)),
                        "cliente":    san(lgds["cliente"].iloc[0]),
                        "desc":       _desc_gdp,
                        "horas":      round(lgds["horas_num"].sum(), 2),
                        "atividades": ativs,
                    })
                projs.append({"nome": san(str(pn)), "gdps": gdps,
                              "horas": round(lp["horas_num"].sum(), 2)})
            colabs_oa.append({
                "nome":     san(cr["Nome"]).title(),
                "rf":       san(cr["RF"]),
                "tipo":     cr["Tipo"],
                "espec":    san(str(cr.get("Especialização", ""))),
                "horas":    h_oa,
                "projetos": projs,
            })
        colabs_oa.sort(key=lambda x: x["horas"], reverse=True)
        oa_por_nucleo[nucleo] = {
            "nome":         nucleo,
            "total":        round(total_oa, 2),
            "colaboradores":colabs_oa,
        }

    OA_MES = {"label": mes_ref, "nucleos": oa_por_nucleo}

    # ── Mesclar com histórico do HTML anterior ────────────────────────────────
    dados_hist = {}
    if html_anterior:
        html_anterior.seek(0)
        dados_hist = extrair_dados_html(html_anterior)

    pos_json_dict = {k.lower(): v for k, v in pos_processado.items()}
    pos_final = dict(dados_hist.get("pos") or {})
    pos_final.update(pos_json_dict)

    lanc_final = dict(dados_hist.get("lanc") or {})
    lanc_final.update(lanc_por_nucleo)

    cruz_hist = list(dados_hist.get("cruz") or [])
    meses_excluir = set(meses_remover) | {mes_ref}
    cruz_filtrado = [m for m in cruz_hist if m.get("label") not in meses_excluir]
    cruz_final = cruz_filtrado + CRUZ

    # OA: histórico acumulado por mês
    oa_hist = dict(dados_hist.get("oa") or {})
    oa_hist[mes_ref] = OA_MES
    # Remover meses excluídos do histórico OA também
    for m in meses_remover:
        oa_hist.pop(m, None)

    status_final = dict(dados_hist.get("status") or {})
    if status_map:
        status_final.update(status_map)

    # ── Serializar ────────────────────────────────────────────────────────────
    COLORS = ["#2E75B6","#FFD966","#70AD47","#FF6B6B","#9B59B6","#E07B39","#1ABC9C",
              "#E74C3C","#3498DB","#F39C12","#27AE60","#8E44AD","#16A085","#D35400","#2980B9"]

    dados_js = (
        "var POS="        + json.dumps(pos_final,    ensure_ascii=True) + ";\n"
        "var LANC="       + json.dumps(lanc_final,   ensure_ascii=True) + ";\n"
        "var CRUZ="       + json.dumps(cruz_final,   ensure_ascii=True) + ";\n"
        "var OA="         + json.dumps(oa_hist,      ensure_ascii=True) + ";\n"
        "var CORES="      + json.dumps(COLORS)                          + ";\n"
        "var STATUS_MAP=" + json.dumps(status_final, ensure_ascii=True) + ";\n"
    )

    # ── Ler template e injetar dados ──────────────────────────────────────────
    template_path = Path(__file__).parent / "template.html"
    if not template_path.exists():
        st.error("❌ Arquivo template.html não encontrado!")
        st.stop()

    with open(template_path, encoding="utf-8") as f:
        html_template = f.read()

    marker_start = "var POS="
    marker_end   = "var BADGES="
    if marker_start not in html_template or marker_end not in html_template:
        st.error("❌ Template HTML não tem os marcadores esperados.")
        st.stop()

    idx_s = html_template.index(marker_start)
    idx_e = html_template.index(marker_end)
    html_final = html_template[:idx_s] + dados_js + html_template[idx_e:]
    html_final = html_final.replace(
        "<title>Demonstrativo Gerencial</title>",
        f"<title>Demonstrativo Gerencial — {mes_ref}</title>"
    )

# ── DOWNLOAD ──────────────────────────────────────────────────────────────────
nome_arquivo = f"Demonstrativo_{mes_ref.replace(' ','_')}.html"
html_bytes   = html_final.encode("utf-8")

st.success(f"✅ HTML gerado! **{len(html_bytes)/1024:.0f} KB**")
st.download_button(
    label           = f"⬇️ Baixar {nome_arquivo}",
    data            = html_bytes,
    file_name       = nome_arquivo,
    mime            = "text/html",
    type            = "primary",
    use_container_width=True,
)
