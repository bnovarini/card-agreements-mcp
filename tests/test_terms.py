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


def test_intro_phrasing_and_boilerplate():
    t = "Annual Percentage Rate (APR) for Purchases 0.00% Introductory APR for a period of twelve (12) billing cycles. After that, your APR will be 11.24% to 22.24%. This APR will vary with the market based on the Prime Rate.\n"
    r = [x for x in T.extract(t) if x[0] == "purchase_apr"][0]
    assert r[8] == 1 and r[9] == 0.0 and r[10] == "12 billing cycles"
    t2 = "Annual Percentage Rate (APR) for Purchases 14.99%. The minimum payment includes promotional Credit Plan purchases.\n"
    r2 = [x for x in T.extract(t2) if x[0] == "purchase_apr"][0]
    assert r2[8] == 0


def test_card_name_inside_label():
    t = "Interest Rates and Interest Charges\nAnnual Percentage Rate (APR) for Visa Platinum Purchases 8.49% to 23.74% , when you open your Account, based on your creditworthiness. This APR will vary with the market based on the Prime Rate.\n"
    rows = [x for x in T.extract(t) if x[0] == "purchase_apr"]
    assert rows and "8.49%" in rows[0][4]


def test_label_then_card_name_then_purchases_on_next_line():
    t = ("Interest Rates and Interest Charges\n"
         "Annual Percentage Rate (APR) for                           Visa Platinum\n"
         "Purchases                                                  10.90% to 20.90%, based on your creditworthiness.\n"
         "                                                           Visa Signature\n"
         "                                                           14.25% to 21.25%\n")
    rows = [x for x in T.extract(t) if x[0] == "purchase_apr"]
    assert rows and "10.90%" in rows[0][4]


def test_plural_rates_and_truncated_purchases_label():
    t1 = "PRICING INFORMATION\nAnnual Percentage Rates for Purchases This APR will vary with the Market based on the Prime +9.74 to 19.74% Prime Rate. (APR) 16.49 to 26.49%\n"
    t2 = "Interest Rates and Interest Charges Annual Percentage Rate (APR) Pu 17.49% to 34.99% APR. This APR will vary with the market based on the Prime Rate.\n"
    for t in (t1, t2):
        assert [x for x in T.extract(t) if x[0] == "purchase_apr"]


def test_daily_periodic_rates_are_not_aprs():
    t = "Interest Rates\nBalance Transfer APR is 0.04792% to 0.07805% as a daily rate.\nAPR for Balance Transfers 21.99% (DPR) 0.060247%\n"
    rows = [x for x in T.extract(t) if x[0] == "balance_transfer_apr"]
    assert all("0.0" not in x[4] or "21.99%" in x[4] for x in rows)
    assert not any('0.04792%' in x[4] for x in rows)
    assert rows and '"0.060247%"' not in rows[0][4]


def test_bank_of_america_cash_advance_labels():
    t = ("APR for Direct Deposit and Check Cash\nAdvances\n\n       These APRs will vary with the        Prime + 21.74%\n"
         "       market based on the Prime Rate (as   (APR) 28.49%\n       of 06/30/2026)                       (DPR) 0.078054%\n\n"
         "APR for Bank Cash Advances\n\n       These APRs will vary with the        Prime + 21.74%\n       market (APR) 28.49%\n")
    rows = [x for x in T.extract(t) if x[0] == "cash_advance_apr"]
    assert rows and "28.49%" in rows[0][4] and "0.078054%" not in rows[0][4]


def test_label_alone_on_its_line():
    t1 = "(DPR = Daily Periodic Rate)\nAnnual Percentage Rates for Purchases\n\nThis APR will vary with the Market based on the\n      Prime +9.74 to 19.74%\nPrime Rate.      (APR) 16.49 to 26.49%\n"
    t2 = "Interest Rates and Interest Charges\n\n     Annual Percentage Rate (APR) Pu\n         17.49% to 34.99% APR. This APR will vary with the market based on the Prime Rate.\n"
    for t in (t1, t2):
        assert [x for x in T.extract(t) if x[0] == "purchase_apr"]


def test_vertical_label_table_shared_value_cell():
    t = ("Interest Rates and Interest Charges\n"
         "                         Regular APR ranges from 10.40% to 27.40% (0.867 to 2.283 monthly\n"
         "Regular Annual           periodic rate) based on creditworthiness. The APRs vary with\n"
         "Percentage Rate          the market based on the Prime Rate plus a margin ranging from 3.65% to\n"
         "(APR) for:               20.65%.\n\n"
         "       Purchases         Secured credit cards, Regular APR is 26.40% (2.200 monthly periodic rate).\n"
         "       Balance           This APR will vary with the market based on the Prime Rate plus a margin of\n"
         "       Transfers         19.65%.\n       Cash\n       Advances\n")
    ks = {x[0] for x in T.extract(t)}
    assert {"purchase_apr", "balance_transfer_apr", "cash_advance_apr"} <= ks
