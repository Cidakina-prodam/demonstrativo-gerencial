"""
visao_lancamentos.py
Renderiza a aba de Lançamentos.
"""

import streamlit as st
import pandas as pd
from processamento import calcular_lancamentos_nucleo, fmt_h, san


def render_lancamentos(
    colab_df: pd.DataFrame,
    lanc_df: pd.DataFrame,
    nucleo: str,
    periodo_ini: pd.Timestamp,
    periodo_fim: pd.Timestamp,
):
    """Renderiza a visão de lançamentos para o núcleo selecionado."""

    rows = calcular_lancamentos_nucleo(
        colab_df, lanc_df, nucleo, periodo_ini, periodo_fim
    )

    if not rows:
        st.warning(f"Nenhum colaborador encontrado para o núcleo {nucleo}.")
        return

    # ── CARDS DE TOTAIS ───────────────────────────────────────────────────────
    tot_fat  = sum(r["fat"]   for r in rows)
    tot_nfat = sum(r["nfat"]  for r in rows)
    tot_int  = sum(r["int"]   for r in rows)
    tot_geral= tot_fat + tot_nfat + tot_int

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🟢 Faturável",      fmt_h(tot_fat))
    c2.metric("🔴 Não Faturável",  fmt_h(tot_nfat))
    c3.metric("🔵 Interno PRODAM", fmt_h(tot_int))
    c4.metric("⚪ Total Geral",    fmt_h(tot_geral))

    st.markdown("---")

    # ── BUSCA E CONTROLES ─────────────────────────────────────────────────────
    col_busca, col_exp = st.columns([3, 1])
    with col_busca:
        busca = st.text_input("🔍 Buscar colaborador", "", key=f"busca_lanc_{nucleo}")
    with col_exp:
        expandir_todos = st.checkbox("Expandir todos", key=f"exp_lanc_{nucleo}")

    # ── AGRUPAMENTO POR TIPO ──────────────────────────────────────────────────
    # Prodam primeiro, depois fábricas em ordem alfabética
    tipos_presentes = ["Prodam"] + sorted(set(
        r["tipo"] for r in rows if r["tipo"] != "Prodam"
    ))

    for tipo in tipos_presentes:
        grupo = [
            r for r in rows
            if r["tipo"] == tipo
            and (not busca or busca.lower() in r["nome"].lower())
        ]
        if not grupo:
            continue

        grupo.sort(key=lambda x: x["nome"])

        # Cabeçalho do grupo
        cor = "#1F4E79" if tipo == "Prodam" else "#2E75B6"
        st.markdown(
            f'<div style="background:{cor};color:white;padding:7px 16px;'
            f'border-radius:7px;font-size:.78rem;font-weight:700;'
            f'letter-spacing:1px;text-transform:uppercase;margin:14px 0 6px">'
            f'{tipo}</div>',
            unsafe_allow_html=True,
        )

        for r in grupo:
            lc: pd.DataFrame = r["lancamentos"]
            total_str = fmt_h(r["total"])
            fat_str   = fmt_h(r["fat"])
            label     = (
                f"**{r['nome']}** "
                f"{'· ' + r['espec'] if r['espec'] else ''} "
                f"&nbsp;|&nbsp; Fat: **{fat_str}** "
                f"&nbsp;|&nbsp; Total: **{total_str}**"
            )

            with st.expander(label, expanded=expandir_todos):
                if lc.empty:
                    st.warning("Sem lançamentos no período.")
                    continue

                # Sub-abas por categoria
                cats = []
                fat_df  = lc[(~lc["eh_prodam"]) & (~lc["eh_ausencia"])]
                nfat_df = lc[lc["eh_ausencia"]]
                int_df  = lc[lc["eh_prodam"] & ~lc["eh_ausencia"]]

                if not fat_df.empty:  cats.append("🟢 Faturável")
                if not nfat_df.empty: cats.append("🔴 Não Faturável")
                if not int_df.empty:  cats.append("🔵 Interno PRODAM")

                if not cats:
                    st.info("Sem lançamentos categorizados.")
                    continue

                sub_tabs = st.tabs(cats)
                cat_dfs  = [df for df in [fat_df, nfat_df, int_df] if not df.empty]

                for tab, df_cat in zip(sub_tabs, cat_dfs):
                    with tab:
                        st.caption(f"Total: **{fmt_h(df_cat['horas_num'].sum())}**")
                        # Tabela de lançamentos
                        tbl = df_cat[[
                            "atividade", "titulo_atividade",
                            "nome_projeto", "data", "horas_num"
                        ]].copy()
                        tbl.columns = [
                            "Atividade", "Título", "Projeto", "Data", "Horas"
                        ]
                        tbl["Horas"] = tbl["Horas"].apply(
                            lambda h: f"{h:.2f}".replace(".", ",")
                        )
                        tbl = tbl.sort_values("Data")
                        st.dataframe(
                            tbl, use_container_width=True, hide_index=True
                        )
