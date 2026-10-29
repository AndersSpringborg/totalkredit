import unittest

from src import scraper


class ParseTotalkreditTablesTest(unittest.TestCase):
    def test_parse_fixed_rate_payout_rows(self):
        payload = {
            "title": "Kurser ved udbetaling af Totalkredit-lån med fast rente",
            "lastUpdatedTimestamp": "2026-07-01T12:46:26.667",
            "nextUpdateTimestamp": "2026-07-01T11:00:00+00:00",
            "groups": [
                {
                    "name": "Fast rente",
                    "entries": [
                        {
                            "name": "4% 2056 med afdrag",
                            "lifetime": "30 år",
                            "fondCode": "954187",
                            "openForOffer": "Åben",
                            "isOpenForOffer": True,
                            "priceRate": "99,57",
                            "spotPriceRatePayment": "99,30",
                            "effectiveRate": "4,10 %",
                            "nasdaqUrl": "https://example.test/954187",
                        }
                    ],
                }
            ],
        }

        rows = scraper.parse_table(payload, scraper.TABLES["fixed_rate_payout"])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["section_key"], "fixed_rate_payout")
        self.assertEqual(rows[0]["group"], "Fast rente")
        self.assertEqual(rows[0]["fond_code"], "954187")
        self.assertEqual(rows[0]["status"], "Åben")
        self.assertEqual(rows[0]["offer_price"], 99.57)
        self.assertEqual(rows[0]["current_price"], 99.30)
        self.assertEqual(rows[0]["effective_rate_percent"], 4.10)

    def test_parse_variable_rate_payout_rows(self):
        payload = {
            "title": "Kurser ved udbetaling af Totalkredit-lån med variabel rente",
            "lastUpdatedTimestamp": "2026-07-01T12:46:24.953",
            "nextUpdateTimestamp": "2026-07-01T11:00:00+00:00",
            "groups": [
                {
                    "name": "F-kort",
                    "entries": [
                        {
                            "name": "Aktuel rente 2,3892%, refinansiering 01-07-2029",
                            "lifetime": "30 år",
                            "fondCode": "955469",
                            "priceRate": "100,28",
                            "spotPriceRatePayment": "100,25",
                            "interestMarginRate": "0,55 %",
                            "expectedRate": "2,5611 %",
                        }
                    ],
                }
            ],
        }

        rows = scraper.parse_table(payload, scraper.TABLES["variable_rate_payout"])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["section_key"], "variable_rate_payout")
        self.assertEqual(rows[0]["group"], "F-kort")
        self.assertEqual(rows[0]["offer_price"], 100.28)
        self.assertEqual(rows[0]["current_price"], 100.25)
        self.assertEqual(rows[0]["interest_margin_percent"], 0.55)
        self.assertEqual(rows[0]["calculation_rate_percent"], 2.5611)

    def test_parse_cash_interest_rows(self):
        payload = {
            "title": "Kontantrenter ved udbetaling af Tilpasningslån i Totalkredit",
            "lastUpdatedTimestamp": "2026-07-01T07:50:17.483",
            "nextUpdateTimestamp": "2026-07-02T05:50:00+00:00",
            "groups": [
                {
                    "name": "Tilpasningslån",
                    "entries": [
                        {
                            "name": "F3 med afdrag",
                            "lifetime": "30 år",
                            "innerInterestGrossValue": "2,63%",
                            "isOpenForOffer": True,
                        }
                    ],
                }
            ],
        }

        rows = scraper.parse_table(payload, scraper.TABLES["cash_interest_payout"])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["section_key"], "cash_interest_payout")
        self.assertEqual(rows[0]["cash_interest_percent"], 2.63)
        self.assertNotIn("fond_code", rows[0])

    def test_parse_redemption_rows_includes_all_subgroups(self):
        payload = {
            "title": "Kurser ved indfrielse af lån i Totalkredit",
            "lastUpdatedTimestamp": "2026-07-01T12:46:26.667",
            "nextUpdateTimestamp": "2026-07-01T11:00:00+00:00",
            "groups": [
                {
                    "name": "Fast rente",
                    "entries": [
                        {
                            "name": "4% 2056 med afdrag",
                            "fondCode": "954187",
                            "green": "Nej",
                            "isGreen": False,
                            "redemptionRate": "100",
                            "interestMarginRate": "-",
                            "expectedRate": "-",
                            "spotPriceRateRedemption": "100,04",
                        }
                    ],
                },
                {
                    "name": "RenteMax",
                    "entries": [
                        {
                            "name": "Aktuel rente 2,8153%, loft 6%, udløb 01-10-2041",
                            "fondCode": "977152",
                            "green": "Nej",
                            "isGreen": False,
                            "redemptionRate": "105",
                            "interestMarginRate": "0,55 %",
                            "expectedRate": "3,1803 %",
                            "spotPriceRateRedemption": "105,55",
                        }
                    ],
                },
            ],
        }

        rows = scraper.parse_table(payload, scraper.TABLES["redemption"])

        self.assertEqual(len(rows), 2)
        self.assertEqual({row["group"] for row in rows}, {"Fast rente", "RenteMax"})
        rentemax = rows[1]
        self.assertEqual(rentemax["section_key"], "redemption")
        self.assertEqual(rentemax["redemption_rate"], 105.0)
        self.assertEqual(rentemax["interest_margin_percent"], 0.55)
        self.assertEqual(rentemax["calculation_rate_percent"], 3.1803)
        self.assertEqual(rentemax["current_price"], 105.55)
        self.assertEqual(rentemax["green"], "Nej")


if __name__ == "__main__":
    unittest.main()
