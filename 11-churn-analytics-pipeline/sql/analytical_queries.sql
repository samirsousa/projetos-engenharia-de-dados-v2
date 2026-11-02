-- =============================================================================
-- PROJETO 11: CUSTOMER CHURN & RETENTION ANALYTICS (END-TO-END)
-- Consultas Analíticas Avançadas em SQL (CTEs & Window Functions)
-- =============================================================================
-- Este arquivo contém a modelagem analítica para:
--   1. Taxa de Churn Mensal (Logo Churn %, Gross MRR Churn %, Net MRR Churn %, GRR % e NRR %)
--   2. Análise de Coorte de Retenção (Cohort Retention Analysis - Clientes e Receita M0..M11)
--   3. Lifetime Value (LTV Teórico, LTV Observado Acumulado, CAC, LTV:CAC e Payback Period)
--   4. Diagnóstico de Motivos de Cancelamento & Risco de Saúde de Produto
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. MONTHLY SAAS CHURN & MRR BRIDGE KPIs (mart_monthly_churn_kpis)
-- Calcula o MRR Bridge completo (Beginning MRR, New, Expansion, Contraction,
-- Churned, Ending MRR) usando Window Functions (LAG) e taxas de Churn e Retenção.
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS mart_monthly_churn_kpis;

CREATE TABLE mart_monthly_churn_kpis AS
WITH monthly_movements AS (
    SELECT
        snapshot_month,
        -- Clientes ativos no encerramento do mês
        SUM(CASE WHEN active_flag = 1 THEN 1 ELSE 0 END) AS ending_active_customers,
        -- Novos clientes adquiridos no mês (M0)
        SUM(CASE WHEN movement_type = 'NEW' THEN 1 ELSE 0 END) AS new_customers,
        -- Clientes que cancelaram no mês
        SUM(CASE WHEN movement_type = 'CHURNED' THEN 1 ELSE 0 END) AS churned_customers,
        -- Clientes que expandiram ou contraíram
        SUM(CASE WHEN movement_type = 'EXPANSION' THEN 1 ELSE 0 END) AS expanded_customers,
        SUM(CASE WHEN movement_type = 'CONTRACTION' THEN 1 ELSE 0 END) AS contracted_customers,

        -- Componentes do MRR Bridge (R$)
        ROUND(SUM(CASE WHEN movement_type = 'NEW' THEN current_mrr_brl ELSE 0.0 END), 2) AS new_mrr_brl,
        ROUND(SUM(CASE WHEN movement_type = 'EXPANSION' THEN mrr_delta_brl ELSE 0.0 END), 2) AS expansion_mrr_brl,
        ROUND(SUM(CASE WHEN movement_type = 'CONTRACTION' THEN ABS(mrr_delta_brl) ELSE 0.0 END), 2) AS contraction_mrr_brl,
        ROUND(SUM(CASE WHEN movement_type = 'CHURNED' THEN previous_mrr_brl ELSE 0.0 END), 2) AS churned_mrr_brl,
        ROUND(SUM(CASE WHEN active_flag = 1 THEN current_mrr_brl ELSE 0.0 END), 2) AS ending_mrr_brl,
        ROUND(SUM(CASE WHEN active_flag = 1 THEN gross_profit_brl ELSE 0.0 END), 2) AS monthly_gross_profit_brl
    FROM raw_mrr_ledger
    GROUP BY snapshot_month
),
lagged_base AS (
    SELECT
        m.*,
        COALESCE(LAG(ending_active_customers) OVER (ORDER BY snapshot_month), 0) AS beginning_customers,
        COALESCE(LAG(ending_mrr_brl) OVER (ORDER BY snapshot_month), 0.0) AS beginning_mrr_brl
    FROM monthly_movements m
)
SELECT
    snapshot_month,
    beginning_customers,
    new_customers,
    churned_customers,
    expanded_customers,
    contracted_customers,
    ending_active_customers,
    ROUND(beginning_mrr_brl, 2) AS beginning_mrr_brl,
    new_mrr_brl,
    expansion_mrr_brl,
    contraction_mrr_brl,
    churned_mrr_brl,
    ROUND(
        new_mrr_brl + expansion_mrr_brl - contraction_mrr_brl - churned_mrr_brl,
        2
    ) AS net_new_mrr_brl,
    ending_mrr_brl,
    ROUND(ending_mrr_brl * 12.0, 2) AS ending_arr_brl,
    monthly_gross_profit_brl,
    ROUND(
        CASE WHEN ending_active_customers > 0
             THEN ending_mrr_brl / ending_active_customers
             ELSE 0.0
        END, 2
    ) AS arpa_brl,

    -- Logo Churn Rate (%) = Clientes Cancelados no mês t / Clientes Ativos no início do mês t
    ROUND(
        CASE WHEN beginning_customers > 0
             THEN (CAST(churned_customers AS REAL) / beginning_customers) * 100.0
             ELSE 0.0
        END, 2
    ) AS logo_churn_rate_pct,

    -- Logo Retention Rate (%) = 100% - Logo Churn Rate (%)
    ROUND(
        CASE WHEN beginning_customers > 0
             THEN (1.0 - (CAST(churned_customers AS REAL) / beginning_customers)) * 100.0
             ELSE 100.0
        END, 2
    ) AS logo_retention_rate_pct,

    -- Gross MRR Churn Rate (%) = (Churned MRR + Contraction MRR) / Beginning MRR
    ROUND(
        CASE WHEN beginning_mrr_brl > 0
             THEN ((churned_mrr_brl + contraction_mrr_brl) / beginning_mrr_brl) * 100.0
             ELSE 0.0
        END, 2
    ) AS gross_mrr_churn_rate_pct,

    -- Net MRR Churn Rate (%) = (Churned MRR + Contraction MRR - Expansion MRR) / Beginning MRR
    -- Valores negativos indicam Net Negative Churn (Expansão supera perdas!)
    ROUND(
        CASE WHEN beginning_mrr_brl > 0
             THEN ((churned_mrr_brl + contraction_mrr_brl - expansion_mrr_brl) / beginning_mrr_brl) * 100.0
             ELSE 0.0
        END, 2
    ) AS net_mrr_churn_rate_pct,

    -- Gross Revenue Retention - GRR (%)
    ROUND(
        CASE WHEN beginning_mrr_brl > 0
             THEN ((beginning_mrr_brl - churned_mrr_brl - contraction_mrr_brl) / beginning_mrr_brl) * 100.0
             ELSE 100.0
        END, 2
    ) AS grr_pct,

    -- Net Dollar Retention - NDR / NRR (%)
    ROUND(
        CASE WHEN beginning_mrr_brl > 0
             THEN ((beginning_mrr_brl - churned_mrr_brl - contraction_mrr_brl + expansion_mrr_brl) / beginning_mrr_brl) * 100.0
             ELSE 100.0
        END, 2
    ) AS nrr_pct
FROM lagged_base
ORDER BY snapshot_month;


-- -----------------------------------------------------------------------------
-- 2. COHORT RETENTION ANALYSIS (mart_cohort_retention)
-- Acompanha cada safra (cohort_month) desde o Mês 0 (aquisição) até M11,
-- medindo tanto Retenção de Clientes (Logo Cohort Retention %) quanto
-- Retenção Líquida de Receita da Safra (Cohort Dollar Retention / NDR %).
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS mart_cohort_retention;

CREATE TABLE mart_cohort_retention AS
WITH cohort_activity AS (
    SELECT
        cohort_month,
        snapshot_month,
        months_since_signup,
        SUM(CASE WHEN active_flag = 1 THEN 1 ELSE 0 END) AS active_customers,
        SUM(CASE WHEN movement_type = 'CHURNED' THEN 1 ELSE 0 END) AS churned_in_period,
        ROUND(SUM(CASE WHEN active_flag = 1 THEN current_mrr_brl ELSE 0.0 END), 2) AS cohort_active_mrr_brl,
        ROUND(SUM(CASE WHEN active_flag = 1 THEN gross_profit_brl ELSE 0.0 END), 2) AS cohort_gross_profit_brl
    FROM raw_mrr_ledger
    GROUP BY cohort_month, snapshot_month, months_since_signup
),
cohort_With_base AS (
    SELECT
        ca.*,
        FIRST_VALUE(active_customers) OVER (
            PARTITION BY cohort_month
            ORDER BY months_since_signup ASC
        ) AS cohort_initial_customers,
        FIRST_VALUE(cohort_active_mrr_brl) OVER (
            PARTITION BY cohort_month
            ORDER BY months_since_signup ASC
        ) AS cohort_initial_mrr_brl,
        SUM(cohort_active_mrr_brl) OVER (
            PARTITION BY cohort_month
            ORDER BY months_since_signup ASC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_cohort_mrr_brl,
        SUM(cohort_gross_profit_brl) OVER (
            PARTITION BY cohort_month
            ORDER BY months_since_signup ASC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_cohort_gross_profit_brl
    FROM cohort_activity ca
)
SELECT
    cohort_month,
    snapshot_month,
    months_since_signup,
     'M' || PRINTF('%02d', months_since_signup) AS period_label,
    cohort_initial_customers,
    active_customers,
    churned_in_period,
    ROUND(
        (CAST(active_customers AS REAL) / cohort_initial_customers) * 100.0,
        2
    ) AS logo_retention_pct,
    ROUND(cohort_initial_mrr_brl, 2) AS cohort_initial_mrr_brl,
    ROUND(cohort_active_mrr_brl, 2) AS cohort_active_mrr_brl,
    ROUND(
        (cohort_active_mrr_brl / cohort_initial_mrr_brl) * 100.0,
        2
    ) AS dollar_retention_pct,
    ROUND(cumulative_cohort_mrr_brl, 2) AS cumulative_cohort_mrr_brl,
    ROUND(
        cumulative_cohort_mrr_brl / cohort_initial_customers,
        2
    ) AS realized_ltv_revenue_per_customer_brl,
    ROUND(
        cumulative_cohort_gross_profit_brl / cohort_initial_customers,
        2
    ) AS realized_ltv_gross_profit_per_customer_brl
FROM cohort_With_base
ORDER BY cohort_month, months_since_signup;


-- -----------------------------------------------------------------------------
-- 3. LIFETIME VALUE (LTV) & UNIT ECONOMICS BY SEGMENT / PLAN / CHANNEL
-- Calcula LTV Teórico Ajustado por Margem Bruta, LTV Observado, CAC,
-- Razão LTV:CAC e Payback Period em meses.
-- Fórmula Clássica SaaS:
--   LTV = (ARPA * Gross Margin %) / Monthly Logo Churn Rate
--   CAC Payback (Meses) = CAC / (ARPA * Gross Margin %)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS mart_ltv_unit_economics;

CREATE TABLE mart_ltv_unit_economics AS
WITH ledger_enriched AS (
    SELECT
        l.customer_id,
        c.segment,
        c.acquisition_channel,
        c.cac_brl,
        l.plan_id,
        p.plan_name,
        p.gross_margin_pct,
        l.snapshot_month,
        l.months_since_signup,
        l.active_flag,
        l.movement_type,
        l.current_mrr_brl,
        l.gross_profit_brl
    FROM raw_mrr_ledger l
    INNER JOIN raw_customers c ON l.customer_id = c.customer_id
    INNER JOIN raw_plans p ON l.plan_id = p.plan_id
),
segment_channel_stats AS (
    SELECT
        segment,
        acquisition_channel,
        COUNT(DISTINCT customer_id) AS total_customers_acquired,
        ROUND(AVG(cac_brl), 2) AS avg_cac_brl,
        -- ARPA médio dos meses ativos
        ROUND(
            SUM(CASE WHEN active_flag = 1 THEN current_mrr_brl ELSE 0.0 END) /
            NULLIF(SUM(CASE WHEN active_flag = 1 THEN 1 ELSE 0 END), 0),
            2
        ) AS arpa_brl,
        ROUND(AVG(gross_margin_pct), 4) AS avg_gross_margin_pct,
        -- Exposição ao risco (meses após M0) e eventos de churn
        SUM(CASE WHEN months_since_signup > 0 THEN 1 ELSE 0 END) AS customer_months_at_risk,
        SUM(CASE WHEN movement_type = 'CHURNED' THEN 1 ELSE 0 END) AS total_churn_events,
        ROUND(SUM(current_mrr_brl) / COUNT(DISTINCT customer_id), 2) AS observed_cumulative_rev_per_cust_brl,
        ROUND(SUM(gross_profit_brl) / COUNT(DISTINCT customer_id), 2) AS observed_cumulative_gp_per_cust_brl
    FROM ledger_enriched
    GROUP BY segment, acquisition_channel
),
ltv_calculated AS (
    SELECT
        segment,
        acquisition_channel,
        total_customers_acquired,
        avg_cac_brl,
        arpa_brl,
        ROUND(avg_gross_margin_pct * 100.0, 2) AS gross_margin_pct,
        ROUND(arpa_brl * avg_gross_margin_pct, 2) AS monthly_gross_profit_per_cust_brl,
        -- Taxa de Churn Mensal Empírica do Segmento/Canal (com piso de 0.8% para estabilidade assintótica)
        ROUND(
            MAX(
                0.008,
                CAST(total_churn_events AS REAL) / NULLIF(customer_months_at_risk, 0)
            ),
            4
        ) AS empirical_monthly_churn_rate
    FROM segment_channel_stats
)
SELECT
    l.segment,
    l.acquisition_channel,
    l.total_customers_acquired,
    l.arpa_brl,
    l.gross_margin_pct,
    l.monthly_gross_profit_per_cust_brl,
    ROUND(l.empirical_monthly_churn_rate * 100.0, 2) AS monthly_churn_rate_pct,
    ROUND(1.0 / l.empirical_monthly_churn_rate, 1) AS expected_lifetime_months,
    -- LTV Bruto (Receita Total Esperada no Ciclo de Vida)
    ROUND(l.arpa_brl / l.empirical_monthly_churn_rate, 2) AS theoretical_revenue_ltv_brl,
    -- LTV Líquido Ajustado por Margem Bruta (Padrão Venture Capital / SaaS)
    ROUND(
        l.monthly_gross_profit_per_cust_brl / l.empirical_monthly_churn_rate,
        2
    ) AS theoretical_gross_margin_ltv_brl,
    l.avg_cac_brl,
    -- Razão LTV:CAC (Benchmark saudável >= 3.0x)
    ROUND(
        (l.monthly_gross_profit_per_cust_brl / l.empirical_monthly_churn_rate) / NULLIF(l.avg_cac_brl, 0),
        2
    ) AS ltv_to_cac_ratio,
    -- CAC Payback Period em Meses (Tempo para recuperar o CAC via Lucro Bruto Mensal)
    ROUND(
        l.avg_cac_brl / NULLIF(l.monthly_gross_profit_per_cust_brl, 0),
        1
    ) AS cac_payback_months,
    CASE
        WHEN ((l.monthly_gross_profit_per_cust_brl / l.empirical_monthly_churn_rate) / NULLIF(l.avg_cac_brl, 0)) >= 5.0
            THEN 'Excelente (>= 5.0x - Escalar Investimento)'
        WHEN ((l.monthly_gross_profit_per_cust_brl / l.empirical_monthly_churn_rate) / NULLIF(l.avg_cac_brl, 0)) >= 3.0
            THEN 'Saudável (3.0x a 4.9x - Crescimento Sustentável)'
        ELSE 'Atenção (< 3.0x - Otimizar CAC ou Retenção)'
    END AS unit_economics_health
FROM ltv_calculated l
ORDER BY ltv_to_cac_ratio DESC;


-- -----------------------------------------------------------------------------
-- 4. CHURN REASONS & REVENUE LOST BREAKDOWN (mart_churn_reasons_breakdown)
-- Analisa o impacto financeiro (MRR e ARR perdidos) por motivo de cancelamento
-- e tipo de Churn (Voluntário vs Involuntário).
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS mart_churn_reasons_breakdown;

CREATE TABLE mart_churn_reasons_breakdown AS
SELECT
    s.churn_type,
    s.churn_reason,
    c.segment,
    COUNT(DISTINCT s.subscription_id) AS churned_subscriptions,
    ROUND(SUM(s.initial_mrr_brl), 2) AS lost_mrr_brl,
    ROUND(SUM(s.initial_mrr_brl) * 12.0, 2) AS lost_arr_brl,
    ROUND(AVG(s.tenure_months), 1) AS avg_tenure_before_churn_months,
    ROUND(
        (CAST(COUNT(DISTINCT s.subscription_id) AS REAL) /
         (SELECT COUNT(*) FROM raw_subscriptions WHERE status = 'CHURNED')) * 100.0,
        2
    ) AS share_of_total_churn_pct
FROM raw_subscriptions s
INNER JOIN raw_customers c ON s.customer_id = c.customer_id
WHERE s.status = 'CHURNED'
GROUP BY s.churn_type, s.churn_reason, c.segment
ORDER BY lost_mrr_brl DESC;
