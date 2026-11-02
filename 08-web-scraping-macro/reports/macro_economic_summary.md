# Painel Analítico de Indicadores Macroeconômicos (SQLite Data Warehouse)

- **Gerado em (UTC):** `2026-11-02T02:54:59.014Z`
- **Banco de Dados Relacional:** `macro_indicators.db`
- **Total de Observações Históricas Armazenadas:** `25`

---

## 1. Snapshot Mais Recente por Indicador (`vw_latest_macro_snapshot`)

| Código | Série SGS/IBGE | Indicador | Instituição | Última Data | Valor | Unidade | Status | Revisões |
| :--- | :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `DESEMPREGO_PNAD` | `24369` | Taxa de Desocupação PNAD Contínua | IBGE | `2026-11-01` | **6.4000** | `PCT_PEA` | `PRELIMINAR` | `1` |
| `DIVIDA_BRUTA_PIB` | `13762` | Dívida Bruta do Governo Geral (% do PIB) | Banco Central do Brasil (BCB) | `2026-11-01` | **78.2000** | `PCT_PIB` | `PRELIMINAR` | `1` |
| `IBC_BR_INDICE` | `24364` | IBC-Br - Índice de Atividade Econômica do Banco Central | Banco Central do Brasil (BCB) | `2026-11-01` | **153.6000** | `INDEX_PTS` | `PRELIMINAR` | `1` |
| `IGPM_ACUM_12M` | `189` | IGP-M - Índice Geral de Preços do Mercado (12m) | FGV IBRE | `2026-11-01` | **5.3400** | `PCT_12M` | `DEFINITIVO` | `1` |
| `IPCA_ACUM_12M` | `13522` | IPCA - Inflação Oficial Acumulada 12 Meses | IBGE | `2026-11-01` | **4.6500** | `PCT_12M` | `PRELIMINAR` | `1` |
| `PTAX_EUR_BRL` | `21619` | Taxa de Câmbio PTAX Euro (Venda) | Banco Central do Brasil (BCB) | `2026-11-01` | **6.2980** | `BRL` | `DEFINITIVO` | `1` |
| `PTAX_USD_BRL` | `1` | Taxa de Câmbio PTAX Dólar Americano (Venda) | Banco Central do Brasil (BCB) | `2026-11-01` | **5.7450** | `BRL` | `DEFINITIVO` | `1` |
| `SELIC_META` | `432` | Taxa de Juros SELIC (Meta COPOM) | Banco Central do Brasil (BCB) | `2026-11-01` | **11.2500** | `PCT_AA` | `DEFINITIVO` | `1` |

---

## 2. Evolução da Taxa de Juros Real Ex-Post — Equação de Fisher (`vw_brazil_real_interest_rate`)

$$r_{\text{real}} = \left(\frac{1 + i_{\text{SELIC}}}{1 + \pi_{\text{IPCA}}} - 1\right) \times 100$$

| Data de Referência | Meta SELIC (% a.a.) | IPCA Acum. 12m (%) | Juro Real Fisher (% a.a.) | Spread Linear (p.p.) |
| :---: | :---: | :---: | :---: | :---: |
| `2026-08-01` | `10.50%` | `4.24%` | **6.0054%** | `6.26 p.p.` |
| `2026-09-01` | `10.75%` | `4.42%` | **6.0621%** | `6.33 p.p.` |
| `2026-10-01` | `11.00%` | `4.58%` | **6.1388%** | `6.42 p.p.` |
| `2026-11-01` | `11.25%` | `4.65%` | **6.3067%** | `6.60 p.p.` |
