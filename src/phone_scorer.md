# Algoritmo de Scoring de Telefones (`PhoneScorer`)

## 1. Objetivo

Dado um CPF com múltiplos telefones associados, atribuir um **score
interpretável ∈ [0, 1]** a cada telefone e devolver um **ranking** —
em particular, os **k melhores telefones por CPF** (default `k=2`)
para alimentar o motor de disparos de WhatsApp.

Implementação: `src/phone_scorer.py` (classe `PhoneScorer`).

### Convenção de classificação

Ao longo do projeto adotamos duas categorias binárias — aplicáveis
tanto em nível de **telefone** quanto de **CPF**:

- **HighDelivery**: taxa de entrega (`status ∈ {delivered, read}`) ≥ **90%**.
- **HighRead**: taxa de leitura (`status == read`) ≥ **75%**.

Daí os termos *Telefone HighDelivery* / *Telefone HighRead* e
*CPF HighDelivery* / *CPF HighRead*. As regras de atualidade usadas
pelo `PhoneScorer` têm como alvo **Telefone HighRead**.

---

## 2. Entrada principal

`score(df)` e `top_k(df, k)` recebem um DataFrame enxuto com, para cada
CPF, os telefones candidatos:

| Coluna             | Tipo       | Descrição                                              |
|--------------------|------------|--------------------------------------------------------|
| `cpf`              | str        | Identificador do CPF.                                  |
| `telefone`         | str        | Telefone candidato.                                    |
| `id_sistema`       | str        | Sistema de origem do registro.                         |
| `data_atualizacao` | datetime   | Data em que o registro foi atualizado naquele sistema. |

Repetições são **esperadas e consolidadas internamente**:

- `(cpf, telefone, id_sistema)` com várias datas → mantém a **mais recente**.
- `(cpf, telefone)` em vários sistemas → escolhe o **sistema mais
  confiável** segundo o ranking de confiabilidade.

---

## 3. Fontes auxiliares

Carregadas uma única vez na construção (`PhoneScorer(...)` ou
`PhoneScorer.from_paths(...)`):

| Fonte                    | Obrigatória?  | Colunas exigidas                              |
|--------------------------|---------------|-----------------------------------------------|
| `ranking_confiabilidade` | sim           | `id_sistema`, `score`; `sistema_nome` opcional. |
| `regras_atualidade`      | sim           | `id_sistema`, `regra`, `prob_high_read`.      |
| `taxa_read`              | **opcional**  | `telefone`, `taxa_read`.                      |

### 3.1 `ranking_confiabilidade`

Resultado da análise de qualidade das fontes (notebook
`02_qualidade_fontes.ipynb`). Cada sistema recebe um **score de
confiabilidade ∈ [0, 1]** que reflete o quão confiável é aquela base
como origem de telefones, calculado como `P(Telefone HighDelivery |
sistema)`.

- **`id_sistema`** — identificador único do sistema.
- **`score`** — confiabilidade do sistema (quanto maior, melhor).
- **`sistema_nome`** *(opcional)* — nome legível; se presente, é
  propagado para a saída para facilitar a auditoria.

### 3.2 `regras_atualidade`

Gerada pelas árvores de decisão no notebook
`03_janela_atualidade.ipynb`. Cada sistema possui **2 cortes** sobre
`dias_desde_atualizacao`, e cada corte está associado à
probabilidade de **Telefone HighRead** (taxa de leitura ≥ 75%).
Essas regras transformam a idade de um registro em um score de
atualidade.

- **`id_sistema`** — mesmo domínio do ranking.
- **`regra`** — expressão textual `"dias <op> <limite>"` (ex.:
  `"dias <= 826"`). Parseada via regex; operadores suportados: `<=`,
  `<`, `>=`, `>`, `==`.
- **`prob_high_read`** — probabilidade de Telefone HighRead
  associada ao corte. Quando a regra é satisfeita, esse valor é
  usado diretamente como `score_atualidade` bruto do telefone.

### 3.3 `taxa_read` *(opcional)*

Agregado histórico de disparos de WhatsApp por telefone. Quando
fornecido, adiciona um sinal de desempenho real (o telefone já
respondeu no passado?). Se **não fornecido**, `w_read` é zerado e os
demais pesos são renormalizados — o algoritmo continua funcional.

- **`telefone`** — número do telefone (chave de junção).
- **`taxa_read`** — `total_reads / total_envios`. Quanto maior, melhor
  o histórico de engajamento.

---

## 4. Metodologia do score

### 4.1 Visão geral

O score final é uma **combinação linear ponderada** de três
componentes — escolha proposital pela total interpretabilidade (não é
caixa-preta):

```
score_final = w_sistema    * n_score_sistema
            + w_atualidade * n_score_atualidade
            + w_read       * n_score_read
```

> **Convenção de nomes:** `score_*` são os valores **brutos** (saída
> direta das fontes auxiliares). `n_score_*` são esses mesmos valores
> **após normalização min-max dentro do mesmo CPF** — ou seja, o
> prefixo `n_` indica "normalizado". A combinação linear sempre opera
> sobre os `n_score_*`, nunca sobre os brutos.

A normalização min-max por CPF é feita porque a comparação relevante é
sempre **entre os telefones de um mesmo CPF** (qual deles é o melhor
candidato), não entre CPFs distintos.

### 4.2 Componentes

**1. `score_sistema` → `n_score_sistema`**

Valor bruto: `score` do sistema escolhido (o mais confiável dentre os
que reportaram aquele `(cpf, telefone)`), vindo do
`ranking_confiabilidade`.
Normalização: min-max dentro do CPF.

**2. `score_atualidade` → `n_score_atualidade`**

Valor bruto: para cada linha, calcula-se
`dias_desde_atualizacao = data_referencia - data_atualizacao` e
confronta-se com as regras do `id_sistema` daquele telefone; a regra
satisfeita fornece `prob_high_read`, que é o `score_atualidade` bruto.
`data_referencia` é configurável (default = hoje, normalizada).
Normalização: min-max dentro do CPF.

**3. `taxa_read` → `n_score_read`**

Valor bruto: `taxa_read` por telefone (vindo da fonte opcional).
Normalização: min-max dentro do CPF.
Se a fonte **não é fornecida**, `w_read = 0` e `w_sistema` /
`w_atualidade` são **renormalizados** para somar 1.

### 4.3 Pesos

Default em `ScoreWeights`:

- `w_sistema = 0.3`
- `w_atualidade = 0.2`
- `w_read = 0.5`

### 4.4 Imputação de valores faltantes

Componentes sem valor após a normalização recebem o valor **neutro
0.5**. Casos típicos:

- sistema sem regra de atualidade aplicável;
- CPF com um único telefone (min-max degenera).

O 0.5 evita penalizar ou premiar artificialmente o telefone por falta
de sinal.

---

## 5. Uso

```python
from phone_scorer import PhoneScorer, ScoreWeights

scorer = PhoneScorer.from_paths(
    ranking_path="deliverables/ranking_confiabilidade.csv",
    regras_path="outputs/decision_trees/df_regras_atualidade.csv",
    taxa_read_path="deliverables/taxa_read_telefone.csv",  # opcional
    weights=ScoreWeights(w_sistema=0.3, w_atualidade=0.2, w_read=0.5),
)

# df_telefones: cpf, telefone, id_sistema, data_atualizacao
ranking = scorer.score(df_telefones)
top2    = scorer.top_k(df_telefones, k=2)
```

- **Com histórico de `taxa_read`:** os 3 sinais entram na combinação
  linear com os pesos originais.
- **Sem histórico:** omita `taxa_read_path` (ou passe `taxa_read=None`).
  A classe detecta a ausência e renormaliza os pesos restantes.

---

## 6. Saída

`score(...)` retorna um DataFrame ordenado por
`(cpf, score_final desc)`, com `rank` por CPF e os componentes
decompostos para auditoria.

**Identificação:** `cpf`, `telefone`, `rank`, `id_sistema`,
`sistema_nome` (se disponível), `data_atualizacao`,
`dias_desde_atualizacao`, `n_sistemas`.

**Score final:** `score_final`.

**Componentes brutos:** `score_sistema`, `score_atualidade`,
`taxa_read`.

**Componentes normalizados (min-max por CPF):** `n_score_sistema`,
`n_score_atualidade`, `n_score_read`.

**Pesos efetivamente aplicados** (já renormalizados conforme
`use_read`): `peso_sistema`, `peso_atualidade`, `peso_read`. Incluídos
em cada linha para facilitar reproduzir o cálculo manualmente e
auditar decisões.
