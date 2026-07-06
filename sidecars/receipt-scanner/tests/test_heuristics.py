"""Unit tests for the generic field-extraction heuristics."""

from receipt_scanner import heuristics


class TestFindAmounts:
    def test_dollar_sign_and_iso(self):
        amounts = heuristics.find_amounts("Total: $17.20 USD")
        values = [a[1] for a in amounts]
        assert 17.20 in values

    def test_comma_thousands(self):
        amounts = heuristics.find_amounts("Grand total $1,234.56")
        assert any(abs(a[1] - 1234.56) < 0.001 for a in amounts)

    def test_negative_discount(self):
        amounts = heuristics.find_amounts("Discount $-25.80")
        assert any(abs(a[1] + 25.80) < 0.001 for a in amounts)

    def test_currency_from_symbol(self):
        amounts = heuristics.find_amounts("Total €42.00")
        eur = [a for a in amounts if a[2] == "EUR"]
        assert eur and abs(eur[0][1] - 42.00) < 0.001

    def test_currency_from_iso_suffix(self):
        amounts = heuristics.find_amounts("904.54 USD")
        assert amounts and amounts[0][2] == "USD"


class TestFindTotal:
    def test_total_beats_zero_amount_due(self):
        # "Amount Due: $0.00" (paid) should NOT win over "Total: $17.20".
        text = "Amount Due:\n$0.00 USD\nSubtotal:\n$17.20\nTotal:\n$17.20 USD"
        amounts = heuristics.find_amounts(text)
        result = heuristics.find_total(text, amounts)
        assert result is not None
        assert abs(result[0] - 17.20) < 0.001

    def test_total_per_passenger(self):
        text = "Total Per Passenger:\n904.54 USD\nTotal:\n904.54 USD"
        amounts = heuristics.find_amounts(text)
        result = heuristics.find_total(text, amounts)
        assert abs(result[0] - 904.54) < 0.001

    def test_fallback_to_largest_when_no_keyword(self):
        # Lyft-style: amounts with no "Total" keyword.
        text = "Apple Pay (Visa)\n$88.73\nStandard fare\n$73.94\nTip\n$14.79"
        amounts = heuristics.find_amounts(text)
        result = heuristics.find_total(text, amounts)
        assert abs(result[0] - 88.73) < 0.001

    def test_none_when_no_amounts(self):
        assert heuristics.find_total("no money here", []) is None


class TestFindDate:
    def test_keyword_date(self):
        assert heuristics.find_date("Receipt Date:\n2026-02-27") == "2026-02-27"

    def test_date_of_issue(self):
        assert heuristics.find_date("Date of issue\nJanuary 4, 2026") == "2026-01-04"

    def test_prefers_verbose_over_print_header(self):
        # Gmail print header "1/28/26, 10:47 PM" must not beat the
        # verbose order date "Wed, Jan 21, 2026".
        text = "1/28/26, 10:47 PM\nGmail - Your order\nWed, Jan 21, 2026 at 9:03 PM"
        assert heuristics.find_date(text) == "2026-01-21"

    def test_slash_date_is_month_first(self):
        # Ambiguous slash dates are pinned to US month/day order, not
        # dateparser's locale autodetection.
        assert heuristics.find_date("Receipt Date: 01/02/2026") == "2026-01-02"

    def test_none_when_no_date(self):
        assert heuristics.find_date("no date here, just words") is None


class TestFindVendor:
    def test_receipt_from(self):
        text = "Your receipt\nReceipt from Acme Hosting LLC\nReceipt #123"
        assert heuristics.find_vendor(text) == "Acme Hosting LLC"

    def test_email_domain(self):
        text = "Acme Airlines\nReceipts@acme-airlines.example.com\nthanks"
        # "Receipt from" absent → falls to sender/domain or first line.
        vendor = heuristics.find_vendor(text)
        assert vendor and "Acme" in vendor

    def test_skips_customer_placeholder_email(self):
        text = "1 message\ncustomer@example.com\nAcme Bookkeeping\nInvoice"
        vendor = heuristics.find_vendor(text)
        assert vendor != "Example"

    def test_skips_noise_first_lines(self):
        text = "PAID\nAcme Hosting\nInvoice #8800"
        assert heuristics.find_vendor(text) == "Acme Hosting"


class TestTaxExtraction:
    def test_anthropic_column_header_does_not_capture_line_item(self):
        # Real Anthropic-invoice shape: "Tax" appears in a `Description Tax
        # Amount` row, and the actual tax is on a later `Tax - <state>
        # (6% on $X) | $0.30` line. Heuristic must pick 0.30, not 5.00.
        text = (
            "Description Qty Unit price Tax Amount\n"
            "One-time credit purchase\n1\n$5.00\n6%\n$5.00\n"
            "Subtotal\n$5.00\n"
            "Total excluding tax\n$5.00\n"
            "Tax - Maryland (6% on $5.00)\n$0.30\n"
            "Total\n$5.30\n"
        )
        fields = heuristics.extract_fields(text)
        assert fields["tax"]["value"] == "0.30"

    def test_freshbooks_tax_colon_zero(self):
        # FreshBooks-style "Tax:\n$0.00 USD" — bare "Tax:" pattern should
        # still match (and return 0.00, not the total below it).
        text = "Subtotal:\n$17.20 USD\nTax:\n$0.00 USD\nTotal:\n$17.20 USD"
        fields = heuristics.extract_fields(text)
        assert fields["tax"]["value"] == "0.00"


class TestFeesExtraction:
    def test_service_fee(self):
        text = "Subtotal: $20.00\nService fee: $1.50\nTotal: $21.50"
        out = heuristics.extract_fields(text)
        assert out["fees"]["value"] == "1.50"

    def test_processing_fee(self):
        text = "Amount: $100.00\nProcessing fee $2.50\nTotal $102.50"
        out = heuristics.extract_fields(text)
        assert out["fees"]["value"] == "2.50"

    def test_gratuity_picked_up(self):
        text = "Subtotal $40.00\nTax $3.20\nGratuity $8.00\nTotal $51.20"
        out = heuristics.extract_fields(text)
        assert out["fees"]["value"] == "8.00"

    def test_tip_colon(self):
        text = "Subtotal $30.00\nTip: $5.00\nTotal $35.00"
        out = heuristics.extract_fields(text)
        assert out["fees"]["value"] == "5.00"

    def test_no_fees_when_only_tax(self):
        # The plain "Tax:" pattern must not be misread as a fee.
        text = "Subtotal: $20.00\nTax: $1.60\nTotal: $21.60"
        out = heuristics.extract_fields(text)
        assert "fees" not in out

    def test_bare_fee_word_not_captured_without_colon(self):
        # "Fee schedule:" in prose shouldn't trigger.
        text = "See the fee schedule\nTotal: $20.00"
        out = heuristics.extract_fields(text)
        assert "fees" not in out


class TestDetectCurrency:
    def test_mode_wins(self):
        assert heuristics.detect_currency("USD USD EUR") == "USD"

    def test_symbol_fallback(self):
        assert heuristics.detect_currency("only £ here") == "GBP"

    def test_default_usd(self):
        assert heuristics.detect_currency("no currency token") == "USD"


class TestNoiseLines:
    def test_paid_is_noise(self):
        assert heuristics.is_noise_line("PAID")

    def test_invoice_number_label_is_noise(self):
        assert heuristics.is_noise_line("Invoice number")

    def test_bare_date_is_noise(self):
        assert heuristics.is_noise_line("February 15, 2026")

    def test_real_vendor_is_not_noise(self):
        assert not heuristics.is_noise_line("Acme Hosting LLC")


class TestFindPayer:
    def test_bill_to_inline(self):
        text = "Invoice #42\nBill to: Acme Corp\nDue: $100.00"
        assert heuristics.find_payer(text) == "Acme Corp"

    def test_sold_to_block(self):
        text = "Invoice\nSold to:\nAcme Corp\n123 Main St"
        assert heuristics.find_payer(text) == "Acme Corp"

    def test_customer_label(self):
        text = "Receipt\nCustomer: Globex LLC\nAmount paid: $200.00"
        assert heuristics.find_payer(text) == "Globex LLC"

    def test_invoiced_to_block(self):
        text = "Invoice 9804\nInvoiced To\nCynthia Cicalese\n123 Main St"
        assert heuristics.find_payer(text) == "Cynthia Cicalese"

    def test_billed_to_variant(self):
        text = "Invoice\nBilled to: Globex LLC\nAmount: $200"
        assert heuristics.find_payer(text) == "Globex LLC"

    def test_received_from(self):
        text = "Payment confirmation\nReceived from Initech Industries\nThanks"
        assert heuristics.find_payer(text) == "Initech Industries"

    def test_skips_when_no_marker(self):
        # An expense-shaped receipt has no Bill-to / Sold-to.
        text = "Acme Hosting\nDate: 2026-01-01\nTotal: $9.99"
        assert heuristics.find_payer(text) is None


class TestExtractFieldsByKind:
    def test_expense_emits_payee(self):
        text = "Acme Hosting LLC\nTotal: $9.99\nDate: 2026-01-01"
        out = heuristics.extract_fields(text, kind="expense")
        assert "payee" in out
        assert "payer" not in out

    def test_income_emits_payer(self):
        text = "Invoice 7\nBill to: Globex LLC\nTotal: $250.00\nDate: 2026-02-15"
        out = heuristics.extract_fields(text, kind="income")
        assert out.get("payer", {}).get("value") == "Globex LLC"
        assert "payee" not in out

    def test_income_keeps_total_and_date(self):
        text = "Invoice 7\nBill to: Globex LLC\nTotal: $250.00\nDate: 2026-02-15"
        out = heuristics.extract_fields(text, kind="income")
        assert out["total"]["value"] == "250.00"
        assert out["date"]["value"] == "2026-02-15"
