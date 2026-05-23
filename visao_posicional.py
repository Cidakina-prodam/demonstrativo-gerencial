"""
visao_posicional.py
Renderiza a aba Posicional.
"""

import streamlit as st
import pandas as pd
from processamento import fmt_h, STATUS_CORES


def _badge_status(status: str, cor: str) -> str:
    if not status:
        return ""
    return (
        f'<span style="background:{cor};color:white;padding:1px 8px;'
        f'border-radius:10px;font-size:.65rem;font-weight:700;'
        f'white-space:nowrap">{status}</span>'
    )


def render_posicional(pos_data: dict):
    """
    Renderiza a visão posicional.
    pos_data: resultado de processamento.processar_posicional()
    """

    if not pos_data or not pos_data.get("secretarias"):
        st.info("Posicional ainda não configurado para este núcleo/mês.")
        return

    # ── CALCULAR TOTAIS ───────────────────────────────────────────────────────
    tot_pos = 0.0
    tot_div = 0
    for sec in pos_data["secretarias"]:
        for os_ in sec["oss"]:
            for proj in os_["projetos"]:
                for dem in proj["demandas"]:
                    tot_pos += dem["horas"]  # horas do PDF (mestre)
                    if dem.get("atividades_faltando"):
                        tot_div += 1

    # Horas lançadas = horas posicional (PDF é o mestre)
    # Se há divergências, mostrar o que foi lançado no CSV
    tot_lanc = tot_pos
    cobertura = 100 if tot_div == 0 else round(tot_lanc / tot_pos * 100, 1)

    # ── CARDS ─────────────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📄 Horas Posicional", fmt_h(tot_pos))
    c2.metric("⏱ Horas Lançadas",   fmt_h(tot_pos if tot_div == 0 else tot_lanc))
    c3.metric("⚠️ Divergências",     "✔ 0" if tot_div == 0 else str(tot_div))
    c4.metric("📊 Cobertura",        f"{cobertura}%")

    st.markdown("---")

    # ── CONTROLES ─────────────────────────────────────────────────────────────
    col_busca, col_b1, col_b2, col_b3 = st.columns([3, 1, 1, 1])
    with col_busca:
        busca = st.text_input("🔍 Buscar demanda", "", key="busca_pos")
    with col_b1:
        expandir = st.button("Expandir tudo", key="exp_pos")
    with col_b2:
        recolher = st.button("Recolher tudo", key="rec_pos")
    with col_b3:
        so_div   = st.toggle("Só divergências", key="div_pos")

    # Controle de estado de expansão
    if "pos_expanded" not in st.session_state:
        st.session_state.pos_expanded = {}
    if expandir:
        st.session_state.pos_expanded = {"_all": True}
    if recolher:
        st.session_state.pos_expanded = {"_all": False}

    def is_expanded(key):
        if "_all" in st.session_state.pos_expanded:
            return st.session_state.pos_expanded["_all"]
        return st.session_state.pos_expanded.get(key, False)

    # ── RENDERIZAR HIERARQUIA ─────────────────────────────────────────────────
    for sec in pos_data["secretarias"]:
        st.markdown(
            f'<div style="background:#1F4E79;color:white;padding:10px 16px;'
            f'border-radius:8px;font-weight:700;margin:16px 0 10px">'
            f'▶ {sec["desc"]} &nbsp;&nbsp; <span style="font-size:.85rem;'
            f'font-weight:400">{fmt_h(sec["horas"])}</span></div>',
            unsafe_allow_html=True,
        )

        for os_ in sec["oss"]:
            st.markdown(
                f'<div style="background:#2E75B6;color:white;padding:6px 14px;'
                f'border-radius:6px;font-size:.82rem;font-weight:700;'
                f'margin:8px 0 6px;display:inline-block">'
                f'■ {os_["desc"]}</div>',
                unsafe_allow_html=True,
            )

            for proj in os_["projetos"]:
                st.markdown(
                    f'<div style="background:#D6E4F0;padding:6px 14px;'
                    f'border-radius:6px;font-weight:600;font-size:.84rem;'
                    f'margin:6px 0 4px;display:flex;justify-content:space-between">'
                    f'<span>{proj["desc"]}</span>'
                    f'<span style="font-family:monospace">{fmt_h(proj["horas"])}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                for dem in proj["demandas"]:
                    faltando  = dem.get("atividades_faltando", [])
                    tem_falta = bool(faltando)

                    # Filtro de divergências
                    if so_div and not tem_falta:
                        continue

                    # Filtro de busca
                    if busca and busca.lower() not in dem["desc"].lower():
                        continue

                    borda = "#C00000" if tem_falta else "#BDC8D4"
                    bg    = "#FDE8D8" if tem_falta else "#F5F7FA"

                    with st.container():
                        st.markdown(
                            f'<div style="border-left:4px solid {borda};'
                            f'background:{bg};padding:8px 14px;border-radius:6px;'
                            f'margin:4px 0;display:flex;align-items:center;gap:8px">'
                            f'<span style="flex:1;font-size:.85rem;font-weight:600">'
                            f'{dem["desc"]}</span>'
                            f'{_badge_status(dem["status"], dem["status_cor"])}'
                            + (f'<span style="background:#C00000;color:white;'
                               f'padding:1px 7px;border-radius:10px;font-size:.62rem;'
                               f'font-weight:700">⚠ {len(faltando)} faltando</span>'
                               if tem_falta else "")
                            + f'<span style="font-family:monospace;font-size:.82rem;'
                            f'margin-left:12px;white-space:nowrap">'
                            f'{fmt_h(dem["horas"])}</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                        # Atividades faltando
                        if faltando:
                            st.markdown(
                                "**❌ Atividades no PDF sem lançamento no CSV:**"
                            )
                            for atv in faltando:
                                st.markdown(
                                    f'<div style="background:#fde8d8;'
                                    f'border-left:3px solid #C00000;'
                                    f'padding:4px 10px;border-radius:4px;'
                                    f'font-size:.78rem;color:#C00000;margin-bottom:3px">'
                                    f'[{atv}] Não encontrado no CSV</div>',
                                    unsafe_allow_html=True,
                                )

                        # Colaboradores
                        exp_key = f"pos_{dem['gdp_id']}"
                        if dem["colaboradores"]:
                            with st.expander(
                                f"👥 {len(dem['colaboradores'])} colaborador(es)",
                                expanded=is_expanded(exp_key),
                            ):
                                for col in dem["colaboradores"]:
                                    st.markdown(
                                        f"**{col['nome'].replace('Colaborador:','').strip()}** "
                                        f"— {fmt_h(col['horas'])}"
                                    )
                                    if col["lancamentos"]:
                                        tbl = pd.DataFrame(col["lancamentos"])
                                        tbl = tbl[["atividade","data","horas","desc"]]
                                        tbl.columns = ["Atividade","Data","Horas","Título"]
                                        tbl["Horas"] = tbl["Horas"].apply(
                                            lambda h: f"{h:.2f}".replace(".", ",")
                                        )
                                        st.dataframe(
                                            tbl, use_container_width=True,
                                            hide_index=True,
                                        )
                        else:
                            st.caption("Sem lançamentos encontrados no CSV.")
