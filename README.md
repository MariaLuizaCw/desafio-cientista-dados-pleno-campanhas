# Desafio Técnico — Cientista de Dados Pleno · Squad WhatsApp

Solução para o case da Prefeitura do Rio: medir o "calor" das fontes de telefones do RMI e construir uma **inteligência de escolha** capaz de selecionar, dentre os telefones associados a um CPF, os mais propensos a entregar e ser lidos no WhatsApp.

---

## Convenção de classificação

Ao longo de todo o projeto adotamos duas categorias binárias de qualidade — aplicáveis tanto a um **telefone** quanto a um **CPF**:

| Categoria         | Definição                                                                 | Limiar |
|-------------------|---------------------------------------------------------------------------|--------|
| **HighDelivery**  | Taxa de entrega = `(delivered + read) / total_disparos` ≥ limiar          | **90%** |
| **HighRead**      | Taxa de leitura = `read / total_disparos` ≥ limiar                        | **75%** |

Combinações usadas nos notebooks e nos entregáveis:

- **Telefone HighDelivery** / **Telefone HighRead** — quando o objeto é um telefone.
- **CPF HighDelivery** / **CPF HighRead** — quando o objeto é um CPF.


---

## Onde encontrar cada entregável

### Parte 1 — Análise Exploratória e Qualidade de Fontes

**1. Desestruturação e Correlação**
- **Entregável:** análise comparativa de taxas de entrega (`DELIVERED`) agregadas por sistema de origem.
- **Onde:** `notebooks/02_qualidade_fontes.ipynb` 

**2. Janela de Atualidade**
- **Entregável:** análise de decaimento da qualidade ao longo do tempo; identificação de "prazo de validade" por sistema.
- **Onde:** `notebooks/03_janela_atualidade.ipynb`
- **Artefato gerado:** `outputs/decision_trees/df_regras_atualidade.csv` (regras extraídas das árvores).

### Parte 2 — Inteligência de Priorização

**3. Ranking de Sistemas**
- **Entregável:** tabela/score de ranking das fontes com justificativa matemática.
- **Onde:** `notebooks/04_ranking_sistemas.ipynb` 
- **Artefatos gerados:**
  - `deliverables/ranking_confiabilidade.csv` 
  - `deliverables/ranking_operacional.csv`

**4. Algoritmo de Escolha**
- **Entregável:** algoritmo que, dado um CPF com N telefones, seleciona automaticamente os 2 melhores combinando origem, atualidade e DDD.
- **Onde:**
  - `src/phone_scorer.py` - implementação do algoritmo.
  - `src/phone_scorer.md` - especificação completa: entradas, fórmula, pesos e auditabilidade.
  - `notebooks/06_teste_phone_scorer.ipynb` - demonstração de uso e validação do algoritmo.

### Parte 3 — Desenho de Experimento

**5. Proposta de Teste A/B**
- **Entregável:** desenho do experimento com hipótese nula, métricas primárias/secundárias, tamanho de amostra e duração estimada.
- **Onde:**
  - `deliverables/proposta_teste_ab/proposta_teste_ab.pdf` — documento final da proposta.
  - `deliverables/proposta_teste_ab/latex/` — arquivos .tex usados no desenvolvimento do documento.
  - `notebooks/07_proporcao_cpfs_taxas.ipynb` — estatísticas auxiliares para o cálculo de tamanho de amostra (insumo da proposta).


---

## Estrutura do repositório

```
desafio-cientista-dados-pleno-campanhas/
├── data/                      # dados brutos (NÃO versionado — ver "Dados")
├── notebooks/                 # análises numeradas em ordem de execução
│   ├── 01_preprocessing.ipynb
│   ├── 02_qualidade_fontes.ipynb
│   ├── 03_janela_atualidade.ipynb
│   ├── 04_ranking_sistemas.ipynb
│   ├── 05_analise_por_ddd.ipynb
│   ├── 06_teste_phone_scorer.ipynb
│   └── 07_proporcao_cpfs_taxas.ipynb
├── src/
│   ├── phone_scorer.py        # classe PhoneScorer (algoritmo de escolha)
│   └── phone_scorer.md        # especificação detalhada do algoritmo
├── outputs/
│   ├── processed/             # parquets intermediários gerados pelo 01
│   └── decision_trees/        # árvores e regras geradas pelo 03
├── mapping/
│   └── mapping_sistemas.csv   # de-para id_sistema → sistema_nome
├── deliverables/
│   ├── ranking_confiabilidade.csv
│   ├── ranking_operacional.csv
│   └── proposta_teste_ab/
│       ├── proposta_teste_ab.pdf
│       └── latex/             # fontes LaTeX da proposta (main.tex + seções)
├── requirements.txt
└── README.md
```

---

## 📂 Mapeamento dos Notebooks

| Notebook                         | Parte do Projeto                              | Item |
|----------------------------------|-----------------------------------------------|------|
| 01_preprocessing.ipynb           | Base (pré-processamento para todas as partes + análise exploratória e entendimento dos dados) | —    |
| 02_qualidade_fontes.ipynb        | Parte 1: Análise Exploratória                 | 1. Desestruturação e Correlação |
| 03_janela_atualidade.ipynb       | Parte 1: Análise Exploratória                 | 2. Janela de Atualidade |
| 04_ranking_sistemas.ipynb        | Parte 2: Inteligência de Priorização          | 3. Ranking de Sistemas |
| 05_analise_por_ddd.ipynb         | Parte 2: Inteligência de Priorização          | 4. Algoritmo de Escolha (DDD) |
| 06_teste_phone_scorer.ipynb      | Parte 2: Inteligência de Priorização          | 4. Algoritmo de Escolha (Scorer) |
| 07_proporcao_cpfs_taxas.ipynb           | Parte 3: Desenho de Experimento               | 5. Baseline para Teste A/B |


---

## Reprodutibilidade

### Pré-requisitos

- **Python 3.14** (versão usada no desenvolvimento)
- Acesso aos parquets brutos do bucket GCS:
  `https://console.cloud.google.com/storage/browser/case_vagas/whatsapp`

### 1. Criar e ativar ambiente virtual

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Linux / macOS:**

```bash
python3.14 -m venv venv
source venv/bin/activate
```

### 2. Instalar dependências

```bash
pip install -r requirements.txt
```

O `requirements.txt` lista as versões exatas usada.

### 3. Posicionar os dados brutos

Baixe os parquets do bucket e coloque-os em `data/` (a pasta é ignorada pelo Git via `.gitignore`).

### 4. Executar os notebooks na ordem

```
notebooks/01_preprocessing.ipynb     
notebooks/02_qualidade_fontes.ipynb
notebooks/03_janela_atualidade.ipynb
notebooks/04_ranking_sistemas.ipynb 
notebooks/05_analise_por_ddd.ipynb
notebooks/06_teste_phone_scorer.ipynb
notebooks/07_proporcao_cpfs_taxas.ipynb    
```

O notebook **01 é obrigatório** antes de qualquer outro: ele materializa os parquets intermediários consumidos pelos demais.

