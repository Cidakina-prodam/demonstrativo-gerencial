"""
visao_desempenho.py
Renderiza a aba de Desempenho de Faturamento.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from processamento import calcular_desempenho_nucleo, fmt_h


def _badge_pct(pct: float) -> str:
    """Retorna emoji colorido conforme % de faturamento."""
    if pct >= 80:   return f"🟢 {pct}%"
    elif pct >= 40: return f"🟡 {pct}%"
    elif pct > 0:   return f"🟠 {pct}%"
    else:           return f"⚫ 0%"


def render_desempenho(
    colab_df: pd.DataFrame,
    lanc_df: pd.DataFrame,
    fat_map: dict,
    nucleo: str,
    periodo_ini: pd.Timestamp,
    periodo_fim: pd.Timestamp,
    status_map: dict,
    tem_posicional: bool,
):
    """Renderiza a visão de Desempenho de Faturamento."""

    if not tem_posicional:
        st.warning(
            "⚠️ **Posicional não configurado para este núcleo/mês.**\n\n"
            "Suba os arquivos do posicional para ver o faturamento."
        )
        return

    rows = calcular_desempenho_nucleo(
        colab_df, lanc_df, fat_map,
        nucleo, periodo_ini, periodo_fim, status_map,
    )

    if not rows:
        st.warning(f"Nenhum colaborador encontrado para o núcleo {nucleo}.")
        return

    # ── CARDS DE TOTAIS ───────────────────────────────────────────────────────
    tot_lanc = sum(r["lancado"]  for r in rows)
    tot_fat  = sum(r["faturado"] for r in rows)
    cobertura = round(tot_fat / tot_lanc * 100, 1) if tot_lanc > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📥 Total Lançado",  fmt_h(tot_lanc))
    c2.metric("✅ Total Faturado", fmt_h(tot_fat))
    c3.metric("📊 Cobertura",      f"{cobertura}%")
    c4.metric("❌ Não Faturado",   fmt_h(tot_lanc - tot_fat))

    st.markdown("---")

    # ── BUSCA ─────────────────────────────────────────────────────────────────
    col_busca, col_exp = st.columns([3, 1])
    with col_busca:
        busca = st.text_input("🔍 Buscar colaborador", "", key=f"busca_desemp_{nucleo}")
    with col_exp:
        expandir_todos = st.checkbox("Expandir todos", key=f"exp_desemp_{nucleo}")

    # ── TABELA POR TIPO ───────────────────────────────────────────────────────
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
            label = (
                f"**{r['nome']}** "
                f"{'· ' + r['espec'] if r['espec'] else ''} "
                f"&nbsp;|&nbsp; "
                f"Lançado: **{fmt_h(r['lancado'])}** "
                f"&nbsp;|&nbsp; "
                f"Faturado: **{fmt_h(r['faturado'])}** "
                f"&nbsp;|&nbsp; {_badge_pct(r['pct_fat'])}"
            )

            with st.expander(label, expanded=expandir_todos):
                # Métricas individuais
                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("Lançado",     fmt_h(r["lancado"]))
                mc2.metric("Faturado",    fmt_h(r["faturado"]))
                mc3.metric("Não Fat.",    fmt_h(r["nao_faturado"]))
                mc4.metric("% Contrib.",  f"{r['pct_contrib']}%")

                # Drill-down: GDPs faturáveis
                if not r["drill"]:
                    st.info("Sem lançamentos faturáveis encontrados no período.")
                    continue

                st.markdown("##### Lançamentos Faturáveis por GDP")
                for proj in r["drill"]:
                    st.caption(f"**{proj['nome']}** / {proj['cliente']}")
                    for g in proj["gdps"]:
                        icone  = "✅" if g["faturado"] else "❌"
                        status = g["status"] or "—"
                        cor_st = g["cor"]
                        st.markdown(
                            f"{icone} &nbsp; "
                            f"`GDS:{g['gds']}` `GDP:{g['gdp']}` "
                            f"&nbsp; <span style='background:{cor_st};color:white;"
                            f"padding:1px 7px;border-radius:8px;font-size:.7rem;"
                            f"font-weight:700'>{status}</span>"
                            f"&nbsp; **{fmt_h(g['horas'])}**",
                            unsafe_allow_html=True,
                        )

    st.markdown("---")

    # ── GRÁFICO DE CONTRIBUIÇÃO ───────────────────────────────────────────────
    df_fat = pd.DataFrame([
        {"Nome": r["nome"], "Faturado": r["faturado"]}
        for r in rows if r["faturado"] > 0
    ])

    if not df_fat.empty:
        st.markdown("#### 🍩 Contribuição no Faturamento")
        fig = px.pie(
            df_fat, names="Nome", values="Faturado",
            hole=0.5,
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(showlegend=False, height=420, margin=dict(t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)
