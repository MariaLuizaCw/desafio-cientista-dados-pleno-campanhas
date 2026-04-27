"""Algoritmo de scoring de telefones por CPF.

Implementa a classe :class:`PhoneScorer`, que combina três sinais
interpretáveis para produzir um score ∈ [0, 1] por telefone e retornar
os ``k`` melhores telefones de cada CPF:

1. **Confiabilidade do sistema de origem** — tabela
   ``ranking_confiabilidade.csv`` (chave: ``id_sistema``).
2. **Atualidade do telefone** — regras por sistema em
   ``df_regras_atualidade.csv`` (2 cortes por sistema, já associadas a uma
   ``prob_alta_perf``).
3. **Taxa de leitura histórica** — opcional. Quando disponível, é
   consumida de ``taxa_read_telefone.csv`` (agregado por telefone).

**Entrada principal do algoritmo (não recebe mais o dataset bruto de
aparições nem de disparos):** um DataFrame enxuto com, para cada CPF, os
telefones associados, o ``id_sistema`` em que apareceram e a
``data_atualizacao`` correspondente. Repetições são esperadas e
consolidadas internamente:

- ``(cpf, telefone, id_sistema)`` com várias datas → mantém a **mais recente**;
- ``(cpf, telefone)`` em vários sistemas → escolhe o **mais confiável** segundo
  o ranking de confiabilidade.

O score final é uma **combinação linear ponderada** dos três sinais
(todos normalizados em [0, 1]). A escolha linear preserva a
interpretabilidade: cada componente do score pode ser inspecionada
individualmente no DataFrame de saída.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd


_REGRA_RE = re.compile(r"\s*dias\s*(<=|<|>=|>|==)\s*(-?\d+(?:\.\d+)?)\s*")

_OPS = {
    "<=": lambda s, v: s <= v,
    "<":  lambda s, v: s < v,
    ">=": lambda s, v: s >= v,
    ">":  lambda s, v: s > v,
    "==": lambda s, v: s == v,
}


def _parse_regra(regra: str) -> tuple[str, float]:
    """Converte ``"dias <= 826"`` em ``("<=", 826.0)``."""
    m = _REGRA_RE.fullmatch(regra)
    if not m:
        raise ValueError(f"Regra de atualidade inválida: {regra!r}")
    return m.group(1), float(m.group(2))


_REQUIRED_ENTRADA = ["cpf", "telefone", "id_sistema", "data_atualizacao"]


@dataclass
class ScoreWeights:
    """Pesos da combinação linear. Renormalizados para somar 1; se
    ``use_read=False``, ``w_read`` é descartado."""

    w_sistema: float = 0.3
    w_atualidade: float = 0.2
    w_read: float = 0.5

    def normalized(self, use_read: bool) -> dict[str, float]:
        pesos = {
            "sistema": self.w_sistema,
            "atualidade": self.w_atualidade,
            "read": self.w_read if use_read else 0.0,
        }
        total = sum(pesos.values())
        if total <= 0:
            raise ValueError("Pesos devem somar valor positivo.")
        return {k: v / total for k, v in pesos.items()}


@dataclass
class PhoneScorer:
    """Atribui score interpretável a cada telefone de um CPF.

    Fontes auxiliares (colunas exigidas):
      - ``ranking_confiabilidade``: ``id_sistema``, ``score`` (e opcionalmente ``sistema_nome``).
      - ``regras_atualidade``: ``id_sistema``, ``regra`` (ex.: ``"dias <= 826"``), ``prob_alta_perf``.
      - ``taxa_read`` (opcional): ``telefone``, ``taxa_read``.

    Entrada de ``score``/``top_k``: DataFrame com ``cpf``, ``telefone``,
    ``id_sistema``, ``data_atualizacao``. Repetições são consolidadas:
    mantém a data mais recente por ``(cpf, telefone, id_sistema)`` e o
    sistema mais confiável por ``(cpf, telefone)``.
    """

    ranking_confiabilidade: pd.DataFrame
    regras_atualidade: pd.DataFrame
    taxa_read: pd.DataFrame | None = None
    weights: ScoreWeights = field(default_factory=ScoreWeights)
    data_referencia: pd.Timestamp | None = None

    def __post_init__(self) -> None:
        self.data_referencia = pd.Timestamp(
            self.data_referencia or pd.Timestamp.today().normalize()
        )

        r = self.ranking_confiabilidade.rename(columns={"score": "score_sistema"}).copy()
        r["id_sistema"] = r["id_sistema"].astype(str)
        keep = ["id_sistema", "score_sistema"] + (
            ["sistema_nome"] if "sistema_nome" in r.columns else []
        )
        self._ranking = r[keep].drop_duplicates("id_sistema")

        g = self.regras_atualidade.copy()
        g["id_sistema"] = g["id_sistema"].astype(str)
        parsed = g["regra"].map(_parse_regra)
        g["operador"] = parsed.str[0]
        g["limite"] = parsed.str[1].astype(float)
        self._regras = g[["id_sistema", "operador", "limite", "prob_alta_perf"]]

        if self.taxa_read is not None:
            t = self.taxa_read[["telefone", "taxa_read"]].copy()
            t["telefone"] = t["telefone"].astype(str)
            self._taxa_read = t
        else:
            self._taxa_read = None

    # ---- entrada principal -------------------------------------------------

    @staticmethod
    def _normaliza_entrada(df: pd.DataFrame) -> pd.DataFrame:
        missing = set(_REQUIRED_ENTRADA) - set(df.columns)
        if missing:
            raise ValueError(f"Entrada faltando colunas: {sorted(missing)}")
        out = df[_REQUIRED_ENTRADA].copy()
        for c in ("cpf", "telefone", "id_sistema"):
            out[c] = out[c].astype(str)
        out["data_atualizacao"] = pd.to_datetime(out["data_atualizacao"], errors="coerce")
        return out

    def _consolida_repeticoes(self, df: pd.DataFrame) -> pd.DataFrame:
        # data mais recente por (cpf, telefone, id_sistema)
        df = (
            df.sort_values("data_atualizacao", na_position="first")
            .groupby(["cpf", "telefone", "id_sistema"], as_index=False)
            .tail(1)
            .merge(self._ranking, on="id_sistema", how="left")
        )
        # sistema mais confiável por (cpf, telefone)
        df = df.sort_values(
            ["score_sistema", "id_sistema"], ascending=[False, True], na_position="last"
        )
        n_sistemas = df.groupby(["cpf", "telefone"])["id_sistema"].transform("nunique")
        out = df.groupby(["cpf", "telefone"], as_index=False).head(1).copy()
        out["n_sistemas"] = n_sistemas.loc[out.index].values
        return out

    # ---- cálculo do score --------------------------------------------------

    def _score_atualidade_vec(self, ids: pd.Series, dias: pd.Series) -> pd.Series:
        """Versão vetorizada: para cada linha de entrada, casa com a regra
        do sistema cujo operador/limite é satisfeito pela contagem de dias."""
        base = pd.DataFrame({"id_sistema": ids.values, "dias": dias.values})
        base["_k"] = np.arange(len(base))
        m = base.merge(self._regras, on="id_sistema", how="left")
        cond = pd.Series(False, index=m.index)
        for op, fn in _OPS.items():
            mask = m["operador"] == op
            if mask.any():
                cond.loc[mask] = fn(m.loc[mask, "dias"], m.loc[mask, "limite"]).fillna(False)
        hits = m[cond].drop_duplicates("_k").set_index("_k")["prob_alta_perf"]
        return hits.reindex(range(len(base))).to_numpy()

    @staticmethod
    def _minmax(s: pd.Series) -> pd.Series:
        vmin, vmax = s.min(skipna=True), s.max(skipna=True)
        if pd.isna(vmin) or vmax == vmin:
            return pd.Series(np.where(s.isna(), np.nan, 0.5), index=s.index)
        return (s - vmin) / (vmax - vmin)

    def score(self, df_telefones: pd.DataFrame) -> pd.DataFrame:
        """Score por telefone. Retorna DataFrame ordenado por
        ``(cpf, score_final desc)`` com componentes decompostos."""
        df = self._normaliza_entrada(df_telefones)
        if df.empty:
            return df.assign(score_final=[], rank=[])

        base = self._consolida_repeticoes(df)
        base["dias_desde_atualizacao"] = (
            self.data_referencia - base["data_atualizacao"]
        ).dt.days
        base["score_atualidade"] = self._score_atualidade_vec(
            base["id_sistema"], base["dias_desde_atualizacao"]
        )

        use_read = self._taxa_read is not None
        if use_read:
            base = base.merge(self._taxa_read, on="telefone", how="left")
        else:
            base["taxa_read"] = np.nan

        # normalização min-max por CPF
        grp = base.groupby("cpf", group_keys=False)
        base["n_score_sistema"] = grp["score_sistema"].transform(self._minmax)
        base["n_score_atualidade"] = grp["score_atualidade"].transform(self._minmax)
        base["n_score_read"] = (
            grp["taxa_read"].transform(self._minmax) if use_read else np.nan
        )
        for col in ("n_score_sistema", "n_score_atualidade", "n_score_read"):
            base[col] = base[col].fillna(0.5)

        pesos = self.weights.normalized(use_read)
        base["score_final"] = (
            pesos["sistema"] * base["n_score_sistema"]
            + pesos["atualidade"] * base["n_score_atualidade"]
            + pesos["read"] * base["n_score_read"]
        )
        base = base.sort_values(["cpf", "score_final"], ascending=[True, False])
        base["rank"] = base.groupby("cpf").cumcount() + 1
        for k, v in pesos.items():
            base[f"peso_{k}"] = v

        front = ["cpf", "telefone", "rank", "score_final", "id_sistema"]
        if "sistema_nome" in base.columns:
            front.append("sistema_nome")
        front += [
            "score_sistema", "score_atualidade", "taxa_read",
            "n_score_sistema", "n_score_atualidade", "n_score_read",
            "data_atualizacao", "dias_desde_atualizacao", "n_sistemas",
            "peso_sistema", "peso_atualidade", "peso_read",
        ]
        cols = [c for c in front if c in base.columns]
        cols += [c for c in base.columns if c not in cols]
        return base[cols].reset_index(drop=True)

    def top_k(self, df_telefones: pd.DataFrame, k: int = 2) -> pd.DataFrame:
        """Retorna os ``k`` melhores telefones por CPF."""
        df = self.score(df_telefones)
        return df[df["rank"] <= k].reset_index(drop=True)

    @classmethod
    def from_paths(
        cls,
        ranking_path: str | Path,
        regras_path: str | Path,
        taxa_read_path: str | Path | None = None,
        **kwargs,
    ) -> "PhoneScorer":
        """Instancia a classe a partir dos caminhos das fontes auxiliares."""
        return cls(
            ranking_confiabilidade=_read_table(ranking_path),
            regras_atualidade=_read_table(regras_path),
            taxa_read=_read_table(taxa_read_path) if taxa_read_path else None,
            **kwargs,
        )


def _read_table(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    return pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)
