"""
Gerador de Portal HTML Público Simulado (Boletim Macroeconômico BCB / IBGE / FGV).

Gera páginas HTML5 realistas com tabelas DOM contendo formatação brasileira,
notas de rodapé `(*)`, símbolos monetários (`R$`), percentuais (`% a.a.`),
linhas de cabeçalho mescladas, valores ausentes (`N/D`, `-`) e arquivo `robots.txt`
para validação determinística de Web Scraping ético offline e em CI/CD.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from src.config import ScrapingPipelineConfig


ROBOTS_TXT_CONTENT = """# Portal de Dados Abertos Macroeconômicos - Política de Crawling Ético
User-agent: *
Allow: /boletim_focus_sgs.html
Allow: /cambio_ptax_series.html
Disallow: /admin/
Disallow: /private-api/
Crawl-delay: 1
"""


BOLETIM_MACRO_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Boletim de Indicadores Macroeconômicos Nacionais (BCB / IBGE / FGV)</title>
</head>
<body>
    <header>
        <h1>Portal Público de Séries Temporais Macroeconômicas</h1>
        <p class="publish-meta">Fonte: Sistema Gerenciador de Séries Temporais (SGS/BCB) &amp; SIDRA/IBGE</p>
    </header>

    <main>
        <table id="macro-indicators-table" class="data-grid">
            <thead>
                <tr>
                    <th>Código Série</th>
                    <th>Indicador Econômico</th>
                    <th>Instituição Fonte</th>
                    <th>Data de Referência</th>
                    <th>Valor Bruto Divulgado</th>
                    <th>Unidade</th>
                    <th>Periodicidade</th>
                    <th>Status Publicação</th>
                </tr>
            </thead>
            <tbody>
                <!-- Série Histórica: Taxa SELIC Meta (SGS 432) -->
                <tr data-series="432">
                    <td> SELIC_META </td>
                    <td>Taxa de Juros SELIC (Meta COPOM)</td>
                    <td>Banco Central do Brasil (BCB)</td>
                    <td>01/08/2026</td>
                    <td>10,50 % a.a.</td>
                    <td>PCT_AA</td>
                    <td>MONTHLY</td>
                    <td>DEFINITIVO</td>
                </tr>
                <tr data-series="432">
                    <td>SELIC_META</td>
                    <td>Taxa de Juros SELIC (Meta COPOM)</td>
                    <td>Banco Central do Brasil (BCB)</td>
                    <td>01/09/2026</td>
                    <td>10,75% a.a. (*)</td>
                    <td>PCT_AA</td>
                    <td>MONTHLY</td>
                    <td>DEFINITIVO</td>
                </tr>
                <tr data-series="432">
                    <td>SELIC_META</td>
                    <td>Taxa de Juros SELIC (Meta COPOM)</td>
                    <td>Banco Central do Brasil (BCB)</td>
                    <td>01/10/2026</td>
                    <td>11,00 % a.a.</td>
                    <td>PCT_AA</td>
                    <td>MONTHLY</td>
                    <td>DEFINITIVO</td>
                </tr>
                <tr data-series="432">
                    <td>SELIC_META</td>
                    <td>Taxa de Juros SELIC (Meta COPOM)</td>
                    <td>Banco Central do Brasil (BCB)</td>
                    <td>01/11/2026</td>
                    <td>11,25% a.a. [1]</td>
                    <td>PCT_AA</td>
                    <td>MONTHLY</td>
                    <td>DEFINITIVO</td>
                </tr>

                <!-- Série Histórica: IPCA Acumulado 12 Meses (IBGE) -->
                <tr data-series="13522">
                    <td>IPCA_ACUM_12M</td>
                    <td>IPCA - Inflação Oficial Acumulada 12 Meses</td>
                    <td>IBGE</td>
                    <td>2026-08-01</td>
                    <td>4,24 %</td>
                    <td>PCT_12M</td>
                    <td>MONTHLY</td>
                    <td>DEFINITIVO</td>
                </tr>
                <tr data-series="13522">
                    <td>IPCA_ACUM_12M</td>
                    <td>IPCA - Inflação Oficial Acumulada 12 Meses</td>
                    <td>IBGE</td>
                    <td>2026-09-01</td>
                    <td>4,42%</td>
                    <td>PCT_12M</td>
                    <td>MONTHLY</td>
                    <td>DEFINITIVO</td>
                </tr>
                <tr data-series="13522">
                    <td>IPCA_ACUM_12M</td>
                    <td>IPCA - Inflação Oficial Acumulada 12 Meses</td>
                    <td>IBGE</td>
                    <td>2026-10-01</td>
                    <td>4,58 % (*)</td>
                    <td>PCT_12M</td>
                    <td>MONTHLY</td>
                    <td>DEFINITIVO</td>
                </tr>
                <tr data-series="13522">
                    <td>IPCA_ACUM_12M</td>
                    <td>IPCA - Inflação Oficial Acumulada 12 Meses</td>
                    <td>IBGE</td>
                    <td>2026-11-01</td>
                    <td>4,65% [preliminar]</td>
                    <td>PCT_12M</td>
                    <td>MONTHLY</td>
                    <td>PRELIMINAR</td>
                </tr>

                <!-- Série Histórica: IGP-M (FGV IBRE) -->
                <tr data-series="189">
                    <td>IGPM_ACUM_12M</td>
                    <td>IGP-M - Índice Geral de Preços do Mercado (12m)</td>
                    <td>FGV IBRE</td>
                    <td>01/09/2026</td>
                    <td>4,89 %</td>
                    <td>PCT_12M</td>
                    <td>MONTHLY</td>
                    <td>DEFINITIVO</td>
                </tr>
                <tr data-series="189">
                    <td>IGPM_ACUM_12M</td>
                    <td>IGP-M - Índice Geral de Preços do Mercado (12m)</td>
                    <td>FGV IBRE</td>
                    <td>01/10/2026</td>
                    <td>5,12 %</td>
                    <td>PCT_12M</td>
                    <td>MONTHLY</td>
                    <td>DEFINITIVO</td>
                </tr>
                <tr data-series="189">
                    <td>IGPM_ACUM_12M</td>
                    <td>IGP-M - Índice Geral de Preços do Mercado (12m)</td>
                    <td>FGV IBRE</td>
                    <td>01/11/2026</td>
                    <td>5,34%</td>
                    <td>PCT_12M</td>
                    <td>MONTHLY</td>
                    <td>DEFINITIVO</td>
                </tr>

                <!-- Série Histórica: Taxa de Desemprego PNAD Contínua (IBGE) -->
                <tr data-series="24369">
                    <td>DESEMPREGO_PNAD</td>
                    <td>Taxa de Desocupação PNAD Contínua</td>
                    <td>IBGE</td>
                    <td>01/09/2026</td>
                    <td>6,7 %</td>
                    <td>PCT_PEA</td>
                    <td>MONTHLY</td>
                    <td>DEFINITIVO</td>
                </tr>
                <tr data-series="24369">
                    <td>DESEMPREGO_PNAD</td>
                    <td>Taxa de Desocupação PNAD Contínua</td>
                    <td>IBGE</td>
                    <td>01/10/2026</td>
                    <td>6,5%</td>
                    <td>PCT_PEA</td>
                    <td>MONTHLY</td>
                    <td>DEFINITIVO</td>
                </tr>
                <tr data-series="24369">
                    <td>DESEMPREGO_PNAD</td>
                    <td>Taxa de Desocupação PNAD Contínua</td>
                    <td>IBGE</td>
                    <td>01/11/2026</td>
                    <td>6,4 % (*)</td>
                    <td>PCT_PEA</td>
                    <td>MONTHLY</td>
                    <td>PRELIMINAR</td>
                </tr>

                <!-- Série Histórica: IBC-Br Índice de Atividade Econômica (BCB) -->
                <tr data-series="24364">
                    <td>IBC_BR_INDICE</td>
                    <td>IBC-Br - Índice de Atividade Econômica do Banco Central</td>
                    <td>Banco Central do Brasil (BCB)</td>
                    <td>01/09/2026</td>
                    <td>151,40 pts</td>
                    <td>INDEX_PTS</td>
                    <td>MONTHLY</td>
                    <td>DEFINITIVO</td>
                </tr>
                <tr data-series="24364">
                    <td>IBC_BR_INDICE</td>
                    <td>IBC-Br - Índice de Atividade Econômica do Banco Central</td>
                    <td>Banco Central do Brasil (BCB)</td>
                    <td>01/10/2026</td>
                    <td>152,85 pts</td>
                    <td>INDEX_PTS</td>
                    <td>MONTHLY</td>
                    <td>DEFINITIVO</td>
                </tr>
                <tr data-series="24364">
                    <td>IBC_BR_INDICE</td>
                    <td>IBC-Br - Índice de Atividade Econômica do Banco Central</td>
                    <td>Banco Central do Brasil (BCB)</td>
                    <td>01/11/2026</td>
                    <td>153,60 pts [1]</td>
                    <td>INDEX_PTS</td>
                    <td>MONTHLY</td>
                    <td>PRELIMINAR</td>
                </tr>

                <!-- Série Histórica: Dívida Bruta do Governo Geral (% PIB) -->
                <tr data-series="13762">
                    <td>DIVIDA_BRUTA_PIB</td>
                    <td>Dívida Bruta do Governo Geral (% do PIB)</td>
                    <td>Banco Central do Brasil (BCB)</td>
                    <td>01/10/2026</td>
                    <td>77,8 % do PIB</td>
                    <td>PCT_PIB</td>
                    <td>MONTHLY</td>
                    <td>DEFINITIVO</td>
                </tr>
                <tr data-series="13762">
                    <td>DIVIDA_BRUTA_PIB</td>
                    <td>Dívida Bruta do Governo Geral (% do PIB)</td>
                    <td>Banco Central do Brasil (BCB)</td>
                    <td>01/11/2026</td>
                    <td>78,2% do PIB</td>
                    <td>PCT_PIB</td>
                    <td>MONTHLY</td>
                    <td>PRELIMINAR</td>
                </tr>

                <!-- Ruído Realista de HTML Público: Linha com valor "N/D" (Não Disponível) que o Transformer deve filtrar -->
                <tr data-series="99999">
                    <td>IBC_BR_INDICE</td>
                    <td>IBC-Br - Prévia Mensal Não Consolidada</td>
                    <td>Banco Central do Brasil (BCB)</td>
                    <td>01/12/2026</td>
                    <td>N/D (*)</td>
                    <td>INDEX_PTS</td>
                    <td>MONTHLY</td>
                    <td>AGUARDANDO_DIVULGACAO</td>
                </tr>
            </tbody>
        </table>
    </main>
</body>
</html>
"""


CAMBIO_PTAX_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Boletim Diário de Taxas de Câmbio PTAX (USD/BRL e EUR/BRL)</title>
</head>
<body>
    <main>
        <table id="macro-indicators-table" class="ptax-grid">
            <thead>
                <tr>
                    <th>Código Série</th>
                    <th>Indicador Econômico</th>
                    <th>Instituição Fonte</th>
                    <th>Data de Referência</th>
                    <th>Valor Bruto Divulgado</th>
                    <th>Unidade</th>
                    <th>Periodicidade</th>
                    <th>Status Publicação</th>
                </tr>
            </thead>
            <tbody>
                <tr data-series="1">
                    <td>PTAX_USD_BRL</td>
                    <td>Taxa de Câmbio PTAX Dólar Americano (Venda)</td>
                    <td>Banco Central do Brasil (BCB)</td>
                    <td>01/09/2026</td>
                    <td>R$ 5,6120</td>
                    <td>BRL</td>
                    <td>MONTHLY</td>
                    <td>DEFINITIVO</td>
                </tr>
                <tr data-series="1">
                    <td>PTAX_USD_BRL</td>
                    <td>Taxa de Câmbio PTAX Dólar Americano (Venda)</td>
                    <td>Banco Central do Brasil (BCB)</td>
                    <td>01/10/2026</td>
                    <td>R$ 5,6890</td>
                    <td>BRL</td>
                    <td>MONTHLY</td>
                    <td>DEFINITIVO</td>
                </tr>
                <tr data-series="1">
                    <td>PTAX_USD_BRL</td>
                    <td>Taxa de Câmbio PTAX Dólar Americano (Venda)</td>
                    <td>Banco Central do Brasil (BCB)</td>
                    <td>01/11/2026</td>
                    <td>R$ 5,7450 (*)</td>
                    <td>BRL</td>
                    <td>MONTHLY</td>
                    <td>DEFINITIVO</td>
                </tr>
                <tr data-series="21619">
                    <td>PTAX_EUR_BRL</td>
                    <td>Taxa de Câmbio PTAX Euro (Venda)</td>
                    <td>Banco Central do Brasil (BCB)</td>
                    <td>01/09/2026</td>
                    <td>R$ 6,1840</td>
                    <td>BRL</td>
                    <td>MONTHLY</td>
                    <td>DEFINITIVO</td>
                </tr>
                <tr data-series="21619">
                    <td>PTAX_EUR_BRL</td>
                    <td>Taxa de Câmbio PTAX Euro (Venda)</td>
                    <td>Banco Central do Brasil (BCB)</td>
                    <td>01/10/2026</td>
                    <td>R$ 6,2410</td>
                    <td>BRL</td>
                    <td>MONTHLY</td>
                    <td>DEFINITIVO</td>
                </tr>
                <tr data-series="21619">
                    <td>PTAX_EUR_BRL</td>
                    <td>Taxa de Câmbio PTAX Euro (Venda)</td>
                    <td>Banco Central do Brasil (BCB)</td>
                    <td>01/11/2026</td>
                    <td>R$ 6,2980</td>
                    <td>BRL</td>
                    <td>MONTHLY</td>
                    <td>DEFINITIVO</td>
                </tr>
            </tbody>
        </table>
    </main>
</body>
</html>
"""


def materialize_mock_portal(config: ScrapingPipelineConfig) -> Tuple[Path, Path, Path]:
    """Grava os arquivos HTML e robots.txt do portal macroeconômico local."""
    config.ensure_directories()
    robots_path = config.html_portal_dir / "robots.txt"
    boletim_path = config.html_portal_dir / "boletim_focus_sgs.html"
    ptax_path = config.html_portal_dir / "cambio_ptax_series.html"

    robots_path.write_text(ROBOTS_TXT_CONTENT, encoding="utf-8")
    boletim_path.write_text(BOLETIM_MACRO_HTML, encoding="utf-8")
    ptax_path.write_text(CAMBIO_PTAX_HTML, encoding="utf-8")

    return robots_path, boletim_path, ptax_path
