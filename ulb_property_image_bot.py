#!/usr/bin/env python3
"""
ULB Haryana public property-photo downloader.

Default behavior:
  * Open the public property search page.
  * Select the requested Town.
  * Read ALL Colony values from the live Colony dropdown.
  * For each Colony:
      - select Residential
      - search
      - walk through result pages
      - save the first/best-looking property photo as PID.jpeg
  * Continue with the next Colony.

You can still run one specific colony with --colony.

Examples:
  python ulb_property_image_bot.py
  python ulb_property_image_bot.py --town "Faridabad"
  python ulb_property_image_bot.py --town "Faridabad" --colony "Sector 15"
  python ulb_property_image_bot.py --town "Faridabad" --list-colonies
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

from PIL import Image, UnidentifiedImageError
from playwright.async_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError, async_playwright


BASE_URL = "https://property.ulbharyana.gov.in/PropertyList/PropertySearch"

# Haryana's property documentation describes the PID as an eight-character ID.
PID_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9]{8}(?![A-Za-z0-9])")

DETAIL_WORDS = re.compile(r"\b(view|detail|details|property|photo|image)\b", re.I)
IMAGE_HINTS = re.compile(r"(property|prop|photo|image|building|house|upload|document)", re.I)
UI_IMAGE_HINTS = re.compile(r"(logo|icon|captcha|menu|arrow|close|loader|spinner|favicon)", re.I)


def clean_pid(text: str) -> str | None:
    if not text:
        return None
    m = PID_RE.search(text.replace("\n", " "))
    return m.group(0).upper() if m else None


def same_site(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
        return host.endswith("ulbharyana.gov.in")
    except Exception:
        return False


async def select_element_for_label(page: Page, label_text: str):
    """Locate the select element associated with a visible label or nearby text."""
    selects = page.locator("select")
    n = await selects.count()
    target = label_text.lower()

    # 1) label[for] association
    for i in range(n):
        sel = selects.nth(i)
        info = await sel.evaluate(
            """el => {
                const id = el.id || "";
                let label = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
                return {
                    id,
                    name: el.getAttribute("name") || "",
                    label: label ? label.innerText : ""
                };
            }"""
        )
        if target in (info["label"] or "").lower():
            return sel

    # 2) nearby parent/container text
    for i in range(n):
        sel = selects.nth(i)
        info = await sel.evaluate(
            """el => {
                let p = el.parentElement;
                let pieces = [];
                for (let j = 0; j < 3 && p; j++, p = p.parentElement) {
                    pieces.push((p.innerText || "").slice(0, 500));
                }
                return {
                    id: el.id || "",
                    name: el.getAttribute("name") || "",
                    text: pieces.join(" | ")
                };
            }"""
        )
        hay = " ".join([info["id"], info["name"], info["text"]]).lower()
        if target in hay:
            return sel

    raise RuntimeError(f"Could not locate dropdown for {label_text!r}")


async def dropdown_options(select) -> list[dict]:
    """Return enabled dropdown options, excluding obvious placeholder entries."""
    options = await select.locator("option").evaluate_all(
        """els => els.map(o => ({
            text: (o.textContent || "").trim(),
            value: o.value,
            disabled: !!o.disabled
        }))"""
    )
    cleaned = []
    for opt in options:
        text = (opt["text"] or "").strip()
        if opt["disabled"]:
            continue
        low = text.lower()
        if not text:
            continue
        if low in {
            "select",
            "select town",
            "select colony",
            "select category",
            "--select--",
            "-- select --",
            "choose",
            "choose town",
            "choose colony",
            "choose category",
        }:
            continue
        # Do not treat a blank/empty value as a usable data option.
        if opt["value"] is None or opt["value"] == "":
            continue
        cleaned.append({"text": text, "value": opt["value"]})
    return cleaned


async def wait_for_colony_options(page: Page, colony_sel, timeout_ms: int = 30_000) -> list[dict]:
    """Wait until the Colony dropdown has real options after changing Town."""
    deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
    last_signature = None
    stable_count = 0

    while asyncio.get_running_loop().time() < deadline:
        opts = await dropdown_options(colony_sel)
        signature = tuple((o["value"], o["text"]) for o in opts)

        # We want at least one real colony option. Requiring the list to be
        # observed twice helps avoid reading during an AJAX replacement.
        if opts:
            if signature == last_signature:
                stable_count += 1
            else:
                stable_count = 0
            last_signature = signature
            if stable_count >= 2:
                return opts
        await page.wait_for_timeout(500)

    return await dropdown_options(colony_sel)


async def choose_option_by_text_or_value(select, desired: str) -> str:
    desired = desired.strip()
    options = await dropdown_options(select)
    if not options:
        raise RuntimeError("Dropdown contains no usable options.")

    # Exact text
    for opt in options:
        if opt["text"].lower() == desired.lower():
            await select.select_option(value=opt["value"])
            return opt["text"]

    # Exact value
    for opt in options:
        if opt["value"] == desired:
            await select.select_option(value=opt["value"])
            return opt["text"]

    # Case-insensitive substring
    for opt in options:
        if desired.lower() in opt["text"].lower():
            await select.select_option(value=opt["value"])
            return opt["text"]

    sample = ", ".join(x["text"] for x in options[:30])
    raise RuntimeError(
        f"Could not find {desired!r} in dropdown. First options: {sample}"
    )


async def get_colony_values_for_town(page: Page, town: str, verbose: bool = False) -> list[dict]:
    """Open the search page, select Town, then copy all live Colony options."""
    await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30_000)

    town_sel = await select_element_for_label(page, "Select Town")
    picked_town = await choose_option_by_text_or_value(town_sel, town)
    print(f"[+] Town selected: {picked_town}")

    colony_sel = await select_element_for_label(page, "Select Colony")
    colonies = await wait_for_colony_options(page, colony_sel)

    if not colonies:
        raise RuntimeError(
            "No Colony values appeared after selecting the Town. "
            "The portal may be temporarily unavailable or may have changed."
        )

    print(f"[+] Copied {len(colonies)} Colony values from the live dropdown.")
    for i, colony in enumerate(colonies, 1):
        print(f"    {i:>4}. {colony['text']}")

    if verbose:
        print("[debug] Colony values:")
        for colony in colonies:
            print(f"        text={colony['text']!r} value={colony['value']!r}")

    return colonies


async def prepare_search(
    page: Page,
    town: str,
    colony_value: str,
    colony_text: str,
) -> str:
    """Fresh page for each colony so AJAX/search state does not leak between colonies."""
    await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30_000)

    town_sel = await select_element_for_label(page, "Select Town")
    picked_town = await choose_option_by_text_or_value(town_sel, town)

    colony_sel = await select_element_for_label(page, "Select Colony")
    colonies = await wait_for_colony_options(page, colony_sel)
    # Prefer the original value; fall back to text when needed.
    try:
        await colony_sel.select_option(value=colony_value)
    except Exception:
        await choose_option_by_text_or_value(colony_sel, colony_text)

    cat_sel = await select_element_for_label(page, "Select Category")
    picked_category = await choose_option_by_text_or_value(cat_sel, "Residential")

    print(f"[+] {picked_town} -> {colony_text} -> {picked_category}")
    return colony_text


async def click_search(page: Page) -> None:
    selectors = [
        'button:has-text("Search")',
        'input[type="submit"][value*="Search" i]',
        'input[type="button"][value*="Search" i]',
    ]
    for selector in selectors:
        loc = page.locator(selector)
        if await loc.count():
            await loc.first.click()
            await wait_for_results(page)
            return

    txt = page.get_by_text("Search", exact=True)
    if await txt.count():
        await txt.first.click()
        await wait_for_results(page)
        return

    raise RuntimeError("Could not find the Search button.")


async def wait_for_results(page: Page) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=15_000)
    except PlaywrightTimeoutError:
        pass
    await page.wait_for_timeout(1_000)


async def extract_image_candidates(block) -> list[dict]:
    candidates = []

    imgs = block.locator("img")
    for i in range(await imgs.count()):
        img = imgs.nth(i)
        try:
            data = await img.evaluate(
                """el => ({
                    src: el.currentSrc || el.src || el.getAttribute('data-src')
                        || el.getAttribute('data-original')
                        || el.getAttribute('data-lazy-src') || "",
                    alt: el.alt || "",
                    width: el.naturalWidth || el.width || 0,
                    height: el.naturalHeight || el.height || 0
                })"""
            )
        except Exception:
            continue
        if data["src"]:
            candidates.append(data)

    els = block.locator("[style*='background-image']")
    for i in range(await els.count()):
        el = els.nth(i)
        try:
            data = await el.evaluate(
                """el => {
                    const bg = getComputedStyle(el).backgroundImage || "";
                    const m = bg.match(/url\\(["']?(.*?)["']?\\)/i);
                    const r = el.getBoundingClientRect();
                    return {
                        src: m ? m[1] : "",
                        alt: "",
                        width: Math.round(r.width),
                        height: Math.round(r.height)
                    };
                }"""
            )
        except Exception:
            continue
        if data["src"]:
            candidates.append(data)

    return candidates


def rank_image(url: str, width: int, height: int, alt: str = "") -> float:
    text = f"{url} {alt}"
    score = 0.0
    if IMAGE_HINTS.search(text):
        score += 20
    if UI_IMAGE_HINTS.search(text):
        score -= 50
    if width and height:
        score += min((width * height) / 50_000, 25)
    if re.search(r"\.(jpe?g|png|webp)(?:$|\?)", url, re.I):
        score += 5
    return score


async def get_result_blocks(page: Page):
    blocks = []

    trs = page.locator("tr")
    for i in range(await trs.count()):
        tr = trs.nth(i)
        try:
            text = (await tr.inner_text()).strip()
        except Exception:
            continue
        if clean_pid(text):
            blocks.append(tr)

    if blocks:
        return blocks

    generic = page.locator(
        ".card, [class*='property'], [id*='property'], article, .result, .search-result"
    )
    for i in range(await generic.count()):
        el = generic.nth(i)
        try:
            text = (await el.inner_text()).strip()
        except Exception:
            continue
        if clean_pid(text):
            blocks.append(el)

    if blocks:
        return blocks

    return [page.locator("body")]


async def collect_page_records(page: Page) -> list[tuple[str, list[dict], list[str]]]:
    records: dict[str, tuple[list[dict], list[str]]] = {}
    blocks = await get_result_blocks(page)

    for block in blocks:
        try:
            text = (await block.inner_text()).strip()
        except Exception:
            continue

        pid = clean_pid(text)
        if not pid:
            continue

        imgs = await extract_image_candidates(block)
        links = []
        anchors = block.locator("a[href]")
        for i in range(await anchors.count()):
            a = anchors.nth(i)
            try:
                href = await a.get_attribute("href")
                if href:
                    links.append(urljoin(page.url, href))
            except Exception:
                continue

        if pid not in records:
            records[pid] = (imgs, links)
        else:
            old_imgs, old_links = records[pid]
            records[pid] = (
                old_imgs + imgs,
                list(dict.fromkeys(old_links + links)),
            )

    return [(pid, imgs, links) for pid, (imgs, links) in records.items()]


async def first_photo_from_detail(
    context: BrowserContext,
    hrefs: list[str],
    pid: str,
    verbose: bool,
) -> dict | None:
    page = await context.new_page()
    try:
        for href in hrefs:
            if not same_site(href):
                continue
            if not DETAIL_WORDS.search(href):
                continue

            try:
                await page.goto(href, wait_until="domcontentloaded", timeout=20_000)
                await page.wait_for_timeout(700)
            except Exception:
                continue

            body_text = (await page.locator("body").inner_text()).strip()
            found_pid = clean_pid(body_text) or pid
            if found_pid != pid:
                continue

            imgs = await extract_image_candidates(page.locator("body"))
            if imgs:
                imgs = sorted(
                    imgs,
                    key=lambda x: rank_image(
                        x["src"],
                        int(x["width"] or 0),
                        int(x["height"] or 0),
                        x["alt"],
                    ),
                    reverse=True,
                )
                for img in imgs:
                    if not UI_IMAGE_HINTS.search(img["src"] + " " + img["alt"]):
                        if verbose:
                            print(f"        detail image: {img['src']}")
                        return img
    finally:
        await page.close()

    return None


async def download_as_jpeg(
    context: BrowserContext,
    page_url: str,
    image_url: str,
    out_file: Path,
) -> bool:
    image_url = urljoin(page_url, image_url)
    if image_url.startswith("data:"):
        return False

    try:
        resp = await context.request.get(
            image_url,
            headers={"Referer": page_url},
            timeout=30_000,
        )
        if not resp.ok:
            return False
        data = await resp.body()
    except Exception:
        return False

    try:
        with Image.open(io.BytesIO(data)) as original:
            im = original.convert("RGBA") if original.mode in ("RGBA", "LA", "P") else original.convert("RGB")
            if im.mode == "RGBA":
                bg = Image.new("RGB", im.size, "white")
                bg.paste(im, mask=im.getchannel("A"))
                im = bg
            im.save(out_file, "JPEG", quality=92, optimize=True)
        return True
    except (UnidentifiedImageError, OSError):
        return False


async def find_next_button(page: Page):
    candidates = [
        page.get_by_role("link", name=re.compile(r"^\s*Next\s*$", re.I)),
        page.get_by_role("button", name=re.compile(r"^\s*Next\s*$", re.I)),
        page.locator('a[aria-label*="next" i], button[aria-label*="next" i]'),
        page.get_by_text("Next", exact=True),
    ]
    for loc in candidates:
        if await loc.count():
            item = loc.last
            try:
                disabled = await item.is_disabled()
            except Exception:
                disabled = False
            aria_disabled = (await item.get_attribute("aria-disabled") or "").lower()
            cls = (await item.get_attribute("class") or "").lower()
            if not disabled and aria_disabled != "true" and "disabled" not in cls:
                return item
    return None


async def process_results(
    page: Page,
    context: BrowserContext,
    out_dir: Path,
    max_pages: int,
    verbose: bool,
    manifest_writer,
    colony_text: str,
) -> tuple[int, int]:
    out_dir.mkdir(parents=True, exist_ok=True)

    seen_pids: set[str] = set()
    saved = 0
    page_no = 1

    while page_no <= max_pages:
        print(f"    [+] Processing result page {page_no} for {colony_text}...")
        records = await collect_page_records(page)

        for pid, imgs, links in records:
            if pid in seen_pids:
                continue
            seen_pids.add(pid)

            target = out_dir / f"{pid}.jpeg"
            if target.exists():
                print(f"        {pid}: exists, skipping")
                manifest_writer.writerow([colony_text, pid, "exists", str(target), ""])
                continue

            imgs = sorted(
                imgs,
                key=lambda x: rank_image(
                    x["src"],
                    int(x["width"] or 0),
                    int(x["height"] or 0),
                    x["alt"],
                ),
                reverse=True,
            )

            chosen = None
            for img in imgs:
                src = img.get("src", "")
                text = f"{src} {img.get('alt', '')}"
                if src and not UI_IMAGE_HINTS.search(text):
                    chosen = img
                    break

            if not chosen:
                chosen = await first_photo_from_detail(context, links, pid, verbose)

            if not chosen:
                print(f"        {pid}: no photograph found")
                manifest_writer.writerow([colony_text, pid, "no_photo", "", ""])
                continue

            ok = await download_as_jpeg(context, page.url, chosen["src"], target)
            if ok:
                saved += 1
                print(f"        {pid}: saved -> {target}")
                manifest_writer.writerow([colony_text, pid, "saved", str(target), chosen["src"]])
            else:
                print(f"        {pid}: image could not be downloaded/decoded")
                manifest_writer.writerow([colony_text, pid, "download_failed", "", chosen["src"]])

        next_btn = await find_next_button(page)
        if not next_btn:
            break

        before = (await page.locator("body").inner_text())[:5000]
        try:
            await next_btn.click()
            await page.wait_for_timeout(700)
            for _ in range(25):
                await page.wait_for_timeout(400)
                after = (await page.locator("body").inner_text())[:5000]
                if after != before:
                    break
        except Exception:
            break

        page_no += 1

    return len(seen_pids), saved


async def run(args) -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not args.headed)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 1000},
            locale="en-IN",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = out_dir / "download_manifest.csv"

        try:
            town = args.town
            if not town:
                town = input("Town: ").strip()

            # IMPORTANT: read Colony options from the live portal after Town is selected.
            colonies = await get_colony_values_for_town(page, town, verbose=args.verbose)

            if args.list_colonies:
                print(f"\n[+] Colony list for {town}:")
                for i, c in enumerate(colonies, 1):
                    print(f"{i}. {c['text']}")
                return 0

            if args.colony:
                wanted = args.colony.strip().lower()
                selected = [
                    c for c in colonies
                    if c["text"].lower() == wanted or c["value"] == args.colony
                ]
                if not selected:
                    # Also allow substring matching for convenience.
                    selected = [c for c in colonies if wanted in c["text"].lower()]
                if not selected:
                    raise RuntimeError(
                        f"Colony {args.colony!r} was not found in the live dropdown."
                    )
                colonies = selected

            print(f"\n[+] Colonies to process: {len(colonies)}")
            print(f"[+] Output folder: {out_dir.resolve()}")
            print(f"[+] Manifest: {manifest_path.resolve()}\n")

            manifest_exists = manifest_path.exists()
            with manifest_path.open("a", newline="", encoding="utf-8") as mf:
                writer = csv.writer(mf)
                if not manifest_exists:
                    writer.writerow(["colony", "pid", "status", "file", "source_image_url"])

                total_seen = 0
                total_saved = 0

                for idx, colony in enumerate(colonies, 1):
                    print("=" * 72)
                    print(f"[{idx}/{len(colonies)}] Colony: {colony['text']}")

                    try:
                        await prepare_search(page, town, colony["value"], colony["text"])
                        await click_search(page)

                        seen, saved = await process_results(
                            page,
                            context,
                            out_dir,
                            max_pages=args.max_pages,
                            verbose=args.verbose,
                            manifest_writer=writer,
                            colony_text=colony["text"],
                        )
                        total_seen += seen
                        total_saved += saved
                        mf.flush()
                        print(
                            f"    [+] Completed colony: {colony['text']} | "
                            f"unique PIDs: {seen} | images saved: {saved}"
                        )
                    except Exception as exc:
                        print(f"    [!] Colony failed: {colony['text']} -> {exc}", file=sys.stderr)
                        writer.writerow([colony["text"], "", "colony_failed", "", str(exc)])
                        mf.flush()
                        # Continue with the next colony instead of stopping the entire run.
                        continue

                    if args.delay_ms:
                        await page.wait_for_timeout(args.delay_ms)

                print("\n" + "=" * 72)
                print(f"[+] ALL DONE")
                print(f"[+] Colonies attempted: {len(colonies)}")
                print(f"[+] Unique PIDs seen (sum by colony): {total_seen}")
                print(f"[+] New images saved: {total_saved}")
                print(f"[+] Output: {out_dir.resolve()}")
                print(f"[+] Manifest: {manifest_path.resolve()}")

            return 0
        except PlaywrightTimeoutError as e:
            print(f"[!] Browser timeout: {e}", file=sys.stderr)
            print("[!] Try --headed to watch the portal while it runs.", file=sys.stderr)
            return 2
        except Exception as e:
            print(f"[!] Error: {e}", file=sys.stderr)
            print("[!] Try --headed --verbose for troubleshooting.", file=sys.stderr)
            return 2
        finally:
            await context.close()
            await browser.close()


def parse_args():
    ap = argparse.ArgumentParser(
        description=(
            "Read the ULB Haryana live Town/Colony dropdowns and download "
            "Residential property photographs by PID."
        )
    )
    ap.add_argument("--town", help="Town visible in the portal dropdown.")
    ap.add_argument(
        "--colony",
        help="Optional: process only this Colony. If omitted, EVERY live Colony is processed.",
    )
    ap.add_argument(
        "--list-colonies",
        action="store_true",
        help="Only print the Colony values found for the selected Town; do not download images.",
    )
    ap.add_argument(
        "--out",
        default="property_images",
        help="Output directory (default: property_images).",
    )
    ap.add_argument(
        "--max-pages",
        type=int,
        default=500,
        help="Maximum result pages per Colony (default: 500).",
    )
    ap.add_argument(
        "--delay-ms",
        type=int,
        default=750,
        help="Delay between Colonies in milliseconds (default: 750).",
    )
    ap.add_argument(
        "--headed",
        action="store_true",
        help="Show Chromium while the bot runs.",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Print dropdown values and extra image/detail diagnostics.",
    )
    return ap.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
