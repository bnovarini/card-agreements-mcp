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
    assert "10.24%" in rows[0][2] and "12.24%" in " ".join(r[2] for r in rows)


def test_purchase_apr_split_label_chase():
    t = "Purchase Annual\nPercentage Rate (APR)\n                17.49% to 26.49%. This APR will vary with the market based on the Prime Rate.\n"
    assert [r for r in T.extract(t) if r[0] == "purchase_apr"]


def test_purchase_apr_split_label_alliant():
    t = "  Annual Percentage Rate (APR)         15.74% to 25.74% based on your creditworthiness.\n  for Purchases                        the market based on the Prime Rate.\n"
    assert [r for r in T.extract(t) if r[0] == "purchase_apr"]


def test_purchase_apr_sentence_form():
    t = "The Purchase APR is 15.90% which is a monthly periodic rate of 1.3250%.\n"
    assert [r for r in T.extract(t) if r[0] == "purchase_apr"]


HFCU = """ Interest Rates and Interest Charges

 Annual Percentage Rate           Platinum
 (APR) for Purchases              1.99% intro rate for the first 12 billing cycles, then
                                  10.24% to 18.00% based on your creditworthi-
                                  ness. After that, your rate will vary with the market based on
                                  Prime Rate plus a margin.

                                  Platinum Rewards
                                  1.99% intro rate for the first 12 billing cycles, then
                                  12.24% to 18.00% based on your creditworthiness.
                                  After that, your rate will vary with the market based on Prime
                                  Rate plus a margin.
"""


def test_per_card_rows_with_intro_and_index():
    rows = [r for r in T.extract(HFCU) if r[0] == "purchase_apr"]
    assert [r[6] for r in rows] == ["Platinum", "Platinum Rewards"]
    for r in rows:
        assert r[7] == "card" and r[8] == 1 and r[9] == 1.99 and r[10] == "12 billing cycles"
        assert r[11] == 1 and r[12] == "Prime Rate"
    assert "10.24%" in rows[0][2] and "12.24%" in rows[1][2]


def test_margin_only_rate_keeps_margin_and_basis():
    t = "Purchase APR: Prime Rate plus a margin of 12.74% - 19.74%\n"
    r = [x for x in T.extract(t) if x[0] == "purchase_apr"][0]
    assert (r[13], r[14], r[15]) == (12.74, 19.74, "margin")


def test_current_prime_value_is_not_a_stated_apr():
    t = "Purchase and Balance Transfer APR: We add a Margin of 8.74%, 10.74% or 12.74% to the Prime Rate of 6.75%.\n"
    rows = [x for x in T.extract(t) if x[0] in ("purchase_apr", "balance_transfer_apr")]
    assert rows and all(x[15] == "margin" and x[13] == 8.74 and x[14] == 12.74 for x in rows)


def test_balance_transfer_and_cash_advance_labels():
    t = " (APR) Cash Advances              Prime Rate plus 21.99%. This APR will vary with the market.\n (APR) Balance Transfers       Prime Rate plus 9.99%.\n"
    ks = {r[0] for r in T.extract(t)}
    assert {"cash_advance_apr", "balance_transfer_apr"} <= ks


def test_purchase_label_split_across_lines():
    t = ("PRICING INFORMATION\nAnnual Percentage Rate (APR) for\nPurchases\n\n"
         "       These APRs will vary with the        Prime + 7.24% to Prime + 20.24%\n"
         "                                            (APR) 13.99% to 26.99%\n")
    rows = [x for x in T.extract(t) if x[0] == "purchase_apr"]
    assert rows and rows[0][13] == 7.24 and rows[0][14] == 20.24
