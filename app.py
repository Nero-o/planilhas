"""Streamlit app for the AECO monthly consolidation workflow.

Run with: streamlit run app.py
"""
import io
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from aeco import classifier, dictionary as dictmod, exporter, feedback, validate
from aeco.parsers import bs2, conta_simples, sicoob
from aeco.parsers import c6 as c6_parser


DICT_PATH = "data/dictionary.json"
MASTER_PATH = "Extrato AECO - Anual.xlsx"
FEEDBACK_PATH = "data/feedback.jsonl"

st.set_page_config(page_title="AECO Consolidador", layout="wide")
st.title("Consolidação Mensal — Extrato AECO")

# ---------- session state ----------
if "txs" not in st.session_state:
    st.session_state.txs = None
if "txs_original" not in st.session_state:
    st.session_state.txs_original = None
if "saldos" not in st.session_state:
    st.session_state.saldos = {}
@st.cache_resource
def _load_or_build_dict() -> dict | None:
    if Path(DICT_PATH).exists():
        return dictmod.load(DICT_PATH)
    if Path(MASTER_PATH).exists():
        with st.spinner(f"Construindo dicionário a partir de {MASTER_PATH}..."):
            data = dictmod.build(MASTER_PATH)
            try:
                Path(DICT_PATH).parent.mkdir(parents=True, exist_ok=True)
                dictmod.save(data, DICT_PATH)
            except OSError:
                pass  # read-only filesystem (e.g. Streamlit Cloud); keep in memory
            return data
    return None


if "dict" not in st.session_state:
    st.session_state.dict = _load_or_build_dict()

if st.session_state.dict is None:
    st.error(
        f"Dicionário não encontrado em `{DICT_PATH}` e master "
        f"`{MASTER_PATH}` também ausente. "
        f"Suba o master para gerar o dicionário, ou rode localmente: "
        f"`python scripts/build_dictionary.py '{MASTER_PATH}' {DICT_PATH}`"
    )
    st.stop()

categorias = st.session_state.dict["categories"]
descricoes = st.session_state.dict["all_descricoes"]
observacoes = st.session_state.dict["all_observacoes"]

# ---------- 1. Upload ----------
st.header("1. Upload dos extratos")
c1, c2, c3, c4 = st.columns(4)
sicoob_f = c1.file_uploader("Sicoob (xlsx)", type=["xlsx"], key="sicoob_up")
bs2_f = c2.file_uploader("BS2 (csv)", type=["csv"], key="bs2_up")
cs_f = c3.file_uploader("Conta Simples (xlsx)", type=["xlsx"], key="cs_up")
c6_f = c4.file_uploader("C6 (xlsx/csv)", type=["xlsx", "csv"], key="c6_up")
c6_password = c4.text_input(
    "Senha C6 (se necessário)",
    type="password",
    key="c6_pw",
    help="Deixe em branco se o xlsx já estiver sem senha.",
)

use_llm = st.toggle(
    "Usar LLM para casos sem regra (precisa ANTHROPIC_API_KEY)",
    value=bool(os.getenv("ANTHROPIC_API_KEY")),
)

if st.button(
    "Processar",
    type="primary",
    disabled=not any([sicoob_f, bs2_f, cs_f, c6_f]),
):
    with st.spinner("Lendo arquivos e classificando..."):
        dfs, saldos = [], {}
        if sicoob_f:
            df, s = sicoob.parse(sicoob_f); dfs.append(df); saldos["sicoob"] = s
        if bs2_f:
            df, s = bs2.parse(bs2_f); dfs.append(df); saldos["bs2"] = s
        if cs_f:
            df, s = conta_simples.parse(cs_f); dfs.append(df); saldos["conta_simples"] = s
        if c6_f:
            try:
                df, s = c6_parser.parse(c6_f, password=c6_password or None)
            except ValueError as e:
                st.error(str(e))
                st.stop()
            dfs.append(df); saldos["c6"] = s
        raw = pd.concat(dfs, ignore_index=True)
        out = classifier.classify(raw, st.session_state.dict, use_llm=use_llm)
        st.session_state.txs = out
        st.session_state.txs_original = out.copy()
        st.session_state.saldos = saldos

if st.session_state.txs is None:
    st.info("Faça upload de pelo menos um extrato e clique Processar.")
    st.stop()

txs = st.session_state.txs

# ---------- 2. Validação ----------
st.divider()
st.header("2. Validação")
val = validate.run(
    txs,
    st.session_state.saldos,
    anual_path=MASTER_PATH if Path(MASTER_PATH).exists() else None,
)
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total", val["counts"]["total"])
m2.metric("Verdes", val["counts"]["green"])
m3.metric("Amarelas", val["counts"]["yellow"])
m4.metric("Vermelhas", val["counts"]["red"], delta_color="inverse")

if val["saldo"]:
    saldo_cols = st.columns(len(val["saldo"]))
    for col, (src, s) in zip(saldo_cols, val["saldo"].items()):
        status = "OK" if s["ok"] else f"FALHOU (Δ {s['diferenca']:+.2f})"
        col.metric(f"Saldo {src}", status)

for src, suspects in val.get("saldo_warnings", {}).items():
    st.warning(
        f"**Saldo {src}**: possível estorno faltando no extrato. "
        f"{len(suspects)} lançamento(s) com valor igual à diferença do saldo "
        f"e sem reversão correspondente — o banco pode tê-los estornado sem "
        f"emitir a linha. Reexporte o extrato ou adicione o estorno manualmente."
    )
    with st.expander(f"Ver {len(suspects)} lançamento(s) suspeito(s)"):
        st.dataframe(pd.DataFrame(suspects), use_container_width=True)

if val["duplicates"]:
    with st.expander(f"Possíveis duplicatas vs master ({len(val['duplicates'])})"):
        st.dataframe(pd.DataFrame(val["duplicates"]), use_container_width=True)

# ---------- 3. Tabela editável ----------
st.divider()
st.header("3. Revisar e corrigir")

only_pendentes = st.toggle("Mostrar apenas amarelas + vermelhas", value=True)
df_view = txs
if only_pendentes:
    df_view = txs[txs.confidence.isin(["yellow", "red"])]

# Add data tooltip with sugestões
descr_help = "Sugestões: " + ", ".join(descricoes[:5]) + "..."
obs_help = "Sugestões: " + ", ".join(observacoes[:5]) + "..."

display_cols = [
    "_id", "source", "data", "tipo", "beneficiario", "valor",
    "descricao", "observacoes", "fluxo_caixa", "empresa",
    "confidence", "reasoning",
]
edited = st.data_editor(
    df_view[display_cols],
    column_config={
        "_id": None,
        "source": st.column_config.TextColumn("Fonte", disabled=True, width="small"),
        "data": st.column_config.DateColumn("Data", disabled=True, width="small"),
        "tipo": st.column_config.TextColumn("Tipo", disabled=True),
        "beneficiario": st.column_config.TextColumn("Beneficiário", disabled=True),
        "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f", disabled=True, width="small"),
        "descricao": st.column_config.TextColumn("Descrição", help=descr_help, required=True),
        "observacoes": st.column_config.TextColumn("Observações", help=obs_help, required=True),
        "fluxo_caixa": st.column_config.SelectboxColumn(
            "Fluxo Caixa", options=categorias["fluxo_caixa"], required=True
        ),
        "empresa": st.column_config.SelectboxColumn(
            "Empresa", options=categorias["empresa"], required=True
        ),
        "confidence": st.column_config.TextColumn("Conf", disabled=True, width="small"),
        "reasoning": st.column_config.TextColumn("Reasoning", disabled=True),
    },
    use_container_width=True,
    hide_index=True,
    num_rows="fixed",
    key="editor",
)

# Detect novel descriptions/observations and ask for confirmation
known_descr = set(descricoes)
known_obs = set(observacoes)
new_descr = {v for v in edited["descricao"].dropna() if v and v not in known_descr}
new_obs = {v for v in edited["observacoes"].dropna() if v and v not in known_obs}
if new_descr or new_obs:
    st.warning(
        "Valor(es) novo(s) detectado(s). Confirme se é mesmo novo (não typo)."
        + (f"\n- Descrições novas: {sorted(new_descr)}" if new_descr else "")
        + (f"\n- Observações novas: {sorted(new_obs)}" if new_obs else "")
    )
    confirm = st.button("Confirmar valores novos e atualizar")
else:
    confirm = True  # nothing to confirm

if confirm:
    # Merge edits back into the master DataFrame by _id
    for _, row in edited.iterrows():
        mask = txs["_id"] == row["_id"]
        for col in ("descricao", "observacoes", "fluxo_caixa", "empresa"):
            txs.loc[mask, col] = row[col]
        # Promote to green if all 4 fields populated
        if all(row[c] for c in ("descricao", "observacoes", "fluxo_caixa", "empresa")):
            txs.loc[mask, "confidence"] = "green"
            txs.loc[mask, "classifier"] = "manual"
    st.session_state.txs = txs

with st.expander("Pré-visualização colorida (read-only)"):
    def _row_style(r):
        color = {"green": "#d4f7d4", "yellow": "#fff3a3", "red": "#fbb"}.get(
            r["confidence"], "#ffffff"
        )
        return [f"background-color: {color}"] * len(r)

    st.dataframe(
        txs[display_cols].style.apply(_row_style, axis=1),
        use_container_width=True,
    )

# ---------- 4. Exportar ----------
st.divider()
st.header("4. Exportar")
remaining_red = int((txs["confidence"] == "red").sum())
if remaining_red > 0:
    st.warning(f"{remaining_red} linha(s) ainda em vermelho. Revise antes de baixar.")

col_a, col_b = st.columns(2)
with col_a:
    xlsx_bytes = exporter.to_xlsx(txs, st.session_state.saldos)
    st.download_button(
        "Baixar consolidação.xlsx",
        data=xlsx_bytes,
        file_name=f"consolidacao_{pd.Timestamp.now():%Y%m}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
with col_b:
    if st.button("Salvar correções para retreinar"):
        n = feedback.append_corrections(
            st.session_state.txs_original, txs, FEEDBACK_PATH
        )
        st.success(f"{n} correção(ões) gravada(s) em {FEEDBACK_PATH}")
