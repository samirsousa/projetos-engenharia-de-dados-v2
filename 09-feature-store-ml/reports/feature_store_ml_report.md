# Relatório Analítico da Feature Store — Camada Gold para Machine Learning

- **Gerado em (UTC):** `2026-11-02T03:05:28.350Z`
- **Point-in-Time Cutoff (`as_of_timestamp`):** `2026-10-01T23:59:59Z`
- **Total de Clientes Materializados:** `60`
- **Latência de Inferência Online (5 entidades):** `3.966 ms`

---

## 1. Perfil Comportamental por Segmento RFM e Taxa Real de Churn (Holdout 30d)

| Segmento RFM | Clientes | Recência Média (d) | Frequência Média | LTV Médio (R$) | Ticket Móvel (MA3) | Momentum Ticket | Taxa de Churn 30d (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `CHAMPIONS` | 8 | `10.3` | `18.5` | R$ 70,473.52 | R$ 4,431.93 | `1.137` | **0.0%** |
| `LOYAL_CUSTOMERS` | 10 | `23.7` | `12.6` | R$ 44,599.61 | R$ 3,381.05 | `1.006` | **20.0%** |
| `AT_RISK` | 12 | `61.3` | `8.6` | R$ 18,037.75 | R$ 1,388.13 | `0.723` | **58.3%** |
| `POTENTIAL_LOYALIST` | 12 | `9.3` | `7.3` | R$ 9,849.88 | R$ 1,752.35 | `1.183` | **25.0%** |
| `HIBERNATING` | 18 | `109.7` | `4.4` | R$ 7,925.38 | R$ 2,650.62 | `1.086` | **72.2%** |

---

## 2. Importância Preditiva Linear — Top 12 Features vs `target_churn_30d` e `target_next_30d_spend`

| Ranking | Feature Analítica | Correlação Pearson com Churn 30d ($r$) | Correlação com Gasto Futuro 30d ($r$) | Interpretação Preditiva |
| :---: | :--- | :---: | :---: | :--- |
| 1 | `rfm_composite_score` | `-0.6219` | `+0.6115` | Fator de Retenção / Engajamento (-) |
| 2 | `rfm_r_score` | `-0.5737` | `+0.3527` | Fator de Retenção / Engajamento (-) |
| 3 | `rfm_recency_days` | `+0.5658` | `-0.3414` | Fator de Risco de Churn (+) |
| 4 | `rolling_aov_90d` | `-0.5253` | `+0.6390` | Fator de Retenção / Engajamento (-) |
| 5 | `rfm_frequency_total` | `-0.5252` | `+0.7459` | Fator de Retenção / Engajamento (-) |
| 6 | `rfm_f_score` | `-0.5020` | `+0.5527` | Fator de Retenção / Engajamento (-) |
| 7 | `rfm_frequency_90d` | `-0.5009` | `+0.5640` | Fator de Retenção / Engajamento (-) |
| 8 | `peak_hour_sin` | `+0.5002` | `-0.4011` | Fator de Risco de Churn (+) |
| 9 | `rfm_monetary_90d` | `-0.4441` | `+0.7465` | Fator de Retenção / Engajamento (-) |
| 10 | `rfm_monetary_total` | `-0.4297` | `+0.7307` | Fator de Retenção / Engajamento (-) |
| 11 | `rfm_m_score` | `-0.3825` | `+0.5540` | Fator de Retenção / Engajamento (-) |
| 12 | `category_shannon_entropy` | `-0.3588` | `+0.0671` | Fator de Retenção / Engajamento (-) |
