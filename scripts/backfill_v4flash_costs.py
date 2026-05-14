"""Backfill cost data for DeepSeek-V4-Flash calls where cost=0 due to routing_slug being NULL.

Affected period: 2026-05-09 ~ 2026-05-13, user_id=2 (test_user_001)
Pricing: input=1,000,000, output=2,000,000, cached_input=500,000 (micro-yuan per million tokens)

This script:
1. Updates each api_call_log row: recalculates cost, provider_cost, cost_detail
2. Updates usage_stats pre-aggregated buckets: adds the missing total_cost
3. Deducts the total backfilled cost from the user's balance

Run: python scripts/backfill_v4flash_costs.py
"""

import json
import math
import sys

import pymysql

DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "abc123",
    "charset": "utf8mb4",
}

USER_ID = 2
MODEL = "DeepSeek-V4-Flash"
START = "2026-05-09 00:00:00"
END = "2026-05-14 00:00:00"

USER_INPUT_PRICE = 1_000_000
USER_OUTPUT_PRICE = 2_000_000
USER_CACHED_PRICE = 500_000
PROVIDER_INPUT_PRICE = 1_000_000
PROVIDER_OUTPUT_PRICE = 2_000_000
PROVIDER_CACHED_PRICE = 500_000


def calc_cost(prompt_tokens, completion_tokens, cached_tokens, input_price, output_price, cached_price):
    non_cached = max(prompt_tokens - cached_tokens, 0)
    total = non_cached * input_price / 1_000_000 + completion_tokens * output_price / 1_000_000 + cached_tokens * cached_price / 1_000_000
    return math.ceil(total) if total > 0 else 0, non_cached


def main():
    conn_user = pymysql.connect(**DB_CONFIG, database="eucal_ai_user", autocommit=False)
    cur = conn_user.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT id, prompt_tokens, completion_tokens, cached_tokens, cost,
               DATE_FORMAT(created_at, '%%Y-%%m-%%d %%H:00:00') AS stat_hour
        FROM api_call_logs
        WHERE user_id = %s
          AND COALESCE(selected_model, model_name) = %s
          AND status = 1
          AND cost = 0
          AND created_at >= %s AND created_at < %s
        ORDER BY created_at
    """, (USER_ID, MODEL, START, END))
    rows = cur.fetchall()

    if not rows:
        print("No rows to backfill.")
        return

    print(f"Found {len(rows)} rows to backfill.")

    total_user_cost = 0
    total_provider_cost = 0
    hourly_cost_delta: dict[str, int] = {}

    for row in rows:
        pt, ct, ckt = row["prompt_tokens"], row["completion_tokens"], row["cached_tokens"]

        user_cost, non_cached = calc_cost(pt, ct, ckt, USER_INPUT_PRICE, USER_OUTPUT_PRICE, USER_CACHED_PRICE)
        provider_cost, _ = calc_cost(pt, ct, ckt, PROVIDER_INPUT_PRICE, PROVIDER_OUTPUT_PRICE, PROVIDER_CACHED_PRICE)

        cost_detail = {
            "non_cached_input_tokens": non_cached,
            "completion_tokens": ct,
            "cached_tokens": ckt,
            "user_prices": {"input": USER_INPUT_PRICE, "output": USER_OUTPUT_PRICE, "cached_input": USER_CACHED_PRICE},
            "provider_prices": {"input": PROVIDER_INPUT_PRICE, "output": PROVIDER_OUTPUT_PRICE, "cached_input": PROVIDER_CACHED_PRICE},
            "user_cost": user_cost,
            "provider_cost": provider_cost,
        }

        cur.execute("""
            UPDATE api_call_logs
            SET cost = %s, provider_cost = %s, cost_detail = %s
            WHERE id = %s AND cost = 0
        """, (user_cost, provider_cost, json.dumps(cost_detail), row["id"]))

        total_user_cost += user_cost
        total_provider_cost += provider_cost

        stat_hour = row["stat_hour"]
        hourly_cost_delta[stat_hour] = hourly_cost_delta.get(stat_hour, 0) + user_cost

    print(f"Updated {len(rows)} api_call_logs rows.")
    print(f"Total user cost:     {total_user_cost:,} micro-yuan (¥{total_user_cost / 1_000_000:.2f})")
    print(f"Total provider cost: {total_provider_cost:,} micro-yuan (¥{total_provider_cost / 1_000_000:.2f})")

    # Step 2: Update usage_stats pre-aggregated buckets
    updated_stats = 0
    for stat_hour, cost_delta in hourly_cost_delta.items():
        cur.execute("""
            UPDATE usage_stats
            SET total_cost = total_cost + %s
            WHERE user_id = %s AND model_name = %s AND stat_hour = %s
        """, (cost_delta, USER_ID, MODEL, stat_hour))
        updated_stats += cur.rowcount

    print(f"Updated {updated_stats} usage_stats rows across {len(hourly_cost_delta)} hourly buckets.")

    # Step 3: Deduct from user balance
    cur.execute("""
        UPDATE users
        SET balance = balance - %s, used_amount = used_amount + %s
        WHERE id = %s AND balance >= %s
    """, (total_user_cost, total_user_cost, USER_ID, total_user_cost))

    if cur.rowcount == 1:
        print(f"Deducted ¥{total_user_cost / 1_000_000:.2f} from user balance.")
    else:
        print("WARNING: Failed to deduct balance (insufficient funds or user not found). Rolling back.")
        conn_user.rollback()
        conn_user.close()
        sys.exit(1)

    conn_user.commit()
    print("All changes committed successfully.")

    cur.execute("SELECT balance, used_amount FROM users WHERE id = %s", (USER_ID,))
    user = cur.fetchone()
    print(f"New balance: ¥{user['balance'] / 1_000_000:.2f}, used: ¥{user['used_amount'] / 1_000_000:.2f}")

    conn_user.close()


if __name__ == "__main__":
    main()
