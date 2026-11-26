"""Apify Actor entrypoint: Async B2B Contact, WhatsApp & Tax ID Extractor (PPE & MCP-Ready)."""
from __future__ import annotations

import asyncio
from urllib.parse import urlparse
import httpx
from apify import Actor

from .extractor import extract_signals, normalize_url

LIST_FIELDS = (
    "emails",
    "whatsapp",
    "phones",
    "tax_ids",
    "linkedin",
    "twitter_x",
    "instagram",
    "facebook",
    "github",
)


async def process_domain(
    raw_domain: str,
    *,
    check_subpages: bool,
    max_subpages: int,
    timeout_secs: float,
    proxy_config: object | None,
    sem: asyncio.Semaphore,
) -> dict:
    url = normalize_url(raw_domain)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-419,es;q=0.9,en-US;q=0.8,en;q=0.7,pt;q=0.6",
    }

    async with sem:
        proxy_url = await proxy_config.new_url() if proxy_config is not None else None
        async with httpx.AsyncClient(
            headers=headers,
            proxy=proxy_url,
            follow_redirects=True,
            timeout=timeout_secs,
        ) as client:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                final_url = str(resp.url)
                data = extract_signals(resp.text, final_url, max_subpages=max_subpages)
                pages_checked = 1

                if check_subpages and data["subpages"]:
                    sub_tasks = [client.get(sub_url) for sub_url in data["subpages"]]
                    sub_responses = await asyncio.gather(*sub_tasks, return_exceptions=True)
                    for sub_resp in sub_responses:
                        if isinstance(sub_resp, httpx.Response) and sub_resp.status_code == 200:
                            pages_checked += 1
                            sub_data = extract_signals(
                                sub_resp.text,
                                str(sub_resp.url),
                                max_subpages=0,
                            )
                            for k in LIST_FIELDS:
                                data[k] = sorted(set(data[k]) | set(sub_data[k]))

                return {
                    "domain": urlparse(final_url).netloc.lower().removeprefix("www."),
                    "url": final_url,
                    "status": "ok",
                    "company_name": data["company_name"],
                    "title": data["title"],
                    "description": data["description"],
                    "emails": data["emails"],
                    "whatsapp": data["whatsapp"],
                    "phones": data["phones"],
                    "tax_ids": data["tax_ids"],
                    "linkedin": data["linkedin"],
                    "twitter_x": data["twitter_x"],
                    "instagram": data["instagram"],
                    "facebook": data["facebook"],
                    "github": data["github"],
                    "pages_checked": pages_checked,
                }
            except Exception as exc:
                return {
                    "domain": urlparse(url).netloc.lower().removeprefix("www."),
                    "url": url,
                    "status": f"error: {type(exc).__name__}",
                    "company_name": "",
                    "title": "",
                    "description": "",
                    "emails": [],
                    "whatsapp": [],
                    "phones": [],
                    "tax_ids": [],
                    "linkedin": [],
                    "twitter_x": [],
                    "instagram": [],
                    "facebook": [],
                    "github": [],
                    "pages_checked": 0,
                }


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        raw_domains = actor_input.get("domains") or []
        domains = [str(d).strip() for d in raw_domains if str(d).strip()]
        check_subpages = bool(actor_input.get("checkContactPages", True))
        max_subpages = int(actor_input.get("maxSubpagesPerDomain", 3))
        only_with_contacts = bool(actor_input.get("onlyWithContacts", False))
        max_concurrency = max(1, min(25, int(actor_input.get("maxConcurrency", 8))))
        timeout_secs = float(actor_input.get("requestTimeoutSecs", 15))

        if not domains:
            Actor.log.warning("No domains provided in 'domains' input array.")
            await Actor.set_value("SUMMARY", {"processed": 0, "pushed": 0, "with_contacts": 0})
            return

        # Deduplicate domains while preserving order
        seen: set[str] = set()
        unique_domains: list[str] = []
        for d in domains:
            key = d.lower().removeprefix("https://").removeprefix("http://").removeprefix("www.").rstrip("/")
            if key and key not in seen:
                seen.add(key)
                unique_domains.append(d)

        proxy_cfg_raw = actor_input.get("proxyConfiguration")
        proxy_config = None
        if isinstance(proxy_cfg_raw, dict) and (
            proxy_cfg_raw.get("useApifyProxy") or proxy_cfg_raw.get("proxyUrls")
        ):
            proxy_config = await Actor.create_proxy_configuration(actor_proxy_input=proxy_cfg_raw)

        sem = asyncio.Semaphore(max_concurrency)
        tasks = [
            process_domain(
                d,
                check_subpages=check_subpages,
                max_subpages=max_subpages,
                timeout_secs=timeout_secs,
                proxy_config=proxy_config,
                sem=sem,
            )
            for d in unique_domains
        ]

        pushed = 0
        with_contacts = 0
        for coro in asyncio.as_completed(tasks):
            record = await coro
            has_contact = bool(record["emails"] or record["whatsapp"] or record["phones"])
            if has_contact:
                with_contacts += 1
            if only_with_contacts and not has_contact:
                Actor.log.info(f"Skipped {record['domain']} (no email/phone/whatsapp found)")
                continue

            await Actor.push_data(record)
            pushed += 1
            Actor.log.info(
                f"[{record['status']}] {record['domain']} -> "
                f"{len(record['emails'])} emails, {len(record['whatsapp'])} WhatsApp, "
                f"{len(record['phones'])} phones ({record['pages_checked']} pages)"
            )

        summary = {
            "processed_domains": len(unique_domains),
            "pushed_records": pushed,
            "leads_with_contacts": with_contacts,
        }
        await Actor.set_value("SUMMARY", summary)
        Actor.log.info(f"Completed B2B enrichment: {summary}")


if __name__ == "__main__":
    asyncio.run(main())
