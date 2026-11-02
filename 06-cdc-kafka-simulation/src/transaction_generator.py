"""
Componente 1: Gerador de Transações OLTP Simuladas (INSERT, UPDATE, DELETE).

Simula uma carga de trabalho transacional de e-commerce em um banco SQLite local.
Todas as mutações DML disparam automaticamente as triggers ACID no banco de origem,
gravando o estado anterior (BEFORE) e posterior (AFTER) no log interno `_cdc_wal_log`.
"""

from __future__ import annotations

import argparse
import random
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.config import PipelineConfig, setup_logger
from src.database import get_connection, init_oltp_database

logger = setup_logger("OLTP-Generator")


CATALOG_PRODUCTS: List[Tuple[str, str, float]] = [
    ("SKU-NB-PRO16", "Eletronicos", 7499.90),
    ("SKU-MON-4K27", "Perifericos", 2199.00),
    ("SKU-KB-MECH", "Perifericos", 649.50),
    ("SKU-NVME-2TB", "Hardware", 1120.00),
    ("SKU-GPU-RTX4070", "Hardware", 4299.00),
    ("SKU-CHAIR-ERGO", "Escritorio", 1890.00),
    ("SKU-HEADSET-ANC", "Audio", 980.00),
    ("SKU-DOCK-TB4", "Acessórios", 1350.00),
]

CUSTOMERS: List[Tuple[str, str, str]] = [
    ("CUST-1001", "Ana Beatriz Silva", "Sudeste"),
    ("CUST-1002", "Carlos Eduardo Mendes", "Sul"),
    ("CUST-1003", "Fernanda Costa Oliveira", "Nordeste"),
    ("CUST-1004", "Marcos Vinicius Rocha", "Centro-Oeste"),
    ("CUST-1005", "Juliana Almeida Santos", "Sudeste"),
    ("CUST-1006", "Rafael Pereira Lima", "Norte"),
    ("CUST-1007", "Beatriz Ribeiro Souza", "Sul"),
    ("CUST-1008", "Gabriel Martins Castro", "Sudeste"),
    ("CUST-1009", "Larissa Gomes Barbosa", "Nordeste"),
    ("CUST-1010", "Thiago Araujo Cardoso", "Centro-Oeste"),
]

PAYMENT_METHODS: List[str] = ["PIX", "CREDIT_CARD", "BOLETO", "DEBIT_CARD"]

STATUS_TRANSITIONS: Dict[str, List[str]] = {
    "CREATED": ["PAID", "CANCELLED"],
    "PAID": ["SHIPPED", "REFUNDED"],
    "SHIPPED": ["DELIVERED"],
    "DELIVERED": ["REFUNDED"],
    "CANCELLED": ["CREATED"],
    "REFUNDED": ["REFUNDED"],
}


@dataclass
class GenerationStats:
    """Estatísticas consolidadas de uma sessão de geração de transações."""

    inserts: int = 0
    updates: int = 0
    deletes: int = 0

    @property
    def total(self) -> int:
        return self.inserts + self.updates + self.deletes


class TransactionGenerator:
    """Motor de simulação de carga OLTP com suporte a INSERT, UPDATE e DELETE."""

    def __init__(self, config: Optional[PipelineConfig] = None, seed: Optional[int] = None) -> None:
        self.config = config or PipelineConfig()
        self.config.ensure_directories()
        init_oltp_database(self.config.oltp_db_path)
        self.rng = random.Random(seed)

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def _get_existing_order_ids(self) -> List[Dict[str, object]]:
        with get_connection(self.config.oltp_db_path) as conn:
            rows = conn.execute(
                "SELECT order_id, status, quantity, unit_price, total_amount FROM orders ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def execute_insert(self) -> Dict[str, object]:
        """Executa um INSERT de um novo pedido comercial no banco OLTP."""
        customer_id, customer_name, region = self.rng.choice(CUSTOMERS)
        product_sku, category, unit_price = self.rng.choice(CATALOG_PRODUCTS)
        quantity = self.rng.randint(1, 5)
        total_amount = round(quantity * unit_price, 2)
        payment_method = self.rng.choice(PAYMENT_METHODS)
        now_iso = self._utc_now_iso()
        order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"

        with get_connection(self.config.oltp_db_path) as conn:
            conn.execute(
                """
                INSERT INTO orders (
                    order_id, customer_id, customer_name, product_sku, category,
                    quantity, unit_price, total_amount, status, payment_method,
                    region, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    customer_id,
                    customer_name,
                    product_sku,
                    category,
                    quantity,
                    unit_price,
                    total_amount,
                    "CREATED",
                    payment_method,
                    region,
                    now_iso,
                    now_iso,
                ),
            )

        logger.info(
            "DML [INSERT] | order_id=%s | cliente=%s | sku=%s | qtd=%d | total=R$ %.2f",
            order_id,
            customer_id,
            product_sku,
            quantity,
            total_amount,
        )
        return {
            "op": "INSERT",
            "order_id": order_id,
            "total_amount": total_amount,
        }

    def execute_update(self, target_order: Dict[str, object]) -> Dict[str, object]:
        """Executa um UPDATE realista (evolução de status e/ou ajuste de quantidade)."""
        order_id = str(target_order["order_id"])
        old_status = str(target_order["status"])
        old_qty = int(target_order["quantity"])
        unit_price = float(target_order["unit_price"])
        old_total = float(target_order["total_amount"])

        # Decide se atualiza status, quantidade ou ambos
        possible_statuses = STATUS_TRANSITIONS.get(old_status, ["PAID"])
        new_status = self.rng.choice(possible_statuses)

        if old_status == "CREATED" and self.rng.random() < 0.45:
            # Pedido recém-criado pode ter quantidade alterada pelo cliente no carrinho/checkout
            delta_qty = self.rng.choice([-1, 1, 2])
            new_qty = max(1, old_qty + delta_qty)
        else:
            new_qty = old_qty

        new_total = round(new_qty * unit_price, 2)
        now_iso = self._utc_now_iso()

        with get_connection(self.config.oltp_db_path) as conn:
            conn.execute(
                """
                UPDATE orders
                   SET status = ?,
                       quantity = ?,
                       total_amount = ?,
                       updated_at = ?
                 WHERE order_id = ?
                """,
                (new_status, new_qty, new_total, now_iso, order_id),
            )

        logger.info(
            "DML [UPDATE] | order_id=%s | status: %s -> %s | qtd: %d -> %d | total: R$ %.2f -> R$ %.2f",
            order_id,
            old_status,
            new_status,
            old_qty,
            new_qty,
            old_total,
            new_total,
        )
        return {
            "op": "UPDATE",
            "order_id": order_id,
            "old_status": old_status,
            "new_status": new_status,
            "old_total": old_total,
            "new_total": new_total,
        }

    def execute_delete(self, target_order: Dict[str, object]) -> Dict[str, object]:
        """Executa um DELETE físico (expurgo/cancelamento hard-delete) no banco OLTP."""
        order_id = str(target_order["order_id"])
        old_status = str(target_order["status"])
        old_total = float(target_order["total_amount"])

        with get_connection(self.config.oltp_db_path) as conn:
            conn.execute("DELETE FROM orders WHERE order_id = ?", (order_id,))

        logger.info(
            "DML [DELETE] | order_id=%s | status_anterior=%s | valor_removido=R$ %.2f",
            order_id,
            old_status,
            old_total,
        )
        return {
            "op": "DELETE",
            "order_id": order_id,
            "old_status": old_status,
            "removed_amount": old_total,
        }

    def run_workload(
        self,
        num_events: int = 25,
        weights: Tuple[float, float, float] = (0.55, 0.30, 0.15),
        delay_seconds: float = 0.05,
        min_active_records: int = 5,
    ) -> GenerationStats:
        """
        Executa uma sequência de transações simuladas no banco OLTP.

        Args:
            num_events: Quantidade total de eventos DML a gerar.
            weights: Probabilidades relativas para (INSERT, UPDATE, DELETE).
            delay_seconds: Intervalo entre transações para simular tempo real.
            min_active_records: Mínimo de registros ativos antes de permitir DELETE.
        """
        stats = GenerationStats()
        logger.info(
            "Iniciando simulação de transações OLTP | eventos=%d | pesos(I/U/D)=%s | db=%s",
            num_events,
            weights,
            self.config.oltp_db_path,
        )

        for idx in range(1, num_events + 1):
            existing_orders = self._get_existing_order_ids()

            # Garante base mínima populada antes de aplicar UPDATE ou DELETE
            if len(existing_orders) < min_active_records:
                chosen_op = "INSERT"
            else:
                chosen_op = self.rng.choices(
                    population=["INSERT", "UPDATE", "DELETE"],
                    weights=list(weights),
                    k=1,
                )[0]

            if chosen_op == "INSERT":
                self.execute_insert()
                stats.inserts += 1
            elif chosen_op == "UPDATE":
                target = self.rng.choice(existing_orders)
                self.execute_update(target)
                stats.updates += 1
            else:
                # Prioriza deletar pedidos CANCELLED ou CREATED para realismo de negócio
                candidates = [
                    o for o in existing_orders if o["status"] in ("CANCELLED", "CREATED")
                ] or existing_orders
                target = self.rng.choice(candidates)
                self.execute_delete(target)
                stats.deletes += 1

            if delay_seconds > 0 and idx < num_events:
                time.sleep(delay_seconds)

        logger.info(
            "Workload OLTP finalizado | Total=%d (INSERT=%d, UPDATE=%d, DELETE=%d)",
            stats.total,
            stats.inserts,
            stats.updates,
            stats.deletes,
        )
        return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gerador de transações OLTP simuladas (INSERT, UPDATE, DELETE) em SQLite."
    )
    parser.add_argument(
        "--events",
        type=int,
        default=25,
        help="Número de transações a serem geradas por lote (padrão: 25).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.05,
        help="Intervalo em segundos entre transações (padrão: 0.05s).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed opcional para reprodutibilidade determinística.",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Executa continuamente gerando transações até interrupção (Ctrl+C).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generator = TransactionGenerator(seed=args.seed)

    if args.continuous:
        logger.info("Modo contínuo ativado. Pressione Ctrl+C para encerrar.")
        try:
            while True:
                generator.run_workload(num_events=args.events, delay_seconds=args.delay)
                time.sleep(1.0)
        except KeyboardInterrupt:
            logger.info("Gerador OLTP encerrado pelo usuário.")
    else:
        generator.run_workload(num_events=args.events, delay_seconds=args.delay)


if __name__ == "__main__":
    main()
