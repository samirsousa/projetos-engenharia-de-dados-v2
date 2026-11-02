# Relatório Executivo: Social Media Sentiment, Engajamento & NPS Analytics (PT-BR)

## 1. Sumário Executivo Global de Satisfação e Engajamento

| Indicador Analítico (NLP & Social Analytics) | Valor Consolidado | Observação Técnica |
| :--- | ---: | :--- |
| **Total de Avaliações Processadas (JSON)** | `1,250` | Textos limpos e tokenizados em PT-BR |
| **Proporção de Sentimentos Positivos** | **`63.36%`** (`792`) | Compound Polarity `>= +0.15` |
| **Proporção de Sentimentos Neutros** | `9.68%` (`121`) | Compound Polarity em `(-0.15, +0.15)` |
| **Proporção de Sentimentos Negativos** | **`26.96%`** (`337`) | Compound Polarity `<= -0.15` |
| **NPS Simulado Global (Net Promoter Score)** | **`+36.40`** | Promotores: `792` / Detratores: `337` |
| **Polaridade Composta Média** | `+0.3487` | Escala normalizada `[-1.0, +1.0]` |
| **Avaliações com Inversão por Negação (`não/nunca`)** | `237` | Tratadas por janela contextual de 3 tokens |
| **Alcance Total (Impressões nas Redes)** | `8,164,737` | Soma nos 5 canais sociais/reviews |
| **Total de Interações (Likes/Comments/Shares/Saves)** | `859,950` | Taxa Média de Engajamento: `10.59%` |

---

## 2. Consolidação por Categoria de Produto (`mart_category_satisfaction_nps`)

| Categoria ID | Categoria de Produto | Reviews | % Positivo | % Neutro | % Negativo | Saldo Líquido | % Promotores | % Detratores | NPS Simulado | Zona de Qualidade NPS | Taxa Engajamento % |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- | ---: |
| `CAT-COMPUTING` | **Notebooks & Hardware Gamer** | 264 | `74.6%` | `9.8%` | `15.5%` | `+59.1%` | 74.6% | 15.5% | **`+59.1`** | Zona de Excelência (NPS >= 50) | `10.75%` |
| `CAT-SMARTHOME` | **Casa Inteligente & IoT** | 258 | `69.0%` | `10.5%` | `20.5%` | `+48.5%` | 69.0% | 20.5% | **`+48.5`** | Zona de Qualidade (25 a 49) | `10.66%` |
| `CAT-MOBILE` | **Smartphones & Wearables** | 256 | `63.3%` | `7.8%` | `28.9%` | `+34.4%` | 63.3% | 28.9% | **`+34.4`** | Zona de Qualidade (25 a 49) | `10.42%` |
| `CAT-APPLIANCES` | **Eletroportáteis & Café** | 222 | `60.4%` | `9.0%` | `30.6%` | `+29.7%` | 60.4% | 30.6% | **`+29.7`** | Zona de Qualidade (25 a 49) | `10.41%` |
| `CAT-AUDIO` | **Áudio & Fones Bluetooth** | 250 | `48.4%` | `11.2%` | `40.4%` | `+8.0%` | 48.4% | 40.4% | **`+8.0`** | Zona de Aperfeiçoamento (0 a 24) | `10.70%` |

---

## 3. Ranking de Sentimento e NPS por Produto SKU (`mart_product_sentiment_ranking`)

| SKU ID | Produto | Categoria | Preço (R$) | Reviews | % Positivo | % Negativo | NPS Simulado | Polaridade Média | Engajamento % |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `PRD-NB-01` | **Notebook TitanBook Ultra RTX 16GB** | Notebooks & Hardware Gamer | 6,499.00 | 130 | `75.4%` | `14.6%` | **`+60.8`** | `+0.570` | `10.64%` |
| `PRD-IOT-01` | **Robô Aspirador SmartClean Laser LiDAR** | Casa Inteligente & IoT | 2,199.00 | 113 | `74.3%` | `16.8%` | **`+57.5`** | `+0.554` | `10.29%` |
| `PRD-NB-02` | **Monitor Curvo 165Hz IPS 27 Pol** | Notebooks & Hardware Gamer | 1,599.00 | 134 | `73.9%` | `16.4%` | **`+57.5`** | `+0.541` | `10.86%` |
| `PRD-SM-01` | **Smartphone Horizon Pro 5G 256GB** | Smartphones & Wearables | 3,899.00 | 132 | `68.9%` | `22.7%` | **`+46.2`** | `+0.437` | `10.56%` |
| `PRD-IOT-02` | **Fechadura Digital Biometria Wi-Fi** | Casa Inteligente & IoT | 799.00 | 145 | `64.8%` | `23.4%` | **`+41.4`** | `+0.393` | `10.95%` |
| `PRD-CAF-02` | **AirFryer Digital Oven Inox 12L** | Eletroportáteis & Café | 749.00 | 125 | `63.2%` | `26.4%` | **`+36.8`** | `+0.347` | `10.35%` |
| `PRD-AU-02` | **Caixa de Som BoomBox Waterproof 60W** | Áudio & Fones Bluetooth | 699.00 | 127 | `58.3%` | `30.7%` | **`+27.6`** | `+0.272` | `10.49%` |
| `PRD-SM-02` | **Smartwatch PulseFit AMOLED GPS** | Smartphones & Wearables | 899.00 | 124 | `57.3%` | `35.5%` | **`+21.8`** | `+0.218` | `10.28%` |
| `PRD-CAF-01` | **Cafeteira Espresso Barista Pro 19 Bar** | Eletroportáteis & Café | 1,299.00 | 97 | `56.7%` | `36.1%` | **`+20.6`** | `+0.193` | `10.48%` |
| `PRD-AU-01` | **Fone Bluetooth SonicPods ANC** | Áudio & Fones Bluetooth | 449.00 | 123 | `38.2%` | `50.4%` | **`-12.2`** | `-0.094` | `10.92%` |

---

## 4. Desempenho por Canal Social / Plataforma (`mart_channel_engagement_performance`)

| Canal ID | Plataforma / Canal | Tipo | Reviews | Impressões | Interações | Engajamento Ponderado | Taxa Engajamento % | % Positivo | % Negativo | NPS Simulado |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `CH-TK` | **TikTok Shop & Creators** | Short-Form Video | 246 | 2,952,122 | 303,688 | 2,298.7 | **`10.33%`** | `63.8%` | `27.2%` | **`+36.6`** |
| `CH-IG` | **Instagram Reels & Feed** | Social Video/Photo | 244 | 1,933,806 | 211,763 | 1,609.9 | **`10.87%`** | `63.5%` | `26.2%` | **`+37.3`** |
| `CH-YT` | **YouTube Tech Reviews** | Long-Form Video | 244 | 1,617,780 | 166,860 | 1,269.7 | **`10.33%`** | `59.8%` | `31.6%` | **`+28.3`** |
| `CH-TW` | **X / Twitter Mentions** | Microblogging | 268 | 1,210,557 | 129,440 | 897.5 | **`10.62%`** | `64.9%` | `26.1%` | **`+38.8`** |
| `CH-EC` | **E-Commerce Verified Reviews** | Marketplace Portal | 248 | 450,472 | 48,199 | 357.7 | **`10.82%`** | `64.5%` | `23.8%` | **`+40.7`** |

---

## 5. Top 15 Termos do Léxico de Polaridade PT-BR Extraídos (`mart_lexicon_term_impact`)

| Termo Normalizado (PT-BR) | Orientação Léxica | Peso Base no Dicionário | Ocorrências no Corpus | % das Menções Léxicas |
| :--- | :--- | ---: | ---: | ---: |
| `rapido` | `POSITIVE_TERM` | `+1.7` | **357** | `5.43%` |
| `excelente` | `POSITIVE_TERM` | `+2.8` | **299** | `4.54%` |
| `impecavel` | `POSITIVE_TERM` | `+2.8` | **255** | `3.88%` |
| `recomendo` | `POSITIVE_TERM` | `+2.3` | **176** | `2.67%` |
| `estavel` | `POSITIVE_TERM` | `+1.7` | **176** | `2.67%` |
| `comum` | `NEUTRAL_TERM` | `+0.0` | **160** | `2.43%` |
| `perfeito` | `POSITIVE_TERM` | `+2.9` | **157** | `2.39%` |
| `pratico` | `POSITIVE_TERM` | `+1.6` | **157** | `2.39%` |
| `silencioso` | `POSITIVE_TERM` | `+1.6` | **157** | `2.39%` |
| `eficiente` | `POSITIVE_TERM` | `+1.8` | **157** | `2.39%` |
| `nota10` | `POSITIVE_TERM` | `+2.7` | **157** | `2.39%` |
| `sensacional` | `POSITIVE_TERM` | `+2.7` | **133** | `2.02%` |
| `trava` | `NEGATIVE_TERM` | `-2.2` | **133** | `2.02%` |
| `recomendadissimo` | `POSITIVE_TERM` | `+2.9` | **133** | `2.02%` |
| `surpreendente` | `POSITIVE_TERM` | `+2.4` | **131** | `1.99%` |