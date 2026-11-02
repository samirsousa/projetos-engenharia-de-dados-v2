# Relatório Executivo: Sistema de Alerta de Anomalias e Fraudes Financeiras

## 1. Sumário Executivo de Desempenho Estatístico & Prevenção a Perdas

| Indicador do Motor Antifraude | Valor Consolidado | Observação Técnica |
| :--- | ---: | :--- |
| **Total de Transações Analisadas** | `2,504` | Base histórica e eventos de risco |
| **Transações Suspeitas (`suspect_transactions`)** | `72` | Taxa de alerta de `2.88%` |
| **Volume Financeiro Total Transacionado** | `R$ 3,302,610.28` | Soma bruta das operações |
| **Perda Financeira Evitada (Fraudes Bloqueadas)** | **`R$ 218,177.70`** | Capital protegido pelo motor |
| **Z-Score Médio das Transações Suspeitas** | `6.16 σ` | Pico máximo de `11.15 σ` |
| **Precisão Estatística (Precision)** | `100.00%` | `TP = 72` / `FP = 0` |
| **Sensibilidade / Cobertura de Fraude (Recall)** | `100.00%` | `TP = 72` / `FN = 0` |
| **F1-Score Global** | **`100.00%`** | Harmônica entre Precisão e Recall |
| **Taxa de Falso Positivo (FPR)** | `0.00%` | Fricção mínima sobre clientes legítimos |

---

## 2. Baselines Estatísticos por Perfil de Cliente (`profile_statistical_baselines`)

| Código do Perfil | Transações | Média Bruta (R$) | Desvio Bruto (R$) | Média Baseline Limpa $\mu$ (R$) | Desvio Baseline $\sigma$ (R$) | Mediana (R$) | MAD (R$) | P95 (R$) | Limite $3\sigma$ (R$) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `AFFLUENT_PLUS` | 842 | 726.97 | 289.16 | **691.32** | **211.48** | 705.68 | 148.37 | 1,125.61 | `1,325.77` |
| `PRIVATE_WEALTH` | 235 | 3,333.43 | 977.60 | **3,187.40** | **625.21** | 3,231.97 | 430.66 | 4,682.86 | `5,063.04` |
| `RETAIL_BASIC` | 1,054 | 149.52 | 60.22 | **144.23** | **46.48** | 142.97 | 32.83 | 233.82 | `283.67` |
| `SME_CORPORATE` | 373 | 4,690.48 | 1,685.46 | **4,573.78** | **1,395.48** | 4,504.07 | 951.68 | 7,132.84 | `8,760.22` |

---

## 3. Top 20 Transações Críticas Sinalizadas em `suspect_transactions`

| TXN ID | Usuário | Perfil | Valor (R$) | Média Usuário (R$) | Desvio $\sigma$ (R$) | Z-Score ($Z_u$) | Mod. Z ($M_u$) | Canal | Score Risco | Severidade | Regras Estatísticas Acionadas |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | :--- | ---: | :--- | :--- |
| `TXN-002454` | `USR-0055` | `RETAIL_BASIC` | **652.80** | 191.44 | 41.38 | **`+11.15σ`** | `+14.09` | `TED_WIRE` | **`100.0`** | `CRITICAL_FRAUD_ALERT` | Z_SCORE_EXTREME(>=4.2) | MODIFIED_Z_MAD(>=3.5) | PROFILE_PEER_3SIGMA_OUTLIER | UNTRUSTED_NEW_DEVICE | HIGH_RISK_MCC(6051) |
| `TXN-002419` | `USR-0039` | `PRIVATE_WEALTH` | **8,283.59** | 3,183.69 | 486.27 | **`+10.49σ`** | `+11.07` | `PIX_INSTANT` | **`100.0`** | `CRITICAL_FRAUD_ALERT` | Z_SCORE_EXTREME(>=4.2) | MODIFIED_Z_MAD(>=3.5) | PROFILE_PEER_3SIGMA_OUTLIER | UNTRUSTED_NEW_DEVICE | HIGH_RISK_MCC(6051) |
| `TXN-002381` | `USR-0095` | `AFFLUENT_PLUS` | **2,637.76** | 786.02 | 183.09 | **`+10.11σ`** | `+8.44` | `TED_WIRE` | **`100.0`** | `CRITICAL_FRAUD_ALERT` | Z_SCORE_EXTREME(>=4.2) | MODIFIED_Z_MAD(>=3.5) | PROFILE_PEER_3SIGMA_OUTLIER | UNTRUSTED_NEW_DEVICE | HIGH_RISK_MCC(6051) |
| `TXN-002458` | `USR-0010` | `AFFLUENT_PLUS` | **2,004.27** | 663.28 | 139.58 | **`+9.61σ`** | `+11.68` | `TED_WIRE` | **`100.0`** | `CRITICAL_FRAUD_ALERT` | Z_SCORE_EXTREME(>=4.2) | MODIFIED_Z_MAD(>=3.5) | PROFILE_PEER_3SIGMA_OUTLIER | UNTRUSTED_NEW_DEVICE | HIGH_RISK_MCC(7995) | NIGHT_OWL_01H_05H_UNTRUSTED |
| `TXN-002343` | `USR-0100` | `SME_CORPORATE` | **16,708.22** | 3,774.11 | 1,356.78 | **`+9.53σ`** | `+9.78` | `TED_WIRE` | **`100.0`** | `CRITICAL_FRAUD_ALERT` | Z_SCORE_EXTREME(>=4.2) | MODIFIED_Z_MAD(>=3.5) | PROFILE_PEER_3SIGMA_OUTLIER | UNTRUSTED_NEW_DEVICE | HIGH_RISK_MCC(7995) | NIGHT_OWL_01H_05H_UNTRUSTED |
| `TXN-002341` | `USR-0086` | `RETAIL_BASIC` | **379.60** | 105.22 | 30.59 | **`+8.97σ`** | `+10.27` | `PIX_INSTANT` | **`100.0`** | `CRITICAL_FRAUD_ALERT` | Z_SCORE_EXTREME(>=4.2) | MODIFIED_Z_MAD(>=3.5) | PROFILE_PEER_3SIGMA_OUTLIER | UNTRUSTED_NEW_DEVICE | HIGH_RISK_MCC(4829) | NIGHT_OWL_01H_05H_UNTRUSTED |
| `TXN-001826` | `USR-0070` | `AFFLUENT_PLUS` | **2,200.61** | 535.02 | 196.01 | **`+8.50σ`** | `+7.00` | `TED_WIRE` | **`100.0`** | `CRITICAL_FRAUD_ALERT` | Z_SCORE_EXTREME(>=4.2) | MODIFIED_Z_MAD(>=3.5) | PROFILE_PEER_3SIGMA_OUTLIER | UNTRUSTED_NEW_DEVICE | HIGH_RISK_MCC(4829) |
| `TXN-002136` | `USR-0025` | `AFFLUENT_PLUS` | **2,147.43** | 762.83 | 169.07 | **`+8.19σ`** | `+7.81` | `TED_WIRE` | **`100.0`** | `CRITICAL_FRAUD_ALERT` | Z_SCORE_EXTREME(>=4.2) | MODIFIED_Z_MAD(>=3.5) | PROFILE_PEER_3SIGMA_OUTLIER | UNTRUSTED_NEW_DEVICE | HIGH_RISK_MCC(7995) |
| `TXN-002339` | `USR-0005` | `PRIVATE_WEALTH` | **8,966.53** | 2,907.51 | 742.27 | **`+8.16σ`** | `+7.01` | `TED_WIRE` | **`100.0`** | `CRITICAL_FRAUD_ALERT` | Z_SCORE_EXTREME(>=4.2) | MODIFIED_Z_MAD(>=3.5) | PROFILE_PEER_3SIGMA_OUTLIER | UNTRUSTED_NEW_DEVICE | HIGH_RISK_MCC(7995) |
| `TXN-002455` | `USR-0060` | `RETAIL_BASIC` | **507.55** | 145.09 | 44.47 | **`+8.15σ`** | `+7.85` | `TED_WIRE` | **`100.0`** | `CRITICAL_FRAUD_ALERT` | Z_SCORE_EXTREME(>=4.2) | MODIFIED_Z_MAD(>=3.5) | PROFILE_PEER_3SIGMA_OUTLIER | UNTRUSTED_NEW_DEVICE | HIGH_RISK_MCC(7995) |
| `TXN-002418` | `USR-0030` | `RETAIL_BASIC` | **496.43** | 155.47 | 42.26 | **`+8.07σ`** | `+6.99` | `TED_WIRE` | **`100.0`** | `CRITICAL_FRAUD_ALERT` | Z_SCORE_EXTREME(>=4.2) | MODIFIED_Z_MAD(>=3.5) | PROFILE_PEER_3SIGMA_OUTLIER | UNTRUSTED_NEW_DEVICE | HIGH_RISK_MCC(5944) | NIGHT_OWL_01H_05H_UNTRUSTED |
| `TXN-002417` | `USR-0085` | `RETAIL_BASIC` | **400.08** | 123.84 | 34.65 | **`+7.97σ`** | `+8.26` | `PIX_INSTANT` | **`100.0`** | `CRITICAL_FRAUD_ALERT` | Z_SCORE_EXTREME(>=4.2) | MODIFIED_Z_MAD(>=3.5) | PROFILE_PEER_3SIGMA_OUTLIER | UNTRUSTED_NEW_DEVICE | HIGH_RISK_MCC(4829) | NIGHT_OWL_01H_05H_UNTRUSTED |
| `TXN-001948` | `USR-0094` | `AFFLUENT_PLUS` | **1,969.70** | 585.09 | 175.45 | **`+7.89σ`** | `+9.44` | `PIX_INSTANT` | **`100.0`** | `CRITICAL_FRAUD_ALERT` | Z_SCORE_EXTREME(>=4.2) | MODIFIED_Z_MAD(>=3.5) | PROFILE_PEER_3SIGMA_OUTLIER | UNTRUSTED_NEW_DEVICE | HIGH_RISK_MCC(6051) | NIGHT_OWL_01H_05H_UNTRUSTED |
| `TXN-002387` | `USR-0085` | `RETAIL_BASIC` | **389.73** | 123.84 | 34.65 | **`+7.67σ`** | `+7.95` | `TED_WIRE` | **`100.0`** | `CRITICAL_FRAUD_ALERT` | Z_SCORE_EXTREME(>=4.2) | MODIFIED_Z_MAD(>=3.5) | PROFILE_PEER_3SIGMA_OUTLIER | UNTRUSTED_NEW_DEVICE | HIGH_RISK_MCC(7995) |
| `TXN-002298` | `USR-0075` | `RETAIL_BASIC` | **513.82** | 117.21 | 51.77 | **`+7.66σ`** | `+6.81` | `TED_WIRE` | **`100.0`** | `CRITICAL_FRAUD_ALERT` | Z_SCORE_EXTREME(>=4.2) | MODIFIED_Z_MAD(>=3.5) | PROFILE_PEER_3SIGMA_OUTLIER | UNTRUSTED_NEW_DEVICE | HIGH_RISK_MCC(6051) |
| `TXN-002393` | `USR-0013` | `PRIVATE_WEALTH` | **7,525.30** | 3,159.83 | 577.15 | **`+7.56σ`** | `+7.76` | `CREDIT_CARD_CHIP` | **`100.0`** | `CRITICAL_FRAUD_ALERT` | Z_SCORE_EXTREME(>=4.2) | MODIFIED_Z_MAD(>=3.5) | PROFILE_PEER_3SIGMA_OUTLIER | UNTRUSTED_NEW_DEVICE | HIGH_RISK_MCC(5944) | IMPOSSIBLE_TRAVEL(21852km/h) |
| `TXN-002496` | `USR-0004` | `AFFLUENT_PLUS` | **1,846.88** | 764.77 | 145.65 | **`+7.43σ`** | `+8.16` | `PIX_INSTANT` | **`100.0`** | `CRITICAL_FRAUD_ALERT` | Z_SCORE_EXTREME(>=4.2) | MODIFIED_Z_MAD(>=3.5) | PROFILE_PEER_3SIGMA_OUTLIER | UNTRUSTED_NEW_DEVICE | HIGH_RISK_MCC(6051) | NIGHT_OWL_01H_05H_UNTRUSTED |
| `TXN-002489` | `USR-0045` | `AFFLUENT_PLUS` | **1,900.52** | 772.41 | 152.39 | **`+7.40σ`** | `+6.25` | `TED_WIRE` | **`100.0`** | `CRITICAL_FRAUD_ALERT` | Z_SCORE_EXTREME(>=4.2) | MODIFIED_Z_MAD(>=3.5) | PROFILE_PEER_3SIGMA_OUTLIER | UNTRUSTED_NEW_DEVICE | HIGH_RISK_MCC(7995) |
| `TXN-002472` | `USR-0055` | `RETAIL_BASIC` | **487.33** | 191.44 | 41.38 | **`+7.15σ`** | `+9.00` | `PIX_INSTANT` | **`100.0`** | `CRITICAL_FRAUD_ALERT` | Z_SCORE_EXTREME(>=4.2) | MODIFIED_Z_MAD(>=3.5) | PROFILE_PEER_3SIGMA_OUTLIER | UNTRUSTED_NEW_DEVICE | HIGH_RISK_MCC(4829) | NIGHT_OWL_01H_05H_UNTRUSTED |
| `TXN-002470` | `USR-0067` | `SME_CORPORATE` | **11,492.14** | 4,662.05 | 966.01 | **`+7.07σ`** | `+9.08` | `CREDIT_CARD_VIRTUAL_CNP` | **`100.0`** | `CRITICAL_FRAUD_ALERT` | Z_SCORE_EXTREME(>=4.2) | MODIFIED_Z_MAD(>=3.5) | PROFILE_PEER_3SIGMA_OUTLIER | UNTRUSTED_NEW_DEVICE | HIGH_RISK_MCC(4829) | VELOCITY_BURST(2.0min) |