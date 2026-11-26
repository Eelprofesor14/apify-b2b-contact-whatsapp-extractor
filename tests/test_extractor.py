import unittest
from src.extractor import decode_cfemail, extract_signals, is_valid_business_email


class TestB2BExtractor(unittest.TestCase):
    def test_cloudflare_cfemail_decoding(self) -> None:
        # Encode "ventas@pampasteel.com.ar" with XOR key 0x2a
        target = "ventas@pampasteel.com.ar"
        key = 0x2A
        encoded = f"{key:02x}" + "".join(f"{ord(c) ^ key:02x}" for c in target)
        self.assertEqual(decode_cfemail(encoded), target)

    def test_full_b2b_latam_spain_us_signals(self) -> None:
        target = "hola@industrialmetal.es"
        key = 0x15
        cf_hex = f"{key:02x}" + "".join(f"{ord(c) ^ key:02x}" for c in target)

        sample_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <title>Industrial Metal S.L. | Fabricación B2B</title>
          <meta name="description" content="Proveedor mayorista industrial en España y Argentina.">
          <script type="application/ld+json">
          {{
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": "Industrial Metal S.L.",
            "email": "directorio@industrialmetal.es",
            "telephone": "+34 910 123 456",
            "sameAs": [
              "https://www.linkedin.com/company/industrial-metal-sl",
              "https://x.com/industrialmetal"
            ]
          }}
          </script>
        </head>
        <body>
          <a class="__cf_email__" data-cfemail="{cf_hex}">[email protected]</a>
          <p>Escribinos a soporte [arroba] industrialmetal [punto] es o ventas [at] industrialmetal.es</p>
          <p>Ignorar basura: noreply@industrialmetal.es y logo@2x.png y user@sentry.io</p>
          <a href="https://wa.me/5491145678901?text=Hola">WhatsApp Ventas AR</a>
          <a href="https://api.whatsapp.com/send?phone=34600112233">WhatsApp ES</a>
          <a href="/contacto">Contacto</a>
          <a href="/aviso-legal">Aviso Legal</a>
          <footer>CUIT: 30-71234567-9 | CIF: B12345678 | RFC: ABC210101XYZ</footer>
        </body>
        </html>
        """
        res = extract_signals(sample_html, "https://www.industrialmetal.es/")
        self.assertEqual(res["company_name"], "Industrial Metal S.L.")
        self.assertEqual(
            res["emails"],
            [
                "directorio@industrialmetal.es",
                "hola@industrialmetal.es",
                "soporte@industrialmetal.es",
                "ventas@industrialmetal.es",
            ],
        )
        self.assertEqual(res["whatsapp"], ["+34600112233", "+5491145678901"])
        self.assertIn("+34 910 123 456", res["phones"])
        self.assertIn("AR-CUIT: 30-71234567-9", res["tax_ids"])
        self.assertIn("ES-NIF/CIF: B12345678", res["tax_ids"])
        self.assertIn("MX-RFC: ABC210101XYZ", res["tax_ids"])
        self.assertEqual(res["linkedin"], ["https://www.linkedin.com/company/industrial-metal-sl"])
        self.assertEqual(res["twitter_x"], ["https://x.com/industrialmetal"])
        self.assertEqual(
            res["subpages"],
            ["https://www.industrialmetal.es/contacto", "https://www.industrialmetal.es/aviso-legal"],
        )

    def test_junk_email_filtering(self) -> None:
        self.assertFalse(is_valid_business_email("banner@2x.webp"))
        self.assertFalse(is_valid_business_email("test@example.com"))
        self.assertFalse(is_valid_business_email("noreply@company.io"))
        self.assertTrue(is_valid_business_email("founders@startup.ai"))


if __name__ == "__main__":
    unittest.main()
