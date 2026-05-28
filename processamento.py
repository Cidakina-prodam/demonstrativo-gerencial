"""
processamento.py
Toda a lógica de leitura e cruzamento de dados.
Funções puras — sem nada de Streamlit aqui.
"""

import pandas as pd
import re
from collections import defaultdict

# ── CONSTANTES ────────────────────────────────────────────────────────────────

AUSENCIAS = [
    "FÉRIAS", "LICENÇA", "FALTAS E ATRASOS",
    "Ausência Compensável em Banco de Horas",
    "Problemas técnicos no teletrabalho",
]

STATUS_CORES = {
    "Execução":               "#27AE60",
    "Homologação":            "#2E75B6",
    "Homolog. Expressa":      "#2E75B6",
    "Concluída":              "#7F8C8D",
    "Concluída (integração)": "#7F8C8D",
    "Cancelada":              "#E74C3C",
    "Planejamento":           "#F39C12",
    "Planej. Aprovado":       "#F39C12",
    "Aprovar Planej.":        "#E07B39",
    "Aberta":                 "#9B59B6",
}

PERIODOS = {
    "Janeiro 2026":  ("2025-12-21", "2026-01-20"),
    "Fevereiro 2026":("2026-01-21", "2026-02-20"),
    "Março 2026":    ("2026-02-21", "2026-03-20"),
    "Abril 2026":    ("2026-03-21", "2026-04-20"),
    "Maio 2026":     ("2026-04-21", "2026-05-20"),
    "Junho 2026":    ("2026-05-21", "2026-06-20"),
    "Julho 2026":    ("2026-06-21", "2026-07-20"),
    "Agosto 2026":   ("2026-07-21", "2026-08-20"),
    "Setembro 2026": ("2026-08-21", "2026-09-20"),
    "Outubro 2026":  ("2026-09-21", "2026-10-20"),
    "Novembro 2026": ("2026-10-21", "2026-11-20"),
    "Dezembro 2026": ("2026-11-21", "2026-12-20"),
}


# ── UTILITÁRIOS ───────────────────────────────────────────────────────────────

def san(v: str) -> str:
    if not isinstance(v, str):
        return v
    try:
        v = v.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
    except Exception:
        pass
    return v.replace("\r", "").replace("\n", " ").strip()


def fmt_h(v) -> str:
    return f"{float(v or 0):.2f}h".replace(".", ",")


def periodo_de(mes_ref: str):
    ini, fim = PERIODOS[mes_ref]
    return pd.Timestamp(ini), pd.Timestamp(fim)


# ── CARREGAMENTO DE DADOS ─────────────────────────────────────────────────────

def carregar_csv(arquivos) -> pd.DataFrame:
    dfs = []
    for f in arquivos:
        try:
            df = pd.read_csv(f, sep=";", encoding="utf-8", dtype=str)
        except Exception:
            f.seek(0)
            df = pd.read_csv(f, sep=";", encoding="latin-1", dtype=str)
        df.dropna(how="all", inplace=True)
        dfs.append(df)

    if not dfs:
        return pd.DataFrame()

    lanc = pd.concat(dfs, ignore_index=True)
    lanc = lanc.drop_duplicates(subset=["rf", "atividade", "data", "horas"])

    lanc["rf_norm"]     = lanc["rf"].fillna("").str.strip().str.lower()
    lanc["horas_num"]   = pd.to_numeric(
        lanc["horas"].str.replace(",", ".", regex=False), errors="coerce"
    ).fillna(0)
    lanc["data_dt"]     = pd.to_datetime(lanc["data"], format="%d/%m/%Y", errors="coerce")
    lanc["eh_prodam"]   = lanc["cliente"].fillna("").str.upper().str.strip() == "PRODAM"
    lanc["eh_ausencia"] = lanc["nome_projeto"].isin(AUSENCIAS)
    lanc["gds_csv"]     = lanc["gds"].fillna("").str.strip()
    lanc["gdp_csv"]     = lanc["gdp"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    lanc["atividade"]   = lanc["atividade"].fillna("").str.strip()

    return lanc


def carregar_colaboradores(arquivo) -> pd.DataFrame:
    df = pd.read_excel(arquivo, dtype=str)
    df.columns = df.columns.str.strip()
    df["RF_norm"] = df["RF"].fillna("").str.strip().str.lower()
    df["Tipo"]    = df["Tipo"].fillna("").str.strip()
    df["Núcleo"]  = df["Núcleo"].fillna("").str.strip()
    return df


def carregar_status(arquivo) -> dict:
    try:
        df = pd.read_csv(arquivo, sep=";", encoding="latin-1", dtype=str)
    except Exception:
        arquivo.seek(0)
        df = pd.read_csv(arquivo, sep=";", encoding="utf-8", dtype=str)

    # Tolerar colunas ausentes
    if "ID NGDS" not in df.columns:
        df["ID NGDS"] = ""
    if "ID GDP" not in df.columns:
        df["ID GDP"] = ""
    if "Status" not in df.columns:
        df["Status"] = ""

    df["ID NGDS"] = df["ID NGDS"].fillna("").str.strip()
    df["ID GDP"]  = df["ID GDP"].fillna("").str.strip()
    df["Status"]  = df["Status"].fillna("").str.strip()

    mapa = {}
    for _, row in df.iterrows():
        chave = row["ID NGDS"] if row["ID NGDS"] else row["ID GDP"]
        if chave:
            mapa[chave] = {
                "status": row["Status"],
                "cor": STATUS_CORES.get(row["Status"], "#888"),
            }
    return mapa


# ── PROCESSAMENTO POSICIONAL ─────────────────────────────────────────────────

def processar_posicional(
    estrutura_pdf: dict,
    lanc_df: pd.DataFrame,
    periodo_ini: pd.Timestamp,
    periodo_fim: pd.Timestamp,
    status_map: dict,
) -> dict:
    # Período filtrado — usado apenas para aba Lançamentos/Desempenho
    periodo = lanc_df[
        (lanc_df["data_dt"] >= periodo_ini) &
        (lanc_df["data_dt"] <= periodo_fim)
    ]

    # Para cruzamento Posicional x CSV — único loop vetorizado
    # no_periodo=True: lancamento dentro do periodo
    in_per_mask = (
        lanc_df["data_dt"].notna() &
        (lanc_df["data_dt"] >= periodo_ini) &
        (lanc_df["data_dt"] <= periodo_fim)
    )
    lanc_df["col_in_per"]   = in_per_mask
    lanc_df["col_nome_fmt"] = lanc_df.apply(
        lambda r: san(str(r.get("nome", r["rf"]) or r["rf"])).title(), axis=1
    )
    lanc_df["col_desc_atv"] = lanc_df["titulo_atividade"].fillna("").apply(lambda x: san(str(x)))

    mapa_lanc = defaultdict(list)
    mapa_gdp  = defaultdict(list)
    for row in lanc_df.itertuples(index=False):
        atv     = row.atividade
        gdp_val = row.gdp_csv
        nome    = row.col_nome_fmt
        desc    = row.col_desc_atv
        in_per  = bool(row.col_in_per)
        rf      = row.rf
        data    = row.data
        horas   = row.horas_num

        if atv:
            mapa_lanc[atv].append({
                "rf": rf, "nome": nome, "data": data,
                "horas": horas, "desc": desc, "no_periodo": in_per,
            })
        if gdp_val and gdp_val != "n/d":
            mapa_gdp[gdp_val].append({
                "rf": rf, "nome": nome, "data": data,
                "horas": horas, "desc": desc, "atv": atv, "no_periodo": in_per,
            })

    resultado = {"secretarias": []}

    for sec_def in estrutura_pdf.get("secretarias", []):
        sec_out = {
            "desc": san(sec_def["desc"]),
            "horas": sec_def.get("horas", 0),
            "oss": [],
        }

        for os_def in sec_def.get("oss", []):
            os_out = {"desc": san(os_def["desc"]), "projetos": []}

            for proj_def in os_def.get("projetos", []):
                proj_horas   = 0
                demandas_out = []

                for dem_def in proj_def.get("demandas", []):
                    gds    = str(dem_def.get("gds", ""))
                    gdp    = str(dem_def.get("gdp", ""))
                    titulo = san(dem_def.get("titulo", ""))
                    horas  = float(dem_def.get("horas", 0))
                    ativs  = dem_def.get("atividades", [])
                    proj_horas += horas

                    hit    = status_map.get(gds, {}) if status_map else {}
                    status = hit.get("status", "") if isinstance(hit, dict) else ""

                    colaboradores: dict = defaultdict(
                        lambda: {"nome": "", "rf": "", "lancamentos": []}
                    )
                    faltando = []

                    if ativs:
                        # ── Cruzamento por atividade
                        for atv in ativs:
                            lancs = mapa_lanc.get(atv, [])
                            # Fallback por GDP: se o ID de atividade não bater no mapa_lanc,
                            # tenta achar lançamentos do mesmo GDP no CSV
                            # (ocorre quando posicional usa ID diferente do CSV, ex: Mantis vs OS)
                            if not lancs and gdp:
                                _fb1 = mapa_gdp.get(str(gdp), [])
                                _ids_csv = {l["atv"] for l in _fb1}
                                if atv not in _ids_csv and _fb1:
                                    lancs = _fb1
                            # Fallback 2: casar pelo número do Mantis/atividade no título
                            if not lancs and gdp:
                                atv_num = atv.lstrip("0") or atv
                                for l in mapa_gdp.get(str(gdp), []):
                                    if atv in l.get("desc","") or atv_num in l.get("desc",""):
                                        lancs = mapa_gdp.get(str(gdp), [])
                                        break
                            import sys
                            if gdp in ("173276","173276.0") or atv in ("0268228","371430"):
                                _fb_check = mapa_gdp.get(str(gdp),[])
                                print(f"DEBUG atv={atv!r} gdp={gdp!r} mapa_lanc_hit={bool(mapa_lanc.get(atv))} gdp_key_in_mapa={str(gdp) in mapa_gdp} fb_len={len(_fb_check)} lancs_final={len(lancs)} desc0={_fb_check[0].get('desc','') if _fb_check else 'N/A'!r}", file=sys.stderr)

                            # Faltando: nenhum lançamento no período atual
                            lancs_periodo = [l for l in lancs if l["no_periodo"]]
                            if not lancs_periodo:
                                if lancs:
                                    # Há lançamentos históricos (fora do período) — NÃO é divergência
                                    # Faturamento aprovado com atraso é fluxo normal em alguns contratos
                                    # Exibe com badge 📅 Fora do período como contexto
                                    for l in lancs:
                                        rf = l["rf"]
                                        colaboradores[rf]["nome"] = l["nome"]
                                        colaboradores[rf]["rf"]   = rf
                                        colaboradores[rf]["lancamentos"].append({
                                            "atividade":    atv,
                                            "desc":         l["desc"],
                                            "data":         l["data"],
                                            "horas":        l["horas"],
                                            "gds":          gds,
                                            "gdp":          gdp,
                                            "fora_periodo": True,
                                        })
                                else:
                                    # Nenhum lançamento em nenhum período — divergência real
                                    faltando.append(atv)
                            # Lançamentos do período corrente (contam para faturado)
                            for l in lancs_periodo:
                                rf = l["rf"]
                                colaboradores[rf]["nome"] = l["nome"]
                                colaboradores[rf]["rf"]   = rf
                                colaboradores[rf]["lancamentos"].append({
                                    "atividade": atv,
                                    "desc":      l["desc"],
                                    "data":      l["data"],
                                    "horas":     l["horas"],
                                    "gds":       gds,
                                    "gdp":       gdp,
                                })
                    else:
                        # ── Sem atividades: cruzar pelo GDP — contar horas do período
                        lancs_gdp = mapa_gdp.get(gdp, [])
                        if not lancs_gdp and gds and gds != gdp:
                            lancs_gdp = mapa_gdp.get(gds, [])
                        lancs_gdp_periodo = [l for l in lancs_gdp if l["no_periodo"]]
                        if not lancs_gdp_periodo:
                            # Verificar se há lançamento histórico (fora do período)
                            if lancs_gdp:
                                pass  # há histórico mas não no período — não é divergência
                            else:
                                faltando.append(f"GDP:{gdp}/GDS:{gds}")
                        for l in lancs_gdp_periodo:
                            rf = l["rf"]
                            colaboradores[rf]["nome"] = l["nome"]
                            colaboradores[rf]["rf"]   = rf
                            colaboradores[rf]["lancamentos"].append({
                                "atividade": l["atv"],
                                "desc":      l["desc"],
                                "data":      l["data"],
                                "horas":     l["horas"],
                                "gds":       gds,
                                "gdp":       gdp,
                            })

                    colab_list = []
                    for rf, col in colaboradores.items():
                        h = sum(x["horas"] for x in col["lancamentos"])
                        colab_list.append({**col, "horas": round(h, 2)})
                    colab_list.sort(key=lambda x: x["horas"], reverse=True)

                    if gdp != gds:
                        desc_dem = f"GDP {gdp} / GDS {gds} — {titulo}"
                    else:
                        desc_dem = f"GDP {gdp} — {titulo}"

                    demandas_out.append({
                        "desc":               desc_dem,
                        "horas":              horas,
                        "gdp_id":             gds,
                        "gdp_real":           gdp,
                        "status":             status,
                        "status_cor":         STATUS_CORES.get(status, "#888"),
                        "colaboradores":      colab_list,
                        "atividades_faltando": faltando,
                    })

                os_out["projetos"].append({
                    "desc": f"Projeto: {san(proj_def.get('cod',''))} — "
                            f"{san(proj_def.get('nome',''))}",
                    "horas":    proj_horas,
                    "demandas": demandas_out,
                })

            sec_out["oss"].append(os_out)
        resultado["secretarias"].append(sec_out)

    return resultado


# ── PROCESSAMENTO LANÇAMENTOS ─────────────────────────────────────────────────

def calcular_lancamentos_nucleo(
    colab_df: pd.DataFrame,
    lanc_df: pd.DataFrame,
    nucleo: str,
    periodo_ini: pd.Timestamp,
    periodo_fim: pd.Timestamp,
) -> list:
    periodo = lanc_df[
        (lanc_df["data_dt"] >= periodo_ini) &
        (lanc_df["data_dt"] <= periodo_fim)
    ]

    colab_nucleo = colab_df[colab_df["Núcleo"] == nucleo].copy()
    colab_nucleo = colab_nucleo.sort_values(["Tipo", "Nome"])

    resultado = []
    for _, cr in colab_nucleo.iterrows():
        rf = cr["RF_norm"]
        lc = periodo[periodo["rf_norm"] == rf].copy()

        fat  = lc[(~lc["eh_prodam"]) & (~lc["eh_ausencia"])]["horas_num"].sum()
        nfat = lc[lc["eh_ausencia"]]["horas_num"].sum()
        intp = lc[lc["eh_prodam"] & ~lc["eh_ausencia"]]["horas_num"].sum()

        resultado.append({
            "nome":  san(cr["Nome"]).title(),
            "rf":    san(cr["RF"]),
            "tipo":  cr["Tipo"],
            "espec": san(str(cr.get("Especialização", ""))),
            "fat":   round(fat,  2),
            "nfat":  round(nfat, 2),
            "int":   round(intp, 2),
            "total": round(fat + nfat + intp, 2),
            "lancamentos": lc,
        })

    return resultado


# ── PROCESSAMENTO DESEMPENHO ──────────────────────────────────────────────────

def calcular_desempenho_nucleo(
    colab_df: pd.DataFrame,
    lanc_df: pd.DataFrame,
    fat_map: dict,
    nucleo: str,
    periodo_ini: pd.Timestamp,
    periodo_fim: pd.Timestamp,
    status_map: dict,
) -> list:
    periodo = lanc_df[
        (lanc_df["data_dt"] >= periodo_ini) &
        (lanc_df["data_dt"] <= periodo_fim)
    ]
    fat_per = periodo[(~periodo["eh_prodam"]) & (~periodo["eh_ausencia"])]

    gds_faturados = set(fat_map.get("_gds_faturados", set()))

    colab_nucleo = colab_df[colab_df["Núcleo"] == nucleo].copy()

    resultado = []
    for _, cr in colab_nucleo.iterrows():
        rf    = cr["RF_norm"]
        nome  = san(cr["Nome"]).title()
        tipo  = cr["Tipo"]
        espec = san(str(cr.get("Especialização", "")))

        hlanc = round(
            periodo[periodo["rf_norm"] == rf]["horas_num"].sum(), 2
        )
        hfat  = round(fat_map.get(rf, 0), 2)
        hnfat = round(max(hlanc - hfat, 0), 2)
        pct   = round(hfat / hlanc * 100, 1) if hlanc > 0 else 0

        lc_fat = fat_per[fat_per["rf_norm"] == rf]
        drill  = []
        if not lc_fat.empty:
            for proj_nome, lproj in lc_fat.groupby("nome_projeto", sort=False):
                gdps = []
                for gds_val, lgds in lproj.groupby("gds_csv", sort=False):
                    gdp_val  = lgds["gdp_csv"].iloc[0]
                    tipo_dem = san(str(lgds["tipo_demanda"].iloc[0])) \
                               if "tipo_demanda" in lgds.columns else ""
                    h_gds    = round(lgds["horas_num"].sum(), 2)
                    faturado = str(gds_val) in gds_faturados
                    hit      = (status_map or {}).get(gds_val,
                                (status_map or {}).get(gdp_val, {}))
                    status   = hit.get("status", "") if isinstance(hit, dict) else ""
                    gdps.append({
                        "gds":      san(str(gds_val)),
                        "gdp":      san(str(gdp_val)),
                        "tipo":     tipo_dem,
                        "horas":    h_gds,
                        "faturado": faturado,
                        "status":   status,
                        "cor":      STATUS_CORES.get(status, "#888"),
                    })
                drill.append({
                    "nome":    san(str(proj_nome)),
                    "cliente": san(str(lproj["cliente"].iloc[0])),
                    "gdps":    gdps,
                })

        resultado.append({
            "nome":         nome,
            "rf":           san(cr["RF"]),
            "tipo":         tipo,
            "espec":        espec,
            "lancado":      hlanc,
            "faturado":     hfat,
            "nao_faturado": hnfat,
            "pct_fat":      pct,
            "pct_contrib":  0.0,
            "drill":        drill,
        })

    resultado.sort(key=lambda x: (
        0 if x["tipo"] == "Prodam" else 1,
        x["tipo"],
        x["nome"],
    ))

    tot_fat = sum(c["faturado"] for c in resultado)
    for c in resultado:
        c["pct_contrib"] = round(c["faturado"] / tot_fat * 100, 1) \
                           if tot_fat > 0 else 0.0

    return resultado


def construir_fat_map(pos_estrutura: dict) -> dict:
    """
    Constrói mapa rf_norm -> horas_faturadas a partir da estrutura processada
    do posicional (saída de processar_posicional).

    FIX v2: deduplicação global por (rf, atividade, data, horas).
    Resolve dupla contagem quando o mesmo colaborador aparece em múltiplas
    demandas do mesmo GDS (ex: GDS 27581 com 8 demandas no SS0404/SEME).
    A chave inclui RF para evitar colisão entre colaboradores distintos.
    """
    fat   = defaultdict(float)
    gds_f = set()

    # set global de lançamentos já contados: (rf, atividade, data, horas)
    vistos: set = set()

    for sec in pos_estrutura.get("secretarias", []):
        for os_ in sec.get("oss", []):
            for proj in os_.get("projetos", []):
                for dem in proj.get("demandas", []):
                    gds_f.add(dem.get("gdp_id", ""))
                    for col in dem.get("colaboradores", []):
                        rf = col["rf"].strip().lower()
                        for l in col["lancamentos"]:
                            chave = (rf, l.get("atividade", ""), l.get("data", ""), l["horas"])
                            if chave in vistos:
                                continue
                            vistos.add(chave)
                            fat[rf] = round(fat[rf] + l["horas"], 2)

    fat["_gds_faturados"] = gds_f
    return dict(fat)

