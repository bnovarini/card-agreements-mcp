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


def test_purchase_apr_split_label_chase():
    t = "Purchase Annual\nPercentage Rate (APR)\n                17.49% to 26.49%. This APR will vary with the market based on the Prime Rate.\n"
    assert [r for r in T.extract(t) if r[0] == "purchase_apr"]


def test_purchase_apr_split_label_alliant():
    t = "  Annual Percentage Rate (APR)         15.74% to 25.74% based on your creditworthiness.\n  for Purchases                        the market based on the Prime Rate.\n"
    assert [r for r in T.extract(t) if r[0] == "purchase_apr"]


def test_purchase_apr_sentence_form():
    t = "The Purchase APR is 15.90% which is a monthly periodic rate of 1.3250%.\n"
    assert [r for r in T.extract(t) if r[0] == "purchase_apr"]
