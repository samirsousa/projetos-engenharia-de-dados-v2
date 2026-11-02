# Web Scraping Ético de Indicadores Macroeconômicos com Orquestrador DAG (Airflow/Cron Simulator)

Projeto de Engenharia de Dados em **Python puro** para extração automatizada, higienização, tipagem forte e armazenamento histórico relacional de indicadores macroeconômicos nacionais (**SELIC**, **IPCA**, **IGP-M**, **Câmbio PTAX USD/BRL e EUR/BRL**, **IBC-Br**, **Taxa de Desemprego PNAD** e **Dívida Bruta/PIB**), coordenado por um **Orquestrador Customizado em DAG Sequencial** inspirado no Apache Airflow.

---

## Sumário

1. [Arquitetura de Web Scraping Ético e Resiliência de Rede](#1-arquitetura-de-web-scraping-ético-e-resiliência-de-rede)
2. [Diagramas Conceituais da Arquitetura](#2-diagramas-conceituais-da-arquitetura)
3. [Estrutura do Projeto](#3-estrutura-do-projeto)
4. [Detalhamento Técnico dos 4 Componentes](#4-detalhamento-técnico-dos-4-componentes)
5. [Modelagem Relacional SQLite e Cálculo de Juro Real (Fisher)](#5-modelagem-relacional-sqlite-e-cálculo-de-juro-real-fisher)
6. [Instruções de Execução](#6-instruções-de-execução)
7. [Suíte de Testes Automatizados](#7-suíte-de-testes-automatizados)

---

## 1. Arquitetura de Web Scraping Ético e Resiliência de Rede

Coletar dados de portais governamentais e instituições financeiras públicas exige responsabilidade operacional e tolerância a falhas transitórias:

1. **Conformidade Ética (`robots.txt` & `User-Agent`)**:
   - Antes de requisitar qualquer página HTML, o extrator interpreta o arquivo `robots.txt` do portal via `urllib.robotparser.RobotFileParser` e valida se o `User-Agent` do robô (`MacroDataEngineeringBot/1.0`) possui permissão explícita para o caminho.
   - Aplica *politeness rate-limiting* entre requisições para jamais sobrecarregar o servidor de origem.
2. **Classificação de Exceções e Retry com Exponential Backoff + Jitter**:
   - **Erros Transitórios (`TransientScrapeError` — HTTP `429`, `500`, `502`, `503`, `504`, `Timeout`)**: Acionam o motor de retentativas com atraso exponencial e *jitter* aleatório para evitar o efeito *Thundering Herd*:
     $$t_{\text{wait}} = \min\left(T_{\max},\; T_{\text{base}} \times 2^{\text{attempt} - 1}\right) + \mathcal{U}(0.01, 0.05)$$
   - **Erros Permanentes (`PermanentScrapeError` / `RobotsTxtDisallowedError` — HTTP `403`, `404`)**: Abortam imediatamente sem desperdiçar retentativas.

---

## 2. Diagramas Conceituais da Arquitetura

### 2.1. Topologia da DAG e Pipeline Medallion (Bronze -> Silver -> Gold Warehouse)

```mermaid
flowchart LR
    subgraph SCHED["4. Orquestrador DAG (Cron: '0 8 * * 1-5')"]
        direction LR
        T1["t1_verify_portal_ethics<br/>(Valida robots.txt)"]
        T2["t2_extract_raw_html<br/>(DOM Parser + Retry Backoff)"]
        T3["t3_clean_and_type_schema<br/>(Limpeza BR + Schema Tipado)"]
        T4["t4_quality_gate<br/>(Valida Invariantes Silver)"]
        T5["t5_load_sqlite_warehouse<br/>(UPSERT Histórico + Relatório)"]

        T1 -->|"XCom"| T2 -->|"XCom"| T3 -->|"XCom"| T4 -->|"XCom"| T5
    end

    subgraph STORAGE["Camadas de Dados e Persistência"]
        HTML[("Portal HTML Público<br/>(Boletim BCB/IBGE + PTAX)")]
        BRONZE[("Camada Bronze (Raw JSON)<br/>(data/bronze_raw/)")]
        SILVER[("Camada Silver (Typed JSON/CSV)<br/>(data/silver_staged/)")]
        SQLITE[("SQLite Historical Warehouse<br/>(macro_indicators.db)")]
        REPORT[("Painel Analítico Markdown<br/>(macro_economic_summary.md)")]

        HTML --> T2
        T2 --> BRONZE
        BRONZE --> T3
        T3 --> SILVER
        SILVER --> T4 & T5
        T5 --> SQLITE --> REPORT
    end
```

### 2.2. Máquina de Estados do Extrator com Retry Logic

```mermaid
sequenceDiagram
    autonumber
    participant DAG as Task t2_extract_raw_html
    participant Ext as MacroWebExtractor
    participant Robots as RobotFileParser (robots.txt)
    participant Portal as Portal Macroeconômico HTML
    participant Bronze as Camada Bronze (JSON + SHA-256)

    DAG->>Ext: run_extraction(batch_id)
    Ext->>Robots: can_fetch(User-Agent, '/boletim_focus_sgs.html')
    Robots-->>Ext: True (Permitido)

    Ext->>Portal: GET /boletim_focus_sgs.html (Tentativa 1/3)
    Portal--xExt: HTTP 503 Service Unavailable (Falha Transitória)
    Note over Ext: Captura TransientScrapeError<br/>Aguarda Backoff Exponencial + Jitter

    Ext->>Portal: GET /boletim_focus_sgs.html (Tentativa 2/3)
    Portal-->>Ext: HTTP 200 OK (HTML Tabelas DOM)
    Ext->>Ext: MacroHTMLTableParser extrai células <tr>/<td>
    Ext->>Bronze: Persiste raw_macro_indicators_<id>.json + Hash SHA-256
    Ext-->>DAG: Push XCom (bronze_file_path, retries=1)
```

### 2.3. Modelo Entidade-Relacionamento (SQLite Historical Warehouse)

```mermaid
erDiagram
    dim_indicators ||--o{ fact_macro_history : "1:N (indicator_code)"
    dim_indicators {
        TEXT indicator_code PK
        INTEGER series_id
        TEXT indicator_name
        TEXT source_institution
        TEXT unit
        TEXT frequency
        TEXT updated_at_utc
    }
    fact_macro_history {
        INTEGER history_id PK
        TEXT indicator_code FK
        TEXT reference_date "UNIQUE(indicator_code, reference_date)"
        REAL numeric_value
        TEXT publication_status
        INTEGER is_preliminary
        TEXT source_page
        TEXT batch_id
        TEXT first_ingested_at_utc
        TEXT last_updated_at_utc
        INTEGER revision_count
    }
    dag_execution_history {
        TEXT dag_run_id PK
        TEXT dag_id
        TEXT schedule_cron
        TEXT started_at_utc
        TEXT finished_at_utc
        TEXT status
        INTEGER tasks_total
        INTEGER tasks_succeeded
        REAL total_duration_ms
        INTEGER records_loaded
    }
```

---

## 3. Estrutura do Projeto

```text
08-web-scraping-macro/
├── README.md                           # Documentação técnica completa do projeto
├── run_dag.py                          # Ponto de entrada principal do Orquestrador DAG
├── scripts/
│   ├── 1_extractor.py                  # Script 1: Extrator Web Scraping com Retry Logic
│   ├── 2_transformer.py                # Script 2: Limpeza, normalização e Schema Tipado
│   ├── 3_loader.py                     # Script 3: Carga histórica relacional no SQLite
│   └── 4_dag_orchestrator.py           # Script 4: Simulador de Orquestração em DAG Sequencial
├── src/
│   ├── __init__.py
│   ├── config.py                       # Configurações de rede, User-Agent, Backoff e diretórios
│   ├── portal_simulator.py             # Gerador de páginas HTML5 macroeconômicas e robots.txt
│   ├── extractor.py                    # Parser DOM HTML nativo, RobotFileParser e Retry Engine
│   ├── transformer.py                  # Conversão numérica BR, datas ISO, quarentena e tipagem
│   ├── loader.py                       # DDL SQLite, UPSERT histórico, Views SQL e relatório
│   └── dag_orchestrator.py             # Motor DAG (Kahn Topological Sort, XCom, TaskState)
├── tests/
│   ├── __init__.py
│   └── test_macro_pipeline.py          # Testes unitários e de integração fim-a-fim
├── data/                               # Gerado automaticamente durante a execução
│   ├── mock_portal_html/               # Páginas HTML5 e robots.txt inspecionados pelo scraper
│   ├── bronze_raw/                     # Payloads JSON brutos extraídos + SHA-256
│   ├── silver_staged/                  # Registros limpos e estritamente tipados (JSON e CSV)
│   └── warehouse/
│       └── macro_indicators.db         # Banco de dados relacional histórico SQLite
├── logs/
│   └── latest_dag_run.json             # Telemetria detalhada da execução da DAG e XCom
└── reports/
    └── macro_economic_summary.md       # Relatório analítico com Juro Real (Equação de Fisher)
```

---

## 4. Detalhamento Técnico dos 4 Componentes

### 1. Extrator Robusto (`src/extractor.py` & `scripts/1_extractor.py`)
- Implementa [`MacroWebExtractor`](file:///c:/Users/Samir/Downloads/PROJETOS%20PYTHON%20v2/08-web-scraping-macro/src/extractor.py#L121-L266) e [`MacroHTMLTableParser`](file:///c:/Users/Samir/Downloads/PROJETOS%20PYTHON%20v2/08-web-scraping-macro/src/extractor.py#L67-L118) (baseado em `html.parser.HTMLParser` da biblioteca padrão).
- Possui injeção configurável de falha transitória (`--simulate-failures 1`) que simula um erro `HTTP 503 Service Unavailable` na primeira requisição, demonstrando em tempo real o log de **Exponential Backoff + Jitter** e a recuperação automática na tentativa subsequente.

### 2. Transformador e Schema Tipado (`src/transformer.py` & `scripts/2_transformer.py`)
- Implementa [`MacroDataTransformer`](file:///c:/Users/Samir/Downloads/PROJETOS%20PYTHON%20v2/08-web-scraping-macro/src/transformer.py#L64-L246) que converte células brutas de HTML para o dataclass fortemente tipado [`TypedMacroIndicator`](file:///c:/Users/Samir/Downloads/PROJETOS%20PYTHON%20v2/08-web-scraping-macro/src/transformer.py#L31-L47):
  - Remove notas de rodapé e sufixos (`(*)`, `[1]`, `[preliminar]`, `% a.a.`, `R$`, `pts`, `do PIB`).
  - Converte decimais brasileiros (`"10,75% a.a. (*)"` $\rightarrow$ `10.75`, `"R$ 5,7450"` $\rightarrow$ `5.745`).
  - Padroniza datas heterogêneas (`"01/11/2026"` e `"2026-11-01"`) para `YYYY-MM-DD`.
  - Isola linhas não divulgadas (`"N/D (*)"`) em quarentena documentada sem interromper as séries válidas.

### 3. Carregador Histórico SQLite (`src/loader.py` & `scripts/3_loader.py`)
- Implementa [`MacroWarehouseLoader`](file:///c:/Users/Samir/Downloads/PROJETOS%20PYTHON%20v2/08-web-scraping-macro/src/loader.py#L107-L299) sobre o banco `macro_indicators.db`.
- Executa `UPSERT` idempotente em `fact_macro_history` usando a chave natural composta `UNIQUE(indicator_code, reference_date)`:
  - Se um indicador já existente receber uma revisão (ex: de `PRELIMINAR` para `DEFINITIVO`), o valor é atualizado, `first_ingested_at_utc` é preservado e `revision_count` é incrementado automaticamente.

### 4. Simulador de Orquestração em DAG (`src/dag_orchestrator.py` & `run_dag.py`)
- Implementa um motor completo de **Directed Acyclic Graph (DAG)** em Python puro ([`DAG`](file:///c:/Users/Samir/Downloads/PROJETOS%20PYTHON%20v2/08-web-scraping-macro/src/dag_orchestrator.py#L108-L263) e [`PythonTask`](file:///c:/Users/Samir/Downloads/PROJETOS%20PYTHON%20v2/08-web-scraping-macro/src/dag_orchestrator.py#L68-L91)):
  - Suporta encadeamento via operador `>>` (`t1 >> t2 >> t3 >> t4 >> t5`).
  - Executa ordenação topológica via **Algoritmo de Kahn** e bloqueia grafos cíclicos (`DAGCycleError`).
  - Propaga metadados entre tarefas via `XCom` (`ctx.xcom_push` / `ctx.xcom_pull`) e propaga o estado `UPSTREAM_FAILED` caso qualquer tarefa anterior falhe após suas retentativas.

---

## 5. Modelagem Relacional SQLite e Cálculo de Juro Real (Fisher)

Além de armazenar as séries históricas, o banco SQLite disponibiliza a view analítica `vw_brazil_real_interest_rate`, que cruza automaticamente a série `SELIC_META` com `IPCA_ACUM_12M` e calcula a **Taxa de Juros Real Ex-Post** pela Equação Exata de Fisher:

$$r_{\text{real}} = \left(\frac{1 + \frac{\text{SELIC}}{100}}{1 + \frac{\text{IPCA}_{12\text{m}}}{100}} - 1\right) \times 100$$

---

## 6. Instruções de Execução

### Opção A: Executar a DAG Completa via Orquestrador (Recomendado)

```bash
python 08-web-scraping-macro/run_dag.py --clean --simulate-failures 1
```

Também pode ser invocado pelo script numerado 4:

```bash
python 08-web-scraping-macro/scripts/4_dag_orchestrator.py --clean --simulate-failures 1
```

### Opção B: Executar cada Etapa Individualmente (Scripts 1, 2 e 3)

```bash
# 1. Extração Web Scraping Ético (gera JSON bruto na camada Bronze)
python 08-web-scraping-macro/scripts/1_extractor.py --simulate-failures 1

# 2. Limpeza, Normalização e Schema Tipado (gera JSON e CSV na camada Silver)
python 08-web-scraping-macro/scripts/2_transformer.py

# 3. Carga Histórica Relacional no SQLite e geração do Relatório Analítico
python 08-web-scraping-macro/scripts/3_loader.py
```

---

## 7. Suíte de Testes Automatizados

Para executar os testes unitários e de integração (validação de `robots.txt`, recuperação de falha transitória HTTP 503 via Exponential Backoff, parsing numérico brasileiro, detecção de ciclo na DAG, propagação de `UPSTREAM_FAILED` e idempotência de `UPSERT` no SQLite):

```bash
python 08-web-scraping-macro/tests/test_macro_pipeline.py -v
```
