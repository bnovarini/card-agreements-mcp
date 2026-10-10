from card_agreements_mcp import terms as T

TABLE = """ Interest Rates and Interest Charges

 Annual Percentage Rate           Platinum
 (APR) for Purchases              1.99% intro rate for the first 12 billing cycles, then
                                  10.24% to 18.00% based on your creditworthi-
                                  ness. After that, your rate will vary with the market based on
                                  Prime Rate plus a margin.

                                  Platinum Rewards
                                  1.99% intro rate for the first 12 billing cycles, then
                                  12.24% to 18.00% based on your creditworthiness.
"""


def test_purchase_apr_table_layout():
    rows = [r for r in T.extract(TABLE) if r[0] == "purchase_apr"]
    assert rows
    assert "10.24%" in rows[0][2] and "12.24%" in rows[0][2]
