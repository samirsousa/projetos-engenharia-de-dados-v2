# Relatório Executivo: ETL Geoespacial, Densidade de Entregas e Gargalos Logísticos

## 1. Sumário Executivo da Malha Logística Nacional

| Indicador Geoespacial / Logístico | Valor Consolidado | Observação Técnica |
| :--- | ---: | :--- |
| **Remessas Válidas Processadas (Gold)** | `949` | Coordenadas validadas em WGS-84 |
| **Coordenadas Invertidas Recuperadas (Auto-Healed)** | `8` | Correção automática Lat/Lon Swap |
| **Registros em Quarentena Espacial** | `11` | Null Island `(0,0)` ou fora do Bounding Box |
| **Peso Total Transportado** | `13,811.05 t` | Carga líquida movimentada |
| **Momento de Transporte Total (TKU)** | `15,757,506.00 t·km` | Tonelada-quilômetro útil rodoviária |
| **Distância Geodésica Média (Haversine)** | `641.03 km` | Linha reta esférica sobre WGS-84 |
| **Distância Rodoviária Estimada Média** | `859.58 km` | Ajustada pelo índice de tortuosidade ($\kappa$) |
| **Velocidade Efetiva Média de Trânsito** | `47.03 km/h` | Descontado tempo de pátio/doca |
| **Taxa Global OTIF (On-Time In-Full)** | `70.07%` | Entregas dentro do SLA prometido |
| **Taxa Global de Violação de SLA** | `29.93%` | Remessas impactadas por gargalos |
| **Custo Operacional Estimado de Frete** | `R$ 6,777,983.07` | Baseado em R$/t·km por modal |
| **Pegada de Carbono Estimada (Escopo 1/3)** | `777.17 t CO2e` | Emissões do transporte de cargas |

---

## 2. Densidade de Entregas por Polo Regional (Top 14 Zonas)

| Zona ID | Polo / Cidade | UF | Região | Área (km²) | Entregas | Carga (t) | Densidade (Entregas / 1.000 km²) | Densidade Carga (t/km²) | OTIF % | LBI Regional | Classificação Espacial |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| `ZN-SP-CPS` | **Campinas** | SP | Sudeste | 795 | 89 | 570.6 | **`111.95`** | 0.718 | `89.9%` | `10.9` | HIGH_DENSITY_METROPOLITAN_CORE |
| `ZN-MG-BHZ` | **Belo Horizonte** | MG | Sudeste | 950 | 95 | 1,539.1 | **`100.00`** | 1.620 | `71.6%` | `24.9` | HIGH_DENSITY_METROPOLITAN_CORE |
| `ZN-SP-CAP` | **São Paulo** | SP | Sudeste | 1,521 | 140 | 986.8 | **`92.04`** | 0.649 | `70.7%` | `22.4` | HIGH_DENSITY_METROPOLITAN_CORE |
| `ZN-RJ-CAP` | **Rio de Janeiro** | RJ | Sudeste | 1,200 | 90 | 1,309.7 | **`75.00`** | 1.091 | `61.1%` | `30.7` | HIGH_DENSITY_METROPOLITAN_CORE |
| `ZN-PR-CWB` | **Curitiba** | PR | Sul | 850 | 63 | 511.8 | **`74.12`** | 0.602 | `74.6%` | `21.7` | MEDIUM_DENSITY_REGIONAL_POLE |
| `ZN-RS-POA` | **Porto Alegre** | RS | Sul | 1,100 | 78 | 1,530.9 | **`70.91`** | 1.392 | `79.5%` | `20.9` | MEDIUM_DENSITY_REGIONAL_POLE |
| `ZN-BA-SSA` | **Salvador** | BA | Nordeste | 1,050 | 71 | 1,606.7 | **`67.62`** | 1.530 | `56.3%` | `36.1` | MEDIUM_DENSITY_REGIONAL_POLE |
| `ZN-SC-FLN` | **Florianópolis / Itajaí** | SC | Sul | 920 | 61 | 946.5 | **`66.30`** | 1.029 | `72.1%` | `20.6` | MEDIUM_DENSITY_REGIONAL_POLE |
| `ZN-CE-FOR` | **Fortaleza** | CE | Nordeste | 960 | 62 | 1,467.1 | **`64.58`** | 1.528 | `62.9%` | `34.0` | MEDIUM_DENSITY_REGIONAL_POLE |
| `ZN-PE-REC` | **Recife** | PE | Nordeste | 880 | 48 | 549.6 | **`54.55`** | 0.625 | `64.6%` | `29.4` | MEDIUM_DENSITY_REGIONAL_POLE |
| `ZN-DF-BSB` | **Brasília** | DF | Centro-Oeste | 1,350 | 45 | 762.5 | **`33.33`** | 0.565 | `86.7%` | `15.9` | LOW_DENSITY_LONG_HAUL_FRONTIER |
| `ZN-PA-BEL` | **Belém** | PA | Norte | 1,250 | 41 | 758.8 | **`32.80`** | 0.607 | `48.8%` | `41.6` | LOW_DENSITY_LONG_HAUL_FRONTIER |
| `ZN-MT-CGB` | **Cuiabá** | MT | Centro-Oeste | 1,400 | 40 | 763.7 | **`28.57`** | 0.545 | `77.5%` | `24.4` | LOW_DENSITY_LONG_HAUL_FRONTIER |
| `ZN-AM-MAO` | **Manaus (Rodofluvial)** | AM | Norte | 1,800 | 26 | 507.4 | **`14.44`** | 0.282 | `38.5%` | `41.1` | LOW_DENSITY_LONG_HAUL_FRONTIER |

---

## 3. Ranking de Gargalos Logísticos por Corredor (Top 15 Rotas Críticas)

| Corredor ID | Origem -> Destino | Região Destino | Viagens | Haversine (km) | Rodoviário (km) | Doca (h) | Vel. Efetiva (km/h) | Violação SLA % | Índice Gargalo (LBI) | Severidade | Causa Raiz Predominante |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- | :--- |
| `HUB-GO-ANP->ZN-CE-FOR` | Anápolis/GO → **Fortaleza/CE** | Nordeste | 1 | 1,803.5 | 2,380.6 | 6.8h | 31.9 | `100.0%` | **`92.65`** | `CRITICAL_BOTTLENECK` | Port / Fiscal Barrier Inspection (SEFAZ Posto Fiscal) |
| `HUB-MG-EXT->ZN-PR-CWB` | Extrema/MG → **Curitiba/PR** | Sul | 1 | 431.3 | 521.9 | 6.6h | 23.2 | `100.0%` | **`75.60`** | `CRITICAL_BOTTLENECK` | Urban Ring-Road Congestion (Marginal / Av. Brasil) |
| `HUB-PE-REC->ZN-AM-MAO` | Cabo de Santo Agostinho/PE → **Manaus (Rodofluvial)/AM** | Norte | 1 | 2,819.4 | 4,285.5 | 8.8h | 34.8 | `100.0%` | **`68.88`** | `CRITICAL_BOTTLENECK` | Ferry / Rodofluvial Barge Wait Time |
| `HUB-PE-REC->ZN-PR-CWB` | Cabo de Santo Agostinho/PE → **Curitiba/PR** | Sul | 3 | 2,433.4 | 2,944.4 | 8.3h | 36.1 | `100.0%` | **`66.00`** | `CRITICAL_BOTTLENECK` | Dock Queue Overload at Origin/Destination |
| `HUB-PE-REC->ZN-SC-FLN` | Cabo de Santo Agostinho/PE → **Florianópolis / Itajaí/SC** | Sul | 2 | 2,591.3 | 3,265.1 | 6.6h | 38.7 | `100.0%` | **`55.34`** | `CRITICAL_BOTTLENECK` | Port / Fiscal Barrier Inspection (SEFAZ Posto Fiscal) |
| `HUB-PR-CWB->ZN-PA-BEL` | Araucária/PR → **Belém/PA** | Norte | 2 | 2,675.6 | 3,852.8 | 5.5h | 38.7 | `50.0%` | **`54.95`** | `CRITICAL_BOTTLENECK` | Ferry / Rodofluvial Barge Wait Time |
| `HUB-MG-EXT->ZN-PA-BEL` | Extrema/MG → **Belém/PA** | Norte | 9 | 2,387.0 | 3,437.3 | 5.4h | 38.5 | `77.8%` | **`53.22`** | `CRITICAL_BOTTLENECK` | Port / Fiscal Barrier Inspection (SEFAZ Posto Fiscal) |
| `HUB-PR-CWB->ZN-BA-SSA` | Araucária/PR → **Salvador/BA** | Nordeste | 4 | 1,800.9 | 2,413.2 | 5.0h | 38.3 | `75.0%` | **`52.45`** | `CRITICAL_BOTTLENECK` | Dock Queue Overload at Origin/Destination |
| `HUB-GO-ANP->ZN-RJ-CAP` | Anápolis/GO → **Rio de Janeiro/RJ** | Sudeste | 3 | 955.8 | 1,233.0 | 6.3h | 41.5 | `66.7%` | **`51.04`** | `CRITICAL_BOTTLENECK` | Urban Ring-Road Congestion (Marginal / Av. Brasil) |
| `HUB-SP-CAJ->ZN-AM-MAO` | Cajamar/SP → **Manaus (Rodofluvial)/AM** | Norte | 10 | 2,662.8 | 4,047.4 | 4.7h | 39.4 | `70.0%` | **`49.00`** | `CRITICAL_BOTTLENECK` | Dock Queue Overload at Origin/Destination |
| `HUB-PR-CWB->ZN-PE-REC` | Araucária/PR → **Recife/PE** | Nordeste | 3 | 2,478.2 | 3,172.1 | 5.1h | 42.2 | `66.7%` | **`48.91`** | `CRITICAL_BOTTLENECK` | Dock Queue Overload at Origin/Destination |
| `HUB-PE-REC->ZN-SP-CAP` | Cabo de Santo Agostinho/PE → **São Paulo/SP** | Sudeste | 5 | 2,098.5 | 2,602.2 | 6.0h | 41.3 | `60.0%` | **`46.41`** | `CRITICAL_BOTTLENECK` | Port / Fiscal Barrier Inspection (SEFAZ Posto Fiscal) |
| `HUB-PR-CWB->ZN-AM-MAO` | Araucária/PR → **Manaus (Rodofluvial)/AM** | Norte | 1 | 2,747.9 | 4,176.8 | 4.9h | 38.3 | `100.0%` | **`44.44`** | `CRITICAL_BOTTLENECK` | Severe Weather / Serra Highway Speed Restriction |
| `HUB-GO-ANP->ZN-PA-BEL` | Anápolis/GO → **Belém/PA** | Norte | 7 | 1,658.1 | 2,387.6 | 5.9h | 42.3 | `57.1%` | **`42.98`** | `CRITICAL_BOTTLENECK` | Port / Fiscal Barrier Inspection (SEFAZ Posto Fiscal) |
| `HUB-PR-CWB->ZN-RJ-CAP` | Araucária/PR → **Rio de Janeiro/RJ** | Sudeste | 5 | 700.2 | 903.3 | 4.6h | 43.3 | `60.0%` | **`40.28`** | `CRITICAL_BOTTLENECK` | Port / Fiscal Barrier Inspection (SEFAZ Posto Fiscal) |

---

## 4. Auditoria de Quarentena Geoespacial (Anomalias Bloqueadas)

| Shipment ID | Hub Origem | Zona Destino | Lat Destino Bruta | Lon Destino Bruta | Peso (kg) | Motivo de Bloqueio |
| :--- | :--- | :--- | ---: | ---: | ---: | :--- |
| `SHP-00037` | `HUB-PR-CWB` | `ZN-PE-REC` | -7.997598 | -34.747047 | 33,402.0 | `QUARANTINED_OUT_OF_BRAZIL_BOUNDS` |
| `SHP-00099` | `HUB-SP-CAJ` | `ZN-SP-CAP` | 0.0 | 0.0 | 2,432.2 | `QUARANTINED_NULL_ISLAND_ZERO_COORD` |
| `SHP-00299` | `HUB-MG-EXT` | `ZN-RJ-CAP` | 0.0 | 0.0 | 6,813.2 | `QUARANTINED_NULL_ISLAND_ZERO_COORD` |
| `SHP-00499` | `HUB-SP-CAJ` | `ZN-MT-CGB` | 0.0 | 0.0 | 23,362.9 | `QUARANTINED_NULL_ISLAND_ZERO_COORD` |
| `SHP-00589` | `HUB-PE-REC` | `ZN-PE-REC` | -8.134031 | -34.742576 | 9,805.5 | `QUARANTINED_OUT_OF_BRAZIL_BOUNDS` |
| `SHP-00664` | `HUB-MG-EXT` | `ZN-PE-REC` | -8.043587 | -34.747036 | 20,105.9 | `QUARANTINED_OUT_OF_BRAZIL_BOUNDS` |
| `SHP-00699` | `HUB-MG-EXT` | `ZN-SP-CAP` | 0.0 | 0.0 | 23,015.1 | `QUARANTINED_NULL_ISLAND_ZERO_COORD` |
| `SHP-00702` | `HUB-PE-REC` | `ZN-PE-REC` | -8.138531 | -34.752821 | 16,640.1 | `QUARANTINED_OUT_OF_BRAZIL_BOUNDS` |
| `SHP-00795` | `HUB-PE-REC` | `ZN-PE-REC` | -8.065341 | -34.729445 | 7,430.7 | `QUARANTINED_OUT_OF_BRAZIL_BOUNDS` |
| `SHP-00899` | `HUB-SP-CAJ` | `ZN-MG-BHZ` | 0.0 | 0.0 | 9,756.4 | `QUARANTINED_NULL_ISLAND_ZERO_COORD` |
| `SHP-00950` | `HUB-SP-CAJ` | `ZN-SP-CAP` | 0.0 | 0.0 | 2,064.2 | `QUARANTINED_NULL_ISLAND_ZERO_COORD` |