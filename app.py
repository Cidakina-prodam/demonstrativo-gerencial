"""
app.py  —  Demonstrativo Gerencial PRODAM
Página principal: sidebar com uploads + roteamento para as 3 visões.
"""

import streamlit as st
import pandas as pd

from processamento import (
    carregar_csv,
    carregar_colaboradores,
    carregar_status,
    processar_posicional,
    construir_fat_map,
    periodo_de,
    PERIODOS,
)
from visao_lancamentos import render_lancamentos
from visao_desempenho  import render_desempenho
from visao_posicional  import render_posicional

# ── ESTRUTURA DO POSICIONAL (ABRIL 2026) ──────────────────────────────────────
# Esta seção deve ser atualizada mês a mês conforme os novos PDFs.
# Futuramente será lida via upload de PDF automaticamente.

POSICIONAL_ABR2026 = {
    "NSS1": {
        "secretarias": [{
            "desc": "SMS — TC 107/2025/SMS-1/CONTRATOS - Sustentação de TIC",
            "horas": 5123.42,
            "oss": [
                {
                    "desc": "GDS-1 - Operação Assistida",
                    "projetos": [{
                        "cod": "SH0712", "nome": "ATENDIMENTO E SUPORTE A SMS",
                        "demandas": [
                            {"gdp":"189238","gds":"189238","titulo":"Operação Assistida TC 107/2025 - SMS","horas":1000.0,"atividades":[]},
                        ],
                    }],
                },
                {
                    "desc": "NSS-1 - Manutenção e Melhorias",
                    "projetos": [{
                        "cod": "SH0768", "nome": "SIGA SAÚDE",
                        "demandas": [
                            {"gdp":"157558","gds":"20864","titulo":"0251986: [Exportador] Extração de relatório Thrift e-SUS AB","horas":365.5,"atividades":[]},
                            {"gdp":"166266","gds":"23718","titulo":"0262939: Sistema apresenta Motivo de Não Atendido em Branco","horas":56.0,"atividades":["488049"]},
                            {"gdp":"170553","gds":"24597","titulo":"0266353: Botão Limpar com função de consultar a pesquisa","horas":53.0,"atividades":[]},
                            {"gdp":"170703","gds":"24696","titulo":"0266521: Mensagem indevida ao atualizar CNS - BUG","horas":64.5,"atividades":[]},
                            {"gdp":"170715","gds":"24704","titulo":"0266775: Ajuste no WebSerice Pessoa para indicar CNS máster","horas":270.83,"atividades":[]},
                            {"gdp":"173447","gds":"24829","titulo":"0263692: Criação de rotina automatizada - Painel de BI PICS","horas":24.0,"atividades":[]},
                            {"gdp":"173504","gds":"25205","titulo":"0268748: Automatização dos limites de execução e solicitação","horas":1137.4,"atividades":[]},
                            {"gdp":"173881","gds":"25471","titulo":"0269783: Botão Resumo de vagas não funciona","horas":40.0,"atividades":[]},
                            {"gdp":"173954","gds":"25528","titulo":"0269810: Criação de rotina automatizada - Painel Atenção Básica","horas":13.5,"atividades":[]},
                            {"gdp":"173955","gds":"25529","titulo":"0269080: Criação de rotina automatizada - Painel Atenção Especializada","horas":20.5,"atividades":[]},
                            {"gdp":"177418","gds":"26506","titulo":"0273477: Disponibilização dos serviços do Agenda Fácil","horas":522.0,"atividades":[]},
                            {"gdp":"177766","gds":"26745","titulo":"0269951: Troca de dados do paciente ao entrar no Agenda Fácil","horas":42.0,"atividades":[]},
                            {"gdp":"177990","gds":"26873","titulo":"Criação de rotina automatizada - SICAP","horas":20.0,"atividades":[]},
                            {"gdp":"177991","gds":"26819","titulo":"0273716: Repositório SMS - Carga completa dos registros SIGA","horas":18.0,"atividades":[]},
                            {"gdp":"177992","gds":"26869","titulo":"0274468: Atendimento no Registro Reduzido apresentando erro","horas":112.0,"atividades":[]},
                            {"gdp":"178068","gds":"26910","titulo":"0274616: Criação relatório - Posição Fila de espera","horas":58.0,"atividades":[]},
                            {"gdp":"178073","gds":"26915","titulo":"0138619: Criar campo indicação/motivo de cada vacina especial","horas":146.0,"atividades":[]},
                            {"gdp":"178150","gds":"26978","titulo":"0274871: Replicação do WebService de agendamento com CNES Solicitante","horas":98.15,"atividades":[]},
                            {"gdp":"178187","gds":"26989","titulo":"0249859: Erro ao realizar a atualização do cadastro de usuário","horas":46.0,"atividades":[]},
                            {"gdp":"186419","gds":"29228","titulo":"0282426: Inserir bloqueio no Botão Gravar da FPO da APAC","horas":50.01,"atividades":[]},
                        ],
                    }],
                },
                {
                    "desc": "NSS-2 - Manutenção e Melhorias",
                    "projetos": [
                        {
                            "cod":"SH0743","nome":"GSS - GESTAO DE SISTEMAS DA SAUDE",
                            "demandas": [
                                {"gdp":"162192","gds":"22548","titulo":"0258658: SOA BNAFAR - Reprocessamento dos registros com erro genérico","horas":351.5,"atividades":[]},
                                {"gdp":"178592","gds":"27257","titulo":"0275878: Envio de dados para a API OBM","horas":56.0,"atividades":["489163"]},
                                {"gdp":"188248","gds":"29793","titulo":"0284529: Registrar o valor do item a cada movimentação","horas":152.0,"atividades":["487283","488417","488419"]},
                            ],
                        },
                        {
                            "cod":"SH0768","nome":"SIGA SAÚDE",
                            "demandas": [
                                {"gdp":"189175","gds":"30403","titulo":"0286384: Extração de relatório de movimentos","horas":8.0,"atividades":[]},
                            ],
                        },
                    ],
                },
                {
                    "desc": "NSS-3 - Manutenção e Melhorias",
                    "projetos": [{
                        "cod":"SH0835","nome":"WEBSAASS - SISTEMA DE ACOMPANHAMENTO E AVALIAÇÃO DE SERVIÇOS DE SAÚDE",
                        "demandas": [
                            {"gdp":"181045","gds":"28263","titulo":"0279240: Erro inconsistencias Websaass","horas":18.0,"atividades":["489423"]},
                            {"gdp":"181060","gds":"28260","titulo":"0279235: Falha ao tentar anexar PDF no WebSaass","horas":3.0,"atividades":["488635"]},
                            {"gdp":"181195","gds":"28366","titulo":"0279547: Balancete com erro no cálculo de saldos de Receitas","horas":192.0,"atividades":[]},
                            {"gdp":"188884","gds":"188884","titulo":"[WEBSAASS] Suporte e manutenção","horas":24.0,"atividades":["488237","488637","488692"]},
                            {"gdp":"189050","gds":"189050","titulo":"0279238: Erro de duplicidade - UBS Jardim Thomas","horas":30.0,"atividades":["487674","487675","488591"]},
                            {"gdp":"189073","gds":"189073","titulo":"[WEBSAASS] Atualização para o Windows Server 2022","horas":43.13,"atividades":["487731","487734","488238"]},
                            {"gdp":"189539","gds":"189539","titulo":"[WEBSAAS] Balancete - problema no cálculo de saldos","horas":63.6,"atividades":["488670","488671","488672"]},
                            {"gdp":"189563","gds":"30664","titulo":"0287066: Rotina mensal de extração automatizada de unidades x OSS","horas":22.8,"atividades":["488779"]},
                            {"gdp":"189854","gds":"189854","titulo":"Alteração na estrutura do CNPJ","horas":2.0,"atividades":["489410"]},
                        ],
                    }],
                },
            ],
        }],
    },
    "NSS3": {
        "secretarias": [
            {
                "desc": "SEME — TC 025/SEME/2024 - TA01 - Sustentação de TIC",
                "horas": 264.0,
                "oss": [{
                    "desc": "Sem O.S.",
                    "projetos": [
                        {
                            "cod":"SJ2301","nome":"SIGPEC - SISTEMA DE GESTÃO DE PESSOAS E COMPETÊNCIA",
                            "demandas": [
                                {"gdp":"180022","gds":"27560","titulo":"Folha de Pagamento Bolsa Atleta","horas":2.0,"atividades":["409416"]},
                            ],
                        },
                        {
                            "cod":"SS0404","nome":"Joga SP",
                            "demandas": [
                                {"gdp":"180048","gds":"27581","titulo":"Adaptação do Joga SP no atendimento do Evento - Vem Dançar","horas":41.0,
                                 "atividades":["409586","411576","464348","487778","488863","488991","489009","489067","489216","489270"]},
                                {"gdp":"180748","gds":"28054","titulo":"retirar obrigatoriedade do RG em todos os cadastros","horas":20.0,"atividades":["487779","488854","488940","489046"]},
                                {"gdp":"181388","gds":"28475","titulo":"NOVAS Demandas de manutenção","horas":33.0,"atividades":["486595","486596"]},
                                {"gdp":"188915","gds":"188915","titulo":"[SEME] Aplicação JOGA SP - migração de servidor","horas":40.0,"atividades":["487437","488188"]},
                                {"gdp":"189364","gds":"30507","titulo":"adicionar filtro de procura para o telefone de cadastro","horas":22.0,"atividades":["489223"]},
                                {"gdp":"189366","gds":"30336","titulo":"Migração do servidor JOGASP","horas":25.0,"atividades":["488751"]},
                                {"gdp":"189581","gds":"30659","titulo":"alteração dos logos da prefeitura no portal/internet","horas":28.0,"atividades":["489239","489271"]},
                                {"gdp":"189746","gds":"30785","titulo":"Autorização para exclusão de um registro no banco de dados","horas":8.0,"atividades":["489475"]},
                            ],
                        },
                        {
                            "cod":"SS0405","nome":"SIGA SEME-SUPERV.ATIVIDADES ESPORTIVAS REC.E LAZER",
                            "demandas": [
                                {"gdp":"180770","gds":"28067","titulo":"Desenvolvimento do MEU ESPORTE SP","horas":45.0,"atividades":["411041","412316"]},
                            ],
                        },
                    ],
                }],
            },
            {
                "desc": "SMDET — TC 024/2023/SMDET - TA 02/2025 - Sustentação de TIC",
                "horas": 67.0,
                "oss": [{
                    "desc": "Sem O.S.",
                    "projetos": [{
                        "cod":"PS0101","nome":"BANCO DE DADOS DO CIDADÃO - BDC",
                        "demandas": [
                            {"gdp":"188909","gds":"188909","titulo":"[SMDET] ENC: NAS","horas":4.0,"atividades":["487428"]},
                            {"gdp":"189116","gds":"189116","titulo":"[POT/BT] ADS - Jan26 (1) 1.csv","horas":6.0,"atividades":["487798"]},
                            {"gdp":"189357","gds":"189357","titulo":"[SMDET] RES: Extração dos Beneficiários","horas":8.0,"atividades":["488319"]},
                            {"gdp":"189422","gds":"30575","titulo":"Lote de pagamento POT Oportunidades não esta rodando no NAS","horas":4.0,"atividades":["488496"]},
                            {"gdp":"189464","gds":"189464","titulo":"[SMDET] Migração de servidor - levantamento","horas":1.0,"atividades":["488674"]},
                            {"gdp":"189542","gds":"189542","titulo":"[SMDET] ABAE ATT.csv","horas":4.0,"atividades":["488675"]},
                            {"gdp":"189568","gds":"189568","titulo":"[SMDET] problema no processamento de arquivo de pagamento do BT","horas":24.0,"atividades":["488727"]},
                            {"gdp":"189569","gds":"189569","titulo":"[SMDET] alteração da rotina de processamento de arquivo de pagamento","horas":16.0,"atividades":["488728"]},
                        ],
                    }],
                }],
            },
        ],
    },
}

# ── CONFIGURAÇÃO DA PÁGINA ────────────────────────────────────────────────────
st.set_page_config(
    page_title="Demonstrativo Gerencial",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📂 Arquivos de Entrada")
    st.caption("Suba os arquivos do mês de referência")

    csv_files = st.file_uploader(
        "📄 CSV de Lançamentos",
        type=["csv"],
        accept_multiple_files=True,
        help="Um ou mais arquivos CSV (GDS1, GDE, FE)",
    )

    colab_file = st.file_uploader(
        "👥 Colaboradores (xlsx)",
        type=["xlsx"],
        help="Arquivo de colaboradores do mês",
    )

    status_file = st.file_uploader(
        "📊 Status das GDPs (csv) — opcional",
        type=["csv"],
        help="Relatório de faturamento com status das GDPs",
    )

    st.markdown("---")
    st.markdown("### ⚙️ Configuração")

    mes_ref = st.selectbox(
        "Mês de Referência",
        list(PERIODOS.keys()),
        index=3,  # Abril 2026 como padrão
    )

    nucleo_sel = st.selectbox(
        "Núcleo",
        ["NSS1", "NSS2", "NSS3", "NC"],
    )

    st.markdown("---")
    st.caption("**Período de apuração:**")
    ini, fim = [pd.Timestamp(d) for d in PERIODOS[mes_ref]]
    st.caption(f"📌 {ini.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}")

# ── TÍTULO ────────────────────────────────────────────────────────────────────
st.title("📊 Demonstrativo Gerencial")
st.caption(f"Núcleo **{nucleo_sel}** · {mes_ref}")

# ── VERIFICAR UPLOADS MÍNIMOS ─────────────────────────────────────────────────
if not csv_files:
    st.info(
        "👈 **Para começar:**\n\n"
        "1. Suba o(s) arquivo(s) CSV de lançamentos\n"
        "2. Suba o arquivo de colaboradores (xlsx)\n"
        "3. Opcionalmente suba o CSV de status das GDPs"
    )
    st.stop()

# ── CARREGAR DADOS ─────────────────────────────────────────────────────────────
with st.spinner("⏳ Carregando lançamentos..."):
    lanc_df = carregar_csv(csv_files)

colab_df = None
if colab_file:
    with st.spinner("⏳ Carregando colaboradores..."):
        colab_df = carregar_colaboradores(colab_file)

status_map = {}
if status_file:
    with st.spinner("⏳ Carregando status das GDPs..."):
        status_map = carregar_status(status_file)

# ── POSICIONAL: PROCESSAR SE DISPONÍVEL ──────────────────────────────────────
pos_data  = {}
fat_map   = {}
tem_pos   = False

pos_estrutura = POSICIONAL_ABR2026.get(nucleo_sel, {})
if pos_estrutura and mes_ref == "Abril 2026":
    tem_pos = True
    with st.spinner("⏳ Cruzando posicional com CSV..."):
        pos_data = processar_posicional(
            pos_estrutura, lanc_df, ini, fim, status_map
        )
        # fat_map: rf → total horas faturadas (para Desempenho)
        fat_map = construir_fat_map(pos_data)

# ── ABAS ──────────────────────────────────────────────────────────────────────
tabs = st.tabs(["📄 Posicional", "📋 Lançamentos", "🎯 Desempenho de Faturamento"])

with tabs[0]:
    if not tem_pos:
        st.info(
            f"Posicional não disponível para **{nucleo_sel}** em **{mes_ref}**.\n\n"
            "Os posicionais configurados são: NSS1 e NSS3 — Abril 2026."
        )
    else:
        render_posicional(pos_data)

with tabs[1]:
    if colab_df is None:
        st.warning("Suba o arquivo de colaboradores para ver esta visão.")
    else:
        render_lancamentos(colab_df, lanc_df, nucleo_sel, ini, fim)

with tabs[2]:
    if colab_df is None:
        st.warning("Suba o arquivo de colaboradores para ver esta visão.")
    else:
        render_desempenho(
            colab_df, lanc_df, fat_map,
            nucleo_sel, ini, fim, status_map, tem_pos,
        )
