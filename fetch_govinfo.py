"""Prototype: fetch bill text versions from GPO govinfo bulk data.

This is an alternative to fetch_bills.py's Congress.gov API path. It pulls the
same legacy GPO DTD bill XML, but from govinfo.gov/bulkdata, which needs no API
key and has no per-request rate limit.

Two collections are used:
  - BILLS:      full bill *text* XML (legacy bill.dtd), one file per version.
  - BILLSTATUS: bill *metadata* (title, subjects, committee referrals) used for
                discovery and to recover bill titles the committee API omits.

URL shapes:
  text:   https://www.govinfo.gov/bulkdata/BILLS/{congress}/{session}/{type}/BILLS-{congress}{type}{number}{ver}.xml
  status: https://www.govinfo.gov/bulkdata/BILLSTATUS/{congress}/{type}/BILLSTATUS-{congress}{type}{number}.xml
"""

import sys
import xml.etree.ElementTree as ET

import httpx

BULK_BASE = "https://www.govinfo.gov/bulkdata"

# Map the Congress.gov human-readable version label (as stored in our fixtures'
# directory/file names) to the GPO version code used in govinfo filenames.
VERSION_NAME_TO_CODE = {
    "introduced-in-house": "ih",
    "introduced-in-senate": "is",
    "reported-in-house": "rh",
    "reported-in-senate": "rs",
    "engrossed-in-house": "eh",
    "engrossed-in-senate": "es",
    "enrolled-bill": "enr",
    "placed-on-calendar-senate": "pcs",
    "placed-on-calendar-house": "pch",
    "referred-in-senate": "rfs",
    "referred-in-house": "rfh",
}


def sessions_for_congress(congress: int) -> tuple[int, int]:
    """The two calendar years / sessions of a Congress, as session numbers."""
    return (1, 2)


def bill_xml_url(congress: int, session: int, bill_type: str, number: int, ver_code: str) -> str:
    """Build a govinfo BILLS text-XML URL for one version."""
    fname = f"BILLS-{congress}{bill_type}{number}{ver_code}.xml"
    return f"{BULK_BASE}/BILLS/{congress}/{session}/{bill_type}/{fname}"


def billstatus_url(congress: int, bill_type: str, number: int) -> str:
    """Build a govinfo BILLSTATUS metadata-XML URL for one bill."""
    fname = f"BILLSTATUS-{congress}{bill_type}{number}.xml"
    return f"{BULK_BASE}/BILLSTATUS/{congress}/{bill_type}/{fname}"


def fetch_bill_xml(
    client: httpx.Client, congress: int, bill_type: str, number: int, ver_code: str
) -> tuple[bytes | None, str | None]:
    """Download a version's text XML, probing both sessions of the Congress.

    Returns (content, url) or (None, None) if not found in either session.
    """
    for session in sessions_for_congress(congress):
        url = bill_xml_url(congress, session, bill_type, number, ver_code)
        resp = client.get(url)
        if resp.status_code == 200:
            return resp.content, url
    return None, None


def fetch_title(client: httpx.Client, congress: int, bill_type: str, number: int) -> str | None:
    """Pull the bill title from BILLSTATUS metadata (the field the committee API drops)."""
    url = billstatus_url(congress, bill_type, number)
    resp = client.get(url)
    if resp.status_code != 200:
        return None
    root = ET.fromstring(resp.content)
    el = root.find(".//bill/title")
    return el.text if el is not None else None


def _demo(client: httpx.Client) -> None:
    """Show discovery (title via BILLSTATUS) + text fetch for one bill."""
    congress, btype, num = 118, "s", 4690
    title = fetch_title(client, congress, btype, num)
    print(f"BILLSTATUS title for {congress} {btype.upper()} {num}: {title}", file=sys.stderr)
    content, url = fetch_bill_xml(client, congress, btype, num, "rs")
    if content:
        print(f"BILLS text fetched ({len(content):,} bytes) from {url}", file=sys.stderr)
    else:
        print("BILLS text not found", file=sys.stderr)


if __name__ == "__main__":
    with httpx.Client(timeout=30, follow_redirects=True) as c:
        _demo(c)
