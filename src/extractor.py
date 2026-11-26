"""Pure, deterministic B2B contact, WhatsApp, Cloudflare email, JSON-LD & Tax ID extractor."""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, unquote, urljoin, urlparse
from bs4 import BeautifulSoup

EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,15}\b")
OBFUSCATED_EMAIL_RE = re.compile(
    r"\b([a-zA-Z0-9._%+\-]+)\s*(?:\[at\]|\(at\)|\[arroba\]|\(arroba\)|\s+at\s+|\s+arroba\s+)\s*"
    r"([a-zA-Z0-9.\-]+)\s*(?:\[dot\]|\(dot\)|\[punto\]|\(punto\)|\.)\s*([a-zA-Z]{2,15})\b",
    re.IGNORECASE,
)
PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s.\-]?)?(?:\(\d{1,4}\)[\s.\-]?)?\d{2,4}[\s.\-]\d{3,4}[\s.\-]\d{3,4}")
WA_PHONE_RE = re.compile(r"(?:wa\.me/|whatsapp\.com/send/?\?[^\"'\s>]*phone=)\+?(\d{8,15})", re.IGNORECASE)

# High-precision labeled LATAM / Spain B2B Tax IDs
TAX_PATTERNS = [
    ("AR-CUIT", re.compile(r"\bCUIT[:\sN°º\-]*(\d{2}-\d{8}-\d)\b", re.IGNORECASE)),
    ("CL-RUT", re.compile(r"\bRUT[:\sN°º\-]*(\d{1,2}\.?\d{3}\.?\d{3}-[\dkK])\b", re.IGNORECASE)),
    ("BR-CNPJ", re.compile(r"\bCNPJ[:\sN°º\-]*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})\b", re.IGNORECASE)),
    ("ES-NIF/CIF", re.compile(r"\b(?:CIF|NIF)[:\sN°º\-]*([A-HJ-NP-SUVW]\d{7}[0-9A-J]|\d{8}[A-Z])\b", re.IGNORECASE)),
    ("MX-RFC", re.compile(r"\bRFC[:\sN°º\-]*([A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3})\b", re.IGNORECASE)),
]

IGNORED_EMAIL_EXTS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif", ".ico",
    ".css", ".js", ".mjs", ".map", ".woff", ".woff2", ".ttf", ".pdf",
)
JUNK_EMAIL_DOMAINS = {
    "example.com", "example.org", "domain.com", "yourdomain.com", "email.com",
    "sentry.io", "sentry-next.wixpress.com", "wixpress.com", "cloudflare.com",
}
JUNK_EMAIL_PREFIXES = ("noreply@", "no-reply@", "donotreply@", "sentry@")

CONTACT_PATH_KEYWORDS = (
    "contact", "contacto", "contactenos", "fale-conosco", "contato",
    "about", "nosotros", "quienes-somos", "sobre", "empresa",
    "team", "equipo", "legal", "aviso-legal", "imprint", "impressum",
)


def normalize_url(raw: str) -> str:
    cleaned = raw.strip()
    if not cleaned.startswith(("http://", "https://")):
        return f"https://{cleaned}"
    return cleaned


def decode_cfemail(hex_str: str) -> str | None:
    """Decodes Cloudflare's data-cfemail XOR-obfuscated email string."""
    try:
        hex_clean = hex_str.strip()
        if len(hex_clean) < 4 or len(hex_clean) % 2 != 0:
            return None
        key = int(hex_clean[:2], 16)
        decoded = "".join(
            chr(int(hex_clean[i : i + 2], 16) ^ key)
            for i in range(2, len(hex_clean), 2)
        )
        return decoded if "@" in decoded else None
    except ValueError:
        return None


def is_valid_business_email(addr: str) -> bool:
    low = addr.strip().lower().strip(".,;:()[]<>\"'")
    if not low or "@" not in low or len(low) > 120:
        return False
    if low.endswith(IGNORED_EMAIL_EXTS) or low.startswith(JUNK_EMAIL_PREFIXES):
        return False
    local, _, domain = low.partition("@")
    if not local or not domain or "." not in domain:
        return False
    if domain in JUNK_EMAIL_DOMAINS or any(domain.endswith("." + d) for d in JUNK_EMAIL_DOMAINS):
        return False
    # Reject asset version strings like logo@2x.png or bundle@1.2.3
    tld = domain.rsplit(".", 1)[-1]
    if not tld.isalpha() or len(tld) < 2:
        return False
    return bool(EMAIL_RE.fullmatch(low))


def _extract_jsonld_signals(soup: BeautifulSoup) -> dict:
    company_name = ""
    emails: set[str] = set()
    phones: set[str] = set()
    same_as: list[str] = []

    def walk(node: object) -> None:
        nonlocal company_name
        if isinstance(node, dict):
            ntype = str(node.get("@type", "")).lower()
            if any(k in ntype for k in ("organization", "business", "corporation", "store", "company")):
                if not company_name and isinstance(node.get("name"), str):
                    company_name = node["name"].strip()
            if isinstance(node.get("email"), str):
                emails.add(node["email"].replace("mailto:", "").strip())
            if isinstance(node.get("telephone"), str):
                phones.add(node["telephone"].strip())
            sa = node.get("sameAs")
            if isinstance(sa, str):
                same_as.append(sa)
            elif isinstance(sa, list):
                same_as.extend(x for x in sa if isinstance(x, str))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            walk(json.loads(raw))
        except Exception:
            continue

    return {
        "company_name": company_name,
        "emails": emails,
        "phones": phones,
        "same_as": same_as,
    }


def extract_signals(html: str, base_url: str, max_subpages: int = 3) -> dict:
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    meta_desc = ""
    meta_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    if not meta_tag:
        meta_tag = soup.find("meta", attrs={"property": re.compile(r"^og:description$", re.I)})
    if meta_tag and meta_tag.get("content"):
        meta_desc = str(meta_tag["content"]).strip()

    og_site = soup.find("meta", attrs={"property": re.compile(r"^og:site_name$", re.I)})
    og_name = str(og_site["content"]).strip() if og_site and og_site.get("content") else ""

    jld = _extract_jsonld_signals(soup)
    company_name = jld["company_name"] or og_name or (title.split("|")[0].split("—")[0].split("-")[0].strip()[:80])

    raw_emails: set[str] = set(jld["emails"])
    raw_phones: set[str] = set(jld["phones"])
    whatsapp: set[str] = set()

    # Decode Cloudflare protected emails (<a class="__cf_email__" data-cfemail="..."> or /cdn-cgi/l/email-protection#...)
    for tag in soup.find_all(attrs={"data-cfemail": True}):
        dec = decode_cfemail(str(tag["data-cfemail"]))
        if dec:
            raw_emails.add(dec)

    text = soup.get_text(" ", strip=True)
    raw_emails.update(EMAIL_RE.findall(text))
    for m in OBFUSCATED_EMAIL_RE.finditer(text):
        raw_emails.add(f"{m.group(1)}@{m.group(2)}.{m.group(3)}")

    for m in WA_PHONE_RE.finditer(html):
        whatsapp.add(f"+{m.group(1)}")

    tax_ids: set[str] = set()
    for label, pattern in TAX_PATTERNS:
        for tm in pattern.finditer(text):
            tax_ids.add(f"{label}: {tm.group(1).upper()}")

    socials: dict[str, set[str]] = {
        "linkedin": set(),
        "twitter_x": set(),
        "github": set(),
        "instagram": set(),
        "facebook": set(),
    }
    subpages: list[str] = []
    seen_subpages: set[str] = set()
    base_host = urlparse(base_url).netloc.lower().removeprefix("www.")

    def classify_link(raw_href: str) -> None:
        href_str = raw_href.strip()
        if not href_str:
            return
        low_raw = href_str.lower()
        if low_raw.startswith("mailto:"):
            addr = unquote(href_str.split(":", 1)[1].split("?", 1)[0]).strip()
            if addr:
                raw_emails.add(addr)
            return
        if low_raw.startswith("tel:"):
            tel = unquote(href_str.split(":", 1)[1].split("?", 1)[0]).strip()
            if 7 <= sum(c.isdigit() for c in tel) <= 15:
                raw_phones.add(tel)
            return
        if "/cdn-cgi/l/email-protection#" in low_raw:
            frag = href_str.split("#", 1)[1].split("?", 1)[0]
            dec = decode_cfemail(frag)
            if dec:
                raw_emails.add(dec)
            return

        full = urljoin(base_url, href_str)
        low = full.lower()
        for wm in WA_PHONE_RE.finditer(full):
            whatsapp.add(f"+{wm.group(1)}")
        if "whatsapp.com/" in low and "phone=" in low:
            qs = parse_qs(urlparse(full).query)
            for p in qs.get("phone", []):
                digits = "".join(c for c in p if c.isdigit())
                if 8 <= len(digits) <= 15:
                    whatsapp.add(f"+{digits}")

        clean_social = full.split("?")[0].rstrip("/")
        if "linkedin.com/company/" in low or "linkedin.com/in/" in low or "linkedin.com/school/" in low:
            socials["linkedin"].add(clean_social)
        elif ("twitter.com/" in low or "x.com/" in low) and "/intent/" not in low and "/share" not in low:
            socials["twitter_x"].add(clean_social)
        elif "github.com/" in low and not low.endswith("github.com"):
            socials["github"].add(clean_social)
        elif "instagram.com/" in low and "/p/" not in low and "/reel/" not in low:
            socials["instagram"].add(clean_social)
        elif "facebook.com/" in low and "sharer" not in low:
            socials["facebook"].add(clean_social)
        else:
            parsed = urlparse(full)
            link_host = parsed.netloc.lower().removeprefix("www.")
            if parsed.scheme in ("http", "https") and link_host == base_host:
                norm_sub = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
                if norm_sub != base_url.rstrip("/") and norm_sub not in seen_subpages:
                    if any(k in parsed.path.lower() for k in CONTACT_PATH_KEYWORDS):
                        seen_subpages.add(norm_sub)
                        subpages.append(norm_sub)

    for a in soup.find_all("a", href=True):
        classify_link(str(a["href"]))
    for s_url in jld["same_as"]:
        classify_link(s_url)

    for pm in PHONE_RE.findall(text):
        digits = sum(c.isdigit() for c in pm)
        if 8 <= digits <= 15:
            # Avoid matching ISO dates like 2026-11-26
            if not re.fullmatch(r"20\d{2}[\-./]\d{2}[\-./]\d{2}", pm.strip()):
                raw_phones.add(re.sub(r"\s+", " ", pm.strip()))

    clean_emails = sorted({
        e.strip().lower().strip(".,;:()[]<>\"'")
        for e in raw_emails
        if is_valid_business_email(e)
    })
    clean_phones = sorted(raw_phones)[:12]

    return {
        "company_name": company_name,
        "title": title,
        "description": meta_desc,
        "emails": clean_emails,
        "whatsapp": sorted(whatsapp),
        "phones": clean_phones,
        "tax_ids": sorted(tax_ids),
        "linkedin": sorted(socials["linkedin"]),
        "twitter_x": sorted(socials["twitter_x"]),
        "instagram": sorted(socials["instagram"]),
        "facebook": sorted(socials["facebook"]),
        "github": sorted(socials["github"]),
        "subpages": subpages[:max_subpages],
    }
