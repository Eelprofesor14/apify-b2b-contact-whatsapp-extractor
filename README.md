# B2B Contact, WhatsApp & Tax ID Extractor (MCP-Ready)

Fast, lightweight, zero-browser async **B2B Lead Enrichment Actor** built on `httpx` + `BeautifulSoup4` for sales automation (`n8n`, `Make`, `Clay`, `Zapier`) and **AI Agents via Model Context Protocol (`apify-mcp-server`)**.

Unlike generic regex scrapers that miss protected addresses or return image filenames, this Actor decodes **Cloudflare Email Protection (`data-cfemail`)**, de-obfuscates `[at]` / `[arroba]` patterns, parses **Schema.org JSON-LD (`Organization` / `LocalBusiness`)**, extracts **WhatsApp Business numbers** (`wa.me` & `api.whatsapp.com`), and detects **LATAM & Spain B2B Tax IDs** (`CUIT`, `RUT`, `RFC`, `NIF/CIF`, `CNPJ`).

## Key Capabilities

- **Cloudflare & Anti-Bot Email Recovery:** Decodes `data-cfemail` and `/cdn-cgi/l/email-protection` hashes automatically without paying for headless browser RAM.
- **WhatsApp Business Discovery:** Captures direct commercial WhatsApp numbers (`+54...`, `+34...`, `+52...`, `+55...`, `+1...`) critical for B2B outreach across LATAM, Spain, and global SMBs.
- **Structured JSON-LD & Multilingual Subpage Crawling:** Automatically inspects `/contact`, `/contacto`, `/quienes-somos`, `/nosotros`, `/aviso-legal`, `/fale-conosco`, and `/about`.
- **Tax & Legal Entity IDs:** Extracts labeled `AR-CUIT`, `CL-RUT`, `MX-RFC`, `ES-NIF/CIF`, and `BR-CNPJ` from legal footers and imprint pages.
- **MCP-Ready Output & Summary:** Writes clean structured dataset rows plus a compact `SUMMARY` record in the Key-Value Store for LLM / MCP agent tool-calling.

## Input Example

```json
{
  "domains": [
    "https://apify.com",
    "example-industrial.es"
  ],
  "checkContactPages": true,
  "maxSubpagesPerDomain": 3,
  "onlyWithContacts": false,
  "maxConcurrency": 8
}
```

## Output Dataset Example

```json
{
  "domain": "industrialmetal.es",
  "url": "https://www.industrialmetal.es/",
  "status": "ok",
  "company_name": "Industrial Metal S.L.",
  "title": "Industrial Metal S.L. | Fabricación B2B",
  "description": "Proveedor mayorista industrial en España y Argentina.",
  "emails": [
    "directorio@industrialmetal.es",
    "hola@industrialmetal.es",
    "ventas@industrialmetal.es"
  ],
  "whatsapp": [
    "+34600112233",
    "+5491145678901"
  ],
  "phones": [
    "+34 910 123 456"
  ],
  "tax_ids": [
    "AR-CUIT: 30-71234567-9",
    "ES-NIF/CIF: B12345678"
  ],
  "linkedin": [
    "https://www.linkedin.com/company/industrial-metal-sl"
  ],
  "twitter_x": [
    "https://x.com/industrialmetal"
  ],
  "instagram": [],
  "facebook": [],
  "github": [],
  "pages_checked": 3
}
```

## Using with AI Agents (Model Context Protocol — MCP)

Connect this Actor directly to Claude Desktop, Cursor, Windsurf, or Google Antigravity via [Apify's MCP Server](https://docs.apify.com/platform/integrations/mcp) to enrich company domains with verified emails and WhatsApp numbers in real time during agentic workflows.
