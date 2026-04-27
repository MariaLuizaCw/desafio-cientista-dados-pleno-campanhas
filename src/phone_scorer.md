
# Algoritmo de Scoring de Telefones (`PhoneScorer`)

## 1. Objetivo

Dado um CPF que possui múltiplos telefones associados, atribuir um **score
interpretável ∈ [0, 1]** a cada telefone e devolver um **ranking** — em
particular, os **k melhores telefones por CPF** (default `k=2`) para
alimentar o motor de disparos de WhatsApp.

Implementação: `src/phone_scorer.py` (classe `PhoneScorer`).

## 2. Entrada principal


O método `score(df)` / `top_k(df, k)` recebe um DataFrame enxuto com, para
cada CPF, os telefones associados:

| Coluna | Tipo | Descrição |
|---|---|---|
| `cpf` | str | Identificador do CPF. |
| `telefone` | str | Telefone candidato. |
| `id_sistema` | str | Sistema de origem do registro. |
| `data_atualizacao` | datetime | Data em que o registro foi atualizado naquele sistema. |

Repetições são **esperadas e consolidadas internamente**:

- `(cpf, telefone, id_sistema)` com várias datas → mantém a **mais recente**.
- `(cpf, telefone)` em vários sistemas → escolhe o **sistema mais confiável**
  segundo o ranking.

## 3. Fontes auxiliares

Carregadas uma única vez na construção (`PhoneScorer(...)` ou
`PhoneScorer.from_paths(...)`):

| Fonte | Obrigatória? | Colunas exigidas |
|---|---|---|
| `ranking_confiabilidade` | sim | `id_sistema`, `score`; `sistema_nome` opcional. |
| `regras_atualidade` | sim | `id_sistema`, `regra`, `prob_alta_perf`. |
| `taxa_read` | **opcional** | `telefone`, `taxa_read`. |

### 3.1 `ranking_confiabilidade`

Resultado da análise de qualidade das fontes de dados (notebook
`02_qualidade_fontes.ipynb`). Cada sistema recebe um **score de
confiabilidade ∈ [0, 1]** que reflete o quão confiável é aquela base como
origem de telefones. 

- **`id_sistema`** — identificador único do sistema de origem.
- **`score`** — confiabilidade do sistema (quanto maior, melhor).
- **`sistema_nome`** *(opcional)* — nome legível do sistema; se presente,
  é propagado para a saída para facilitar a auditoria.

### 3.2 `regras_atualidade`

Gerada pelas árvores de decisão no notebook `03_janela_atualidade.ipynb`.
Cada sistema possui **2 cortes** sobre `dias_desde_atualizacao`, e cada
corte está associado a uma probabilidade de alta performance do telefone (taxa de read > 90%). A classe usa
essas regras para transformar a idade de um registro em um score de
atualidade.

- **`id_sistema`** — identificador do sistema (mesmo domínio do ranking).
- **`regra`** — expressão textual no formato `"dias <op> <limite>"` (ex.:
  `"dias <= 826"`). Parseada via regex; operadores suportados: `<=`, `<`,
  `>=`, `>`, `==`.
- **`prob_alta_perf`** — probabilidade de alta performance associada
  àquele corte. Serve diretamente como o `score_atualidade` do telefone
  quando a regra é satisfeita.

### 3.3 `taxa_read` *(opcional)*

Agregado histórico de disparos de WhatsApp por telefone. Quando fornecido,
adiciona um sinal de desempenho real (o telefone já respondeu no passado?).
Se **não fornecido**, o peso `w_read` é zerado e os demais pesos são
renormalizados — o algoritmo continua funcional sem esse sinal.

- **`telefone`** — número do telefone (chave de junção).
- **`taxa_read`** — proporção de mensagens lidas (`total_reads /
  total_envios`). Quanto maior, melhor o histórico de engajamento
  daquele número.

## 4. Metodologia do score

O score final é uma **combinação linear ponderada** de três componentes
— escolha proposital pela total interpretabilidade (não é caixa-preta):

```
score_final = w_sistema    * n_score_sistema
            + w_atualidade * n_score_atualidade
            + w_read       * n_score_read
```

Cada componente é normalizado via **min-max dentro do mesmo CPF** (a
comparação relevante é sempre entre os telefones de um mesmo CPF):

1. **`n_score_sistema`** — `score_sistema` vindo do ranking de
   confiabilidade do **sistema escolhido** (o mais confiável dentre os que
   reportaram aquele `(cpf, telefone)`).
2. **`n_score_atualidade`** — calculado vetorialmente: para cada linha,
   `dias_desde_atualizacao = data_referencia - data_atualizacao` é
   confrontado com as regras do `id_sistema` daquele telefone; a regra
   cujo `operador/limite` é satisfeito fornece a `prob_alta_perf`.
   `data_referencia` é configurável (default = hoje, normalizada).
3. **`n_score_read`** — vem da `taxa_read` por telefone. **Se a fonte não
   é fornecida**, `w_read` é zerado e `w_sistema`/`w_atualidade` são
   **renormalizados** para somar 1 — o algoritmo continua funcionando
   sem regressão.

### Pesos

Default em `ScoreWeights`: `w_sistema=0.3`, `w_atualidade=0.2`,
`w_read=0.5`. 

### Imputação de valores faltantes

Componentes sem valor (ex.: sistema sem regra aplicável, telefone sem
histórico, ou CPF com um único telefone)
recebem valor **neutro 0.5** após a normalização — evita penalizar ou
premiar artificialmente o telefone por falta de sinal.

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

- **Com histórico**: os 3 sinais entram na combinação linear com os pesos
  originais.
- **Sem histórico**: omita `taxa_read_path` (ou `taxa_read=None`). A
  classe detecta a ausência e renormaliza os pesos restantes.

## 6. Saída

`score(...)` retorna um DataFrame ordenado por `(cpf, score_final desc)`,
com `rank` por CPF e os componentes decompostos para auditoria:

`cpf`, `telefone`, `rank`, `score_final`, `id_sistema`,
`sistema_nome` (se disponível), `score_sistema`, `score_atualidade`,
`taxa_read`, `n_score_sistema`, `n_score_atualidade`, `n_score_read`,
`data_atualizacao`, `dias_desde_atualizacao`, `n_sistemas`,
`peso_sistema`, `peso_atualidade`, `peso_read`.

Os pesos efetivamente aplicados (já renormalizados conforme `use_read`)
são incluídos em cada linha — facilita reproduzir o cálculo
manualmente e auditar decisões.
