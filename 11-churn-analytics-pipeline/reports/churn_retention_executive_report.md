# Relatório Executivo: Customer Churn, Cohort Retention & LTV Analytics

**Mês de Fechamento (Snapshot):** `2025-12`

## 1. Sumário Executivo de Indicadores SaaS (North Star KPIs)

| Indicador (KPI) | Valor Consolidado | Benchmark SaaS B2B | Status |
| :--- | ---: | :--- | :--- |
| **Clientes Ativos no Fechamento** | `841` | - | Base Ativa |
| **MRR de Fechamento (Ending MRR)** | `R$ 622,507.41` | - | Receita Recorrente Mensal |
| **ARR de Fechamento (Ending ARR)** | `R$ 7,470,088.92` | - | Run-rate Anualizado |
| **ARPA (Ticket Médio Mensal)** | `R$ 740.20` | - | Receita Média por Conta |
| **Logo Churn Mensal Médio** | `4.86%` | `< 3.50%` (Blended) | Monitoramento de Onboarding |
| **Gross MRR Churn Médio** | `3.40%` | `< 2.50%` | Perda Bruta de Receita |
| **Net MRR Churn Médio** | `1.32%` | `< 0.00%` (Ideal) | Compensado por Expansão |
| **GRR Médio (Gross Revenue Retention)** | `96.60%` | `> 90% a 97%` | Retenção Bruta Mensal |
| **NRR / NDR Médio (Net Dollar Retention)** | `98.68%` | `> 100.0%` | Eficiência de Upsell/Cross-sell |
| **LTV Médio Ponderado (Margem Bruta)** | `R$ 30,510.92` | `> 3x CAC` | Valor no Ciclo de Vida |
| **CAC Médio Ponderado** | `R$ 997.47` | - | Custo de Aquisição |
| **Razão Global LTV : CAC** | `30.59x` | `>= 3.00x` | Unit Economics Saudável |

---

## 2. Evolução Mensal de MRR Bridge & Taxas de Churn

| Mês | Base Inicial | Novos | Churn | Base Final | Beginning MRR (R$) | New MRR (R$) | Expansion (R$) | Churned MRR (R$) | Ending MRR (R$) | Logo Churn % | Net MRR Churn % | NRR % |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `2025-01` | 0 | +75 | -0 | **75** | 0.00 | +45,569.74 | +0.00 | -0.00 | **45,569.74** | `0.00%` | `0.00%` | `100.00%` |
| `2025-02` | 75 | +78 | -3 | **150** | 45,569.74 | +49,576.59 | +597.24 | -1,647.98 | **94,020.70** | `4.00%` | `2.47%` | `97.53%` |
| `2025-03` | 150 | +80 | -9 | **221** | 94,020.70 | +47,426.26 | +1,309.97 | -4,269.70 | **138,063.48** | `6.00%` | `3.60%` | `96.40%` |
| `2025-04` | 221 | +83 | -8 | **296** | 138,063.48 | +48,917.68 | +3,167.02 | -2,724.95 | **187,102.21** | `3.62%` | `-0.09%` | `100.09%` |
| `2025-05` | 296 | +86 | -17 | **365** | 187,102.21 | +54,257.73 | +3,203.35 | -7,091.81 | **237,292.32** | `5.74%` | `2.17%` | `97.83%` |
| `2025-06` | 365 | +88 | -22 | **431** | 237,292.32 | +55,469.25 | +4,259.87 | -8,131.59 | **287,364.85** | `6.03%` | `2.27%` | `97.73%` |
| `2025-07` | 431 | +91 | -13 | **509** | 287,364.85 | +57,809.99 | +6,683.12 | -6,592.32 | **344,252.22** | `3.02%` | `0.32%` | `99.68%` |
| `2025-08` | 509 | +93 | -32 | **570** | 344,252.22 | +51,490.52 | +7,086.73 | -15,706.19 | **386,651.91** | `6.29%` | `2.64%` | `97.36%` |
| `2025-09` | 570 | +96 | -24 | **642** | 386,651.91 | +54,910.91 | +6,831.33 | -7,877.26 | **439,303.21** | `4.21%` | `0.58%` | `99.42%` |
| `2025-10` | 642 | +99 | -26 | **715** | 439,303.21 | +57,725.19 | +14,359.85 | -10,463.50 | **500,438.14** | `4.05%` | `-0.78%` | `100.78%` |
| `2025-11` | 715 | +101 | -34 | **782** | 500,438.14 | +65,481.63 | +16,101.44 | -10,637.59 | **570,194.02** | `4.76%` | `-0.85%` | `100.85%` |
| `2025-12` | 782 | +104 | -45 | **841** | 570,194.02 | +64,663.07 | +10,251.78 | -21,438.27 | **622,507.41** | `5.75%` | `2.17%` | `97.83%` |

---

## 3. Matriz de Coorte de Retenção de Clientes (Logo Cohort Retention %)

| Safra (Cohort) | Clientes M00 | M00 | M01 | M02 | M03 | M04 | M05 | M06 | M07 | M08 | M09 | M10 | M11 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `2025-01` | 75 | 100.0% | 96.0% | 88.0% | 84.0% | 80.0% | 74.7% | 72.0% | 70.7% | 69.3% | 69.3% | 69.3% | 68.0% |
| `2025-02` | 78 | 100.0% | 96.2% | 96.2% | 91.0% | 85.9% | 85.9% | 78.2% | 75.6% | 71.8% | 69.2% | 68.0% | - |
| `2025-03` | 80 | 100.0% | 93.8% | 87.5% | 81.2% | 78.8% | 77.5% | 76.2% | 76.2% | 75.0% | 73.8% | - | - |
| `2025-04` | 83 | 100.0% | 94.0% | 88.0% | 84.3% | 79.5% | 75.9% | 75.9% | 75.9% | 71.1% | - | - | - |
| `2025-05` | 86 | 100.0% | 95.3% | 93.0% | 87.2% | 84.9% | 80.2% | 75.6% | 69.8% | - | - | - | - |
| `2025-06` | 88 | 100.0% | 95.5% | 89.8% | 83.0% | 80.7% | 79.5% | 76.1% | - | - | - | - | - |
| `2025-07` | 91 | 100.0% | 89.0% | 84.6% | 81.3% | 78.0% | 72.5% | - | - | - | - | - | - |
| `2025-08` | 93 | 100.0% | 94.6% | 86.0% | 79.6% | 75.3% | - | - | - | - | - | - | - |
| `2025-09` | 96 | 100.0% | 93.8% | 89.6% | 81.2% | - | - | - | - | - | - | - | - |
| `2025-10` | 99 | 100.0% | 86.9% | 80.8% | - | - | - | - | - | - | - | - | - |
| `2025-11` | 101 | 100.0% | 93.1% | - | - | - | - | - | - | - | - | - | - |
| `2025-12` | 104 | 100.0% | - | - | - | - | - | - | - | - | - | - | - |

---

## 4. Lifetime Value (LTV) & Unit Economics por Segmento e Canal

| Segmento | Canal de Aquisição | Clientes | ARPA (R$) | Churn Mensal % | Lifetime (Meses) | LTV Margem Bruta (R$) | CAC (R$) | LTV:CAC | Payback (Meses) | Diagnóstico |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| **Enterprise** | Partner & Referral | 11 | 1,994.94 | `1.79%` | 55.9 | **94,731.84** | 513.09 | **`184.63x`** | 0.3 | Excelente (>= 5.0x - Escalar Investimento) |
| **Enterprise** | Paid Search (Google Ads) | 28 | 2,127.50 | `0.80%` | 125.0 | **226,047.50** | 1,295.35 | **`174.51x`** | 0.7 | Excelente (>= 5.0x - Escalar Investimento) |
| **Enterprise** | Organic Search (SEO) | 41 | 2,081.06 | `2.01%` | 49.8 | **88,004.98** | 568.40 | **`154.83x`** | 0.3 | Excelente (>= 5.0x - Escalar Investimento) |
| **Enterprise** | Outbound Sales (SDR/AE) | 59 | 2,087.10 | `0.80%` | 125.0 | **221,753.75** | 2,950.35 | **`75.16x`** | 1.7 | Excelente (>= 5.0x - Escalar Investimento) |
| **Enterprise** | Paid Social (LinkedIn) | 10 | 2,151.42 | `1.89%` | 52.9 | **96,757.14** | 1,764.60 | **`54.83x`** | 1.0 | Excelente (>= 5.0x - Escalar Investimento) |
| **Mid-Market** | Organic Search (SEO) | 115 | 688.13 | `3.08%` | 32.5 | **18,563.96** | 444.31 | **`41.78x`** | 0.8 | Excelente (>= 5.0x - Escalar Investimento) |
| **Mid-Market** | Partner & Referral | 51 | 651.77 | `3.60%` | 27.8 | **15,026.94** | 396.89 | **`37.86x`** | 0.7 | Excelente (>= 5.0x - Escalar Investimento) |
| **Mid-Market** | Paid Search (Google Ads) | 79 | 737.25 | `4.02%` | 24.9 | **15,245.77** | 1,023.29 | **`14.90x`** | 1.7 | Excelente (>= 5.0x - Escalar Investimento) |
| **SMB** | Partner & Referral | 86 | 235.02 | `6.58%` | 15.2 | **2,862.77** | 325.40 | **`8.80x`** | 1.7 | Excelente (>= 5.0x - Escalar Investimento) |
| **SMB** | Organic Search (SEO) | 173 | 233.85 | `6.50%` | 15.4 | **2,883.54** | 360.25 | **`8.00x`** | 1.9 | Excelente (>= 5.0x - Escalar Investimento) |
| **Mid-Market** | Outbound Sales (SDR/AE) | 103 | 679.08 | `3.27%` | 30.6 | **17,248.93** | 2,288.95 | **`7.54x`** | 4.1 | Excelente (>= 5.0x - Escalar Investimento) |
| **Mid-Market** | Paid Social (LinkedIn) | 27 | 727.59 | `7.26%` | 13.8 | **8,331.27** | 1,357.59 | **`6.14x`** | 2.2 | Excelente (>= 5.0x - Escalar Investimento) |
| **SMB** | Outbound Sales (SDR/AE) | 37 | 226.09 | `2.26%` | 44.2 | **8,006.19** | 1,844.56 | **`4.34x`** | 10.2 | Saudável (3.0x a 4.9x - Crescimento Sustentável) |
| **SMB** | Paid Search (Google Ads) | 171 | 237.83 | `7.36%` | 13.6 | **2,589.27** | 814.91 | **`3.18x`** | 4.3 | Saudável (3.0x a 4.9x - Crescimento Sustentável) |
| **SMB** | Paid Social (LinkedIn) | 83 | 229.70 | `10.40%` | 9.6 | **1,768.94** | 1,106.61 | **`1.60x`** | 6.0 | Atenção (< 3.0x - Otimizar CAC ou Retenção) |

---

## 5. Diagnóstico de Motivos de Cancelamento & Impacto Financeiro

| Tipo de Churn | Motivo Declarado / Raiz | Segmento | Contas Perdidas | MRR Perdido (R$) | ARR Perdido (R$) | Tenure Médio (Meses) |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: |
| `Voluntary` | Budget / Cost Reduction | Mid-Market | 22 | 14,733.90 | **176,806.80** | 2.9 |
| `Voluntary` | Budget / Cost Reduction | SMB | 49 | 10,688.77 | **128,265.24** | 3.5 |
| `Voluntary` | Low Product Adoption / Onboarding Gap | Mid-Market | 16 | 10,027.27 | **120,327.24** | 2.4 |
| `Voluntary` | Low Product Adoption / Onboarding Gap | SMB | 38 | 8,540.57 | **102,486.84** | 3.2 |
| `Voluntary` | Missing Enterprise Feature / Integration | Mid-Market | 10 | 6,292.50 | **75,510.00** | 2.3 |
| `Voluntary` | Switched to Competitor | SMB | 27 | 5,947.11 | **71,365.32** | 3.0 |
| `Involuntary` | Involuntary - Credit Card Expired / Hard Decline | SMB | 21 | 4,623.76 | **55,485.12** | 3.3 |
| `Voluntary` | Missing Enterprise Feature / Integration | Enterprise | 2 | 4,500.63 | **54,007.56** | 3.0 |
| `Voluntary` | Switched to Competitor | Enterprise | 2 | 3,873.96 | **46,487.52** | 1.5 |
| `Voluntary` | Low Product Adoption / Onboarding Gap | Enterprise | 2 | 3,793.25 | **45,519.00** | 6.5 |
| `Involuntary` | Involuntary - Credit Card Expired / Hard Decline | Mid-Market | 6 | 3,743.75 | **44,925.00** | 4.7 |
| `Voluntary` | Switched to Competitor | Mid-Market | 6 | 3,673.37 | **44,080.44** | 4.3 |

---

## 6. Simulação Executiva de Impacto Financeiro da Retenção

1. **Redução de 1.0 p.p. no Churn Mensal (Alavanca de Customer Success & Onboarding):**
   - Economia Composta de MRR em 12 meses: **`R$ 78,949.52 / mês`**
   - Aumento Direto de ARR (Receita Anual Recorrente): **`R$ 947,394.24 / ano`**
   - Criação de Valor no Valuation da Empresa (Múltiplo 6.0x ARR): **`R$ 5,684,365.44`**
2. **Automação de Dunning & Recuperação de Churn Involuntário (Cartão Expirado/Falha de Pagamento):**
   - ARR Total Perdido por Falha de Cobrança Involuntária: `R$ 121,716.96`
   - ARR Recuperável Imediato (taxa de recuperação de 65% via Smart Retries & Pix/Boleto Fallback): **`R$ 79,116.02 / ano`**
